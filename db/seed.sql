-- SEATLOCK DEV SEED DATA (our own; not from the organizers).
-- Logins (dev only):  admin@seatlock.test / Admin@123
--                     organizer1@seatlock.test, organizer2@seatlock.test / Organizer@123
--                     student1..student20@seatlock.test / Student@123
-- Event start times are relative to now(), so the data is "fresh" on every reseed.

INSERT INTO users (id, email, full_name, password_hash, role) VALUES
 (1, 'admin@seatlock.test',      'Admin User',   'pbkdf2_sha256$600000$seatlockadmin$TvfAQJFp5n+wyriPmmbJUoTKFzjIoJYpM0l09W0S0GI=', 'ADMIN'),
 (2, 'organizer1@seatlock.test', 'Olivia Organizer', 'pbkdf2_sha256$600000$seatlockorg1$CcTwUr1vilHM5R6B1x4ejAIO73xFXU389W79R3Z2jJE=', 'ORGANIZER'),
 (3, 'organizer2@seatlock.test', 'Omar Organizer',   'pbkdf2_sha256$600000$seatlockorg2$sfzfqXKgOx6kQes6eVUQp+w9nKmgeO5AHg/79uuCMfI=', 'ORGANIZER');

INSERT INTO users (id, email, full_name, password_hash, role)
SELECT 3 + n, 'student' || n || '@seatlock.test', 'Student ' || n,
       'pbkdf2_sha256$600000$seatlockstu$OhC9sDSU5yyR5hWkRzhI7lgTGibfBJelxrvXx+HnfVg=', 'STUDENT'
FROM generate_series(1, 20) AS n;

INSERT INTO events (id, organizer_id, title, description, venue, starts_at, status) VALUES
 (1, 2, 'Annual Tech Fest Keynote',  'Headline event, numbered seats.', 'Main Auditorium', now() + interval '7 days',  'PUBLISHED'),
 (2, 3, 'Cultural Night',            'Music and dance.',               'Open Air Theatre', now() + interval '10 days', 'PUBLISHED'),
 (3, 2, 'Workshop (draft)',          'Not yet published.',             'Seminar Hall',     now() + interval '14 days', 'DRAFT'),
 (4, 2, 'Past Event (booking closed)', 'Already started; for closure tests.', 'Main Auditorium', now() - interval '1 day', 'PUBLISHED');

-- Seats: events 1, 2, 4 get 6 rows (A-F) x 10 seats; event 3 gets 3 x 10.
INSERT INTO seats (event_id, row_label, seat_number)
SELECT e.id, chr(64 + r), s
FROM (VALUES (1, 6), (2, 6), (3, 3), (4, 6)) AS e(id, rows),
     LATERAL generate_series(1, e.rows) AS r,
     LATERAL generate_series(1, 10) AS s;

-- A few blocked seats (event 1, row F) and one pre-existing booking (student1, event 1, A1-A2).
UPDATE seats SET status = 'BLOCKED'
 WHERE event_id = 1 AND row_label = 'F' AND seat_number IN (1, 2);

INSERT INTO bookings (id, event_id, user_id, status) VALUES (1, 1, 4, 'CONFIRMED');
INSERT INTO booking_seats (booking_id, event_id, seat_id)
SELECT 1, 1, id FROM seats WHERE event_id = 1 AND row_label = 'A' AND seat_number IN (1, 2);
UPDATE seats SET status = 'BOOKED'
 WHERE event_id = 1 AND row_label = 'A' AND seat_number IN (1, 2);

-- Keep sequences ahead of the explicit IDs used above.
SELECT setval('users_id_seq',    (SELECT max(id) FROM users));
SELECT setval('events_id_seq',   (SELECT max(id) FROM events));
SELECT setval('bookings_id_seq', (SELECT max(id) FROM bookings));