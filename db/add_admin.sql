-- Creates (or updates) the admin account. Safe to run more than once.
INSERT INTO users (email, full_name, password_hash, role)
VALUES ('mohitparkash1@gmail.com', 'Mohit Prakash', 'pbkdf2_sha256$1000000$YlofWoKqpD7rWgjJ930EgL$yfp3D9Viwxq8aaWLAEdOWrZ+sioIXQfC9+oDZw2r/tQ=', 'ADMIN')
ON CONFLICT (email) DO UPDATE
SET full_name = EXCLUDED.full_name,
    password_hash = EXCLUDED.password_hash,
    role = 'ADMIN',
    is_active = TRUE;
