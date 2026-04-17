PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK(role IN ('labour', 'contractor', 'client', 'admin')),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS labourers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    skill TEXT NOT NULL,
    phone TEXT NOT NULL,
    location TEXT NOT NULL,
    wage INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('Assigned', 'Available', 'On Leave')),
    contractor_name TEXT NOT NULL,
    client_name TEXT DEFAULT '',
    work_start_date TEXT DEFAULT '',
    work_end_date TEXT DEFAULT '',
    work_start_time TEXT DEFAULT '',
    work_end_time TEXT DEFAULT '',
    last_client_name TEXT DEFAULT '',
    client_review TEXT DEFAULT '',
    labour_username TEXT NOT NULL UNIQUE,
    FOREIGN KEY (labour_username) REFERENCES users(username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    recipient_role TEXT NOT NULL DEFAULT '',
    labour_username TEXT NOT NULL DEFAULT '',
    bill_id INTEGER,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT NOT NULL UNIQUE,
    labour_id INTEGER NOT NULL,
    labour_username TEXT NOT NULL,
    labour_name TEXT NOT NULL,
    contractor_username TEXT NOT NULL DEFAULT '',
    contractor_name TEXT NOT NULL,
    client_username TEXT NOT NULL DEFAULT '',
    client_name TEXT NOT NULL,
    skill TEXT NOT NULL,
    location TEXT NOT NULL,
    wage_per_day INTEGER NOT NULL,
    total_days INTEGER NOT NULL,
    total_amount INTEGER NOT NULL,
    work_start_date TEXT NOT NULL,
    work_end_date TEXT NOT NULL,
    work_start_time TEXT NOT NULL,
    work_end_time TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('Generated', 'Completed')),
    payment_method TEXT NOT NULL DEFAULT '',
    payment_status TEXT NOT NULL DEFAULT 'Pending',
    payment_reference TEXT NOT NULL DEFAULT '',
    review TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT '',
    paid_at TEXT NOT NULL DEFAULT ''
);

INSERT OR IGNORE INTO users (role, username, password_hash, full_name)
VALUES ('contractor', 'contractor1', '1234', 'Rakesh Mehta');

INSERT OR IGNORE INTO users (role, username, password_hash, full_name)
VALUES ('labour', 'labour1', '1234', 'Suresh Kumar');

INSERT OR IGNORE INTO users (role, username, password_hash, full_name)
VALUES ('client', 'client1', '1234', 'Akshar Infra Client');

INSERT OR IGNORE INTO users (role, username, password_hash, full_name)
VALUES ('admin', 'admin1', '1234', 'Portal Admin');

INSERT OR IGNORE INTO labourers
(name, skill, phone, location, wage, status, contractor_name, client_name, work_start_date, work_end_date, work_start_time, work_end_time, last_client_name, client_review, labour_username)
VALUES ('Suresh Kumar', 'Mason', '9876543210', 'Gamdi Site A', 750, 'Assigned', 'Rakesh Buildcon', '', '', '', '', '', '', '', 'labour1');

INSERT OR IGNORE INTO users (role, username, password_hash, full_name)
VALUES ('labour', 'labour2', '1234', 'Arpitbhai Patel');

INSERT OR IGNORE INTO labourers
(name, skill, phone, location, wage, status, contractor_name, client_name, work_start_date, work_end_date, work_start_time, work_end_time, last_client_name, client_review, labour_username)
VALUES ('Arpitbhai Patel', 'Carpenter', '9876543210', 'Gamdi Site B', 800, 'Available', 'Rakesh Buildcon', '', '', '', '', '', '', '', 'labour2');
