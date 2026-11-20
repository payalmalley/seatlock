-- SEATLOCK schema (PostgreSQL 16). Our own schema: the organizers' starter kit was not available.
-- If the official schema arrives, diff against this file before changing anything.

-- ---------------------------------------------------------------- users
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT        NOT NULL UNIQUE,
    full_name     TEXT        NOT NULL,
    password_hash TEXT        NOT NULL,          -- Django PBKDF2 format
    role          TEXT        NOT NULL CHECK (role IN ('ADMIN', 'ORGANIZER', 'STUDENT')),
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------- events
CREATE TABLE events (
    id           BIGSERIAL PRIMARY KEY,
    organizer_id BIGINT      NOT NULL REFERENCES users(id),
    title        TEXT        NOT NULL,
    description  TEXT        NOT NULL DEFAULT '',
    venue        TEXT        NOT NULL DEFAULT '',
    starts_at    TIMESTAMPTZ NOT NULL,           -- booking closes at this instant
    status       TEXT        NOT NULL DEFAULT 'DRAFT'
                 CHECK (status IN ('DRAFT', 'PUBLISHED', 'CANCELLED')),
    version      INTEGER     NOT NULL DEFAULT 1, -- optimistic locking: UPDATE ... WHERE id=? AND version=?
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_organizer ON events(organizer_id);
CREATE INDEX idx_events_status_start ON events(status, starts_at);

-- ---------------------------------------------------------------- seats
-- seats.status holds only the durable states. "HELD" is derived from an active,
-- unexpired row in holds, so the seat row lock (SELECT ... FOR UPDATE) covers every state.
CREATE TABLE seats (
    id          BIGSERIAL PRIMARY KEY,
    event_id    BIGINT  NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    row_label   TEXT    NOT NULL,
    seat_number INTEGER NOT NULL CHECK (seat_number > 0),
    status      TEXT    NOT NULL DEFAULT 'AVAILABLE'
                CHECK (status IN ('AVAILABLE', 'BOOKED', 'BLOCKED')),
    UNIQUE (event_id, row_label, seat_number)
);
CREATE INDEX idx_seats_event ON seats(event_id);

-- ---------------------------------------------------------------- holds
-- One row per held seat. All seats of one hold request share hold_group (UUID).
CREATE TABLE holds (
    id         BIGSERIAL PRIMARY KEY,
    hold_group UUID        NOT NULL,
    event_id   BIGINT      NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id    BIGINT      NOT NULL REFERENCES users(id),
    seat_id    BIGINT      NOT NULL REFERENCES seats(id) ON DELETE CASCADE,
    status     TEXT        NOT NULL DEFAULT 'ACTIVE'
               CHECK (status IN ('ACTIVE', 'CONFIRMED', 'RELEASED', 'EXPIRED')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Safety net: a seat can have at most one ACTIVE hold, even if application locking has a bug.
-- Expired rows must be flipped to EXPIRED inside the hold transaction before a new hold is inserted.
CREATE UNIQUE INDEX uq_holds_active_seat ON holds(seat_id) WHERE status = 'ACTIVE';
CREATE INDEX idx_holds_user_event ON holds(user_id, event_id, status);
CREATE INDEX idx_holds_group ON holds(hold_group);

-- ------------------------------------------------------------- bookings
CREATE TABLE bookings (
    id            BIGSERIAL PRIMARY KEY,
    event_id      BIGINT      NOT NULL REFERENCES events(id),
    user_id       BIGINT      NOT NULL REFERENCES users(id),
    status        TEXT        NOT NULL DEFAULT 'CONFIRMED'
                  CHECK (status IN ('CONFIRMED', 'CANCELLED')),
    checked_in_at TIMESTAMPTZ,
    checked_in_by BIGINT REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelled_at  TIMESTAMPTZ
);
CREATE INDEX idx_bookings_user ON bookings(user_id, event_id);
CREATE INDEX idx_bookings_event ON bookings(event_id);

CREATE TABLE booking_seats (
    id         BIGSERIAL PRIMARY KEY,
    booking_id BIGINT  NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    event_id   BIGINT  NOT NULL REFERENCES events(id),
    seat_id    BIGINT  NOT NULL REFERENCES seats(id),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE   -- set FALSE when the booking is cancelled
);
-- Safety net: a seat can belong to at most one ACTIVE booking.
CREATE UNIQUE INDEX uq_booking_seats_active_seat ON booking_seats(seat_id) WHERE is_active;
CREATE INDEX idx_booking_seats_booking ON booking_seats(booking_id);

-- ------------------------------------------------------- audit (4 shards)
-- Globally unique, time-ordered IDs come from one shared sequence, so (id DESC) is a valid
-- cursor across all four shards.
CREATE SEQUENCE audit_id_seq;

-- Routing rule, enforced by each shard's CHECK constraint:
--   event action     -> shard = event_id % 4      (hash(event_id) = identity; stable and deterministic)
--   non-event action -> shard = actor_id % 4      (anonymous, e.g. failed login for unknown email -> shard 0)
CREATE TABLE audit_logs_0 (
    id          BIGINT      PRIMARY KEY DEFAULT nextval('audit_id_seq'),
    action      TEXT        NOT NULL CHECK (action IN (
                  'LOGIN','LOGIN_FAILED','SEAT_HELD','SEAT_HOLD_REJECTED','HOLD_EXPIRED',
                  'BOOKING_CONFIRMED','BOOKING_CANCELLED','EVENT_UPDATED','CHECKIN','ACCESS_DENIED')),
    actor_id    BIGINT,              -- no FK: failed logins may have no user
    event_id    BIGINT,              -- no FK: shard tables stay independent
    entity_type TEXT,
    entity_id   BIGINT,
    details     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT shard_routing_0 CHECK (
        (CASE WHEN event_id IS NOT NULL THEN event_id ELSE COALESCE(actor_id, 0) END) % 4 = 0)
);
CREATE TABLE audit_logs_1 (LIKE audit_logs_0 INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES);
CREATE TABLE audit_logs_2 (LIKE audit_logs_0 INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES);
CREATE TABLE audit_logs_3 (LIKE audit_logs_0 INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES);

-- LIKE copies the shard_routing_0 check; replace it with the right one per shard.
ALTER TABLE audit_logs_1 DROP CONSTRAINT shard_routing_0;
ALTER TABLE audit_logs_2 DROP CONSTRAINT shard_routing_0;
ALTER TABLE audit_logs_3 DROP CONSTRAINT shard_routing_0;
ALTER TABLE audit_logs_1 ADD CONSTRAINT shard_routing_1 CHECK (
    (CASE WHEN event_id IS NOT NULL THEN event_id ELSE COALESCE(actor_id, 0) END) % 4 = 1);
ALTER TABLE audit_logs_2 ADD CONSTRAINT shard_routing_2 CHECK (
    (CASE WHEN event_id IS NOT NULL THEN event_id ELSE COALESCE(actor_id, 0) END) % 4 = 2);
ALTER TABLE audit_logs_3 ADD CONSTRAINT shard_routing_3 CHECK (
    (CASE WHEN event_id IS NOT NULL THEN event_id ELSE COALESCE(actor_id, 0) END) % 4 = 3);

-- Per-shard indexes for event filter, date filter and cursor paging (newest first).
DO $$
DECLARE n INT;
BEGIN
    FOR n IN 0..3 LOOP
        EXECUTE format('CREATE INDEX idx_audit_logs_%s_id_desc ON audit_logs_%s (id DESC)', n, n);
        EXECUTE format('CREATE INDEX idx_audit_logs_%s_event ON audit_logs_%s (event_id, id DESC)', n, n);
        EXECUTE format('CREATE INDEX idx_audit_logs_%s_created ON audit_logs_%s (created_at DESC)', n, n);
    END LOOP;
END $$;