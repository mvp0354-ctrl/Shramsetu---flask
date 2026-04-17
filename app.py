from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from flask import Flask, flash, g, redirect, render_template, request, session, url_for


BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "shramsetu.db"
SCHEMA_FILE = BASE_DIR / "schema.sql"

app = Flask(__name__)
app.secret_key = "shramsetu-demo-secret-key"
app.permanent_session_lifetime = timedelta(days=30)

DEFAULT_SUMMARY = {
    "labours": 0,
    "locations": 0,
    "contractors": 0,
    "declared_wages": 0,
    "portal_users": 0,
}


def normalize_phone(phone: str) -> str:
    return "".join(char for char in phone if char.isdigit())


def valid_phone(phone: str, *, required: bool) -> bool:
    if not phone:
        return not required
    return len(phone) == 10


def get_connection() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_connection(_exception: BaseException | None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = get_connection().execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_connection().execute(query, params).fetchone()
    return dict(row) if row else None


def execute_query(query: str, params: tuple[Any, ...] = ()) -> None:
    connection = get_connection()
    connection.execute(query, params)
    connection.commit()


def execute_insert(query: str, params: tuple[Any, ...] = ()) -> int:
    connection = get_connection()
    cursor = connection.execute(query, params)
    connection.commit()
    return int(cursor.lastrowid)


def username_exists(username: str) -> bool:
    existing = fetch_one("SELECT id FROM users WHERE username = ?", (username,))
    return existing is not None


def delete_user_by_username(username: str) -> None:
    execute_query("DELETE FROM users WHERE username = ?", (username,))


def initialize_database() -> None:
    connection = get_connection()
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL CHECK(role IN ('labour', 'contractor', 'client', 'admin')),
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS labourers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            skill TEXT NOT NULL,
            phone TEXT NOT NULL,
            location TEXT NOT NULL,
            wage INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Assigned', 'Available', 'On Leave')),
            contractor_name TEXT NOT NULL,
            labour_username TEXT NOT NULL UNIQUE,
            FOREIGN KEY (labour_username) REFERENCES users(username) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
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
        )
        """
    )
    connection.execute(
        """
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
        )
        """
    )

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(labourers)").fetchall()
    }
    if "client_name" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN client_name TEXT DEFAULT ''")
    if "work_start_date" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN work_start_date TEXT DEFAULT ''")
    if "work_end_date" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN work_end_date TEXT DEFAULT ''")
    if "work_start_time" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN work_start_time TEXT DEFAULT ''")
    if "work_end_time" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN work_end_time TEXT DEFAULT ''")
    if "last_client_name" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN last_client_name TEXT DEFAULT ''")
    if "client_review" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN client_review TEXT DEFAULT ''")
    if "leave_start_date" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN leave_start_date TEXT DEFAULT ''")
    if "leave_end_date" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN leave_end_date TEXT DEFAULT ''")
    if "leave_start_time" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN leave_start_time TEXT DEFAULT ''")
    if "leave_end_time" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN leave_end_time TEXT DEFAULT ''")
    if "leave_reason" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN leave_reason TEXT DEFAULT ''")
    if "leave_requested_by" not in columns:
        connection.execute("ALTER TABLE labourers ADD COLUMN leave_requested_by TEXT DEFAULT ''")
    user_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "phone" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")

    bill_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(bills)").fetchall()
    }
    if "payment_method" not in bill_columns:
        connection.execute("ALTER TABLE bills ADD COLUMN payment_method TEXT NOT NULL DEFAULT ''")
    if "payment_status" not in bill_columns:
        connection.execute("ALTER TABLE bills ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Pending'")
    if "payment_reference" not in bill_columns:
        connection.execute("ALTER TABLE bills ADD COLUMN payment_reference TEXT NOT NULL DEFAULT ''")
    if "paid_at" not in bill_columns:
        connection.execute("ALTER TABLE bills ADD COLUMN paid_at TEXT NOT NULL DEFAULT ''")

    connection.execute(
        """
        INSERT OR IGNORE INTO users (role, username, password_hash, full_name, phone)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("contractor", "contractor1", "1234", "Rakesh Buildcon", "9000000000"),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO users (role, username, password_hash, full_name, phone)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("labour", "labour1", "1234", "Suresh Kumar", "9876543210"),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO users (role, username, password_hash, full_name, phone)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("labour", "labour2", "1234", "Anita Devi", "9123456780"),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO users (role, username, password_hash, full_name, phone)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("client", "client1", "1234", "Metro Infra Client", "9011111111"),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO users (role, username, password_hash, full_name, phone)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("admin", "admin1", "1234", "Portal Admin", "9022222222"),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO labourers
        (name, skill, phone, location, wage, status, contractor_name, labour_username, client_name, work_start_date, work_end_date, work_start_time, work_end_time, last_client_name, client_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("Suresh Kumar", "Mason", "9876543210", "Nagpur Site A", 750, "Assigned", "Rakesh Buildcon", "labour1", "", "", "", "", "", "", ""),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO labourers
        (name, skill, phone, location, wage, status, contractor_name, labour_username, client_name, work_start_date, work_end_date, work_start_time, work_end_time, last_client_name, client_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("Anita Devi", "Electrician", "9123456780", "Pune Tower Project", 900, "Available", "Rakesh Buildcon", "labour2", "", "", "", "", "", "", ""),
    )
    connection.commit()
    normalize_labour_statuses()


def parse_end_datetime(date_value: str, time_value: str) -> datetime | None:
    if not date_value:
        return None
    normalized_time = time_value or "23:59"
    try:
        return datetime.strptime(f"{date_value} {normalized_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def normalize_labour_statuses() -> None:
    connection = get_connection()
    now = datetime.now()
    labourers = connection.execute(
        """
        SELECT id, status, work_end_date, work_end_time, leave_end_date, leave_end_time
        FROM labourers
        """
    ).fetchall()

    for labour in labourers:
        if labour["status"] == "Assigned":
            work_end = parse_end_datetime(labour["work_end_date"], labour["work_end_time"])
            if work_end and work_end <= now:
                connection.execute(
                    """
                    UPDATE labourers
                    SET status = 'Available',
                        client_name = '',
                        work_start_date = '',
                        work_end_date = '',
                        work_start_time = '',
                        work_end_time = ''
                    WHERE id = ?
                    """,
                    (labour["id"],),
                )

        if labour["status"] == "On Leave":
            leave_end = parse_end_datetime(labour["leave_end_date"], labour["leave_end_time"])
            if leave_end and leave_end <= now:
                connection.execute(
                    """
                    UPDATE labourers
                    SET status = 'Available',
                        leave_start_date = '',
                        leave_end_date = '',
                        leave_start_time = '',
                        leave_end_time = '',
                        leave_reason = '',
                        leave_requested_by = ''
                    WHERE id = ?
                    """,
                    (labour["id"],),
                )

    connection.commit()


def parse_schedule_datetime(date_value: str, time_value: str) -> datetime | None:
    if not date_value or not time_value:
        return None
    try:
        return datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def calculate_total_days(work_start_date: str, work_end_date: str) -> int | None:
    try:
        start_date = datetime.strptime(work_start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(work_end_date, "%Y-%m-%d").date()
    except ValueError:
        return None

    if end_date < start_date:
        return None
    return (end_date - start_date).days + 1


def generate_bill_number(labour_id: int) -> str:
    return f"BILL-{datetime.now():%Y%m%d%H%M%S%f}-{labour_id}"


def build_upi_link(bill: dict[str, Any]) -> str:
    params = urlencode(
        {
            "pa": "shramsetu.payments@upi",
            "pn": "Shramsetu Portal",
            "tn": f"{bill['bill_number']} {bill['labour_name']}",
            "am": str(bill["total_amount"]),
            "cu": "INR",
        }
    )
    return f"upi://pay?{params}"


def enrich_bills(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["payment_method"] = item.get("payment_method") or "-"
        item["payment_status"] = item.get("payment_status") or "Pending"
        item["payment_reference"] = item.get("payment_reference") or "-"
        item["upi_link"] = build_upi_link(item)
        enriched.append(item)
    return enriched


def create_notification(
    username: str,
    recipient_role: str,
    title: str,
    message: str,
    labour_username: str = "",
    bill_id: int | None = None,
) -> None:
    execute_query(
        """
        INSERT INTO notifications (username, recipient_role, labour_username, bill_id, title, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (username, recipient_role, labour_username, bill_id, title, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def notify_bill_payment(
    bill: dict[str, Any],
    payment_method: str,
    payment_reference: str,
) -> None:
    message = (
        f"Payment recorded for bill {bill['bill_number']} via {payment_method}. "
        f"Amount: Rs. {bill['total_amount']}."
    )
    if payment_reference:
        message = f"{message} Reference: {payment_reference}."

    create_notification(
        bill["client_username"],
        "client",
        "Bill payment recorded",
        message,
        bill["labour_username"],
    )
    create_notification(
        bill["labour_username"],
        "labour",
        "Payment update",
        f"{message} Labour: {bill['labour_name']}.",
        bill["labour_username"],
    )
    if bill["contractor_username"]:
        create_notification(
            bill["contractor_username"],
            "contractor",
            "Client payment recorded",
            f"{message} Client: {bill['client_name']}.",
            bill["labour_username"],
        )


def notifications_for_user(username: str) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT title, message, created_at
        FROM notifications
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 15
        """,
        (username,),
    )


def contractor_account(contractor_name: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT username, role, full_name
        FROM users
        WHERE role = 'contractor' AND full_name = ?
        """,
        (contractor_name,),
    )


def labour_bills(labour_username: str) -> list[dict[str, Any]]:
    return enrich_bills(fetch_all(
        """
        SELECT bill_number, labour_name, contractor_name, client_name, skill, location,
               wage_per_day, total_days, total_amount, work_start_date, work_end_date,
               work_start_time, work_end_time, status, payment_method, payment_status,
               payment_reference, review, created_at, completed_at, paid_at
        FROM bills
        WHERE labour_username = ?
        ORDER BY id DESC
        """,
        (labour_username,),
    ))


def contractor_bills(contractor_name: str) -> list[dict[str, Any]]:
    return enrich_bills(fetch_all(
        """
        SELECT bill_number, labour_name, contractor_name, client_name, skill, location,
               wage_per_day, total_days, total_amount, work_start_date, work_end_date,
               work_start_time, work_end_time, status, payment_method, payment_status,
               payment_reference, review, created_at, completed_at, paid_at
        FROM bills
        WHERE contractor_name = ?
        ORDER BY id DESC
        """,
        (contractor_name,),
    ))


def client_bills(client_name: str) -> list[dict[str, Any]]:
    return enrich_bills(fetch_all(
        """
        SELECT bill_number, labour_name, contractor_name, client_name, skill, location,
               wage_per_day, total_days, total_amount, work_start_date, work_end_date,
               work_start_time, work_end_time, status, payment_method, payment_status,
               payment_reference, review, created_at, completed_at, paid_at
        FROM bills
        WHERE client_name = ?
        ORDER BY id DESC
        """,
        (client_name,),
    ))


def all_bills() -> list[dict[str, Any]]:
    return enrich_bills(fetch_all(
        """
        SELECT bill_number, labour_name, contractor_name, client_name, skill, location,
               wage_per_day, total_days, total_amount, work_start_date, work_end_date,
               work_start_time, work_end_time, status, payment_method, payment_status,
               payment_reference, review, created_at, completed_at, paid_at
        FROM bills
        ORDER BY id DESC
        """
    ))


def current_user() -> dict[str, Any] | None:
    username = session.get("username")
    role = session.get("role")
    if not username or not role:
        return None

    return fetch_one(
        """
        SELECT id, role, username, full_name AS name, phone
        FROM users
        WHERE username = ? AND role = ?
        """,
        (username, role),
    )


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user():
            flash("Please login first.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped_view


def role_required(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user = current_user()
            if not user or user["role"] not in roles:
                flash("You do not have permission to access that page.", "error")
                return redirect(url_for("index"))
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def build_summary() -> dict[str, int]:
    summary = fetch_one(
        """
        SELECT
            COUNT(*) AS labours,
            COUNT(DISTINCT location) AS locations,
            COUNT(DISTINCT contractor_name) AS contractors,
            COALESCE(SUM(wage), 0) AS declared_wages
        FROM labourers
        """
    ) or {}
    user_count = fetch_one("SELECT COUNT(*) AS portal_users FROM users") or {}

    return {
        "labours": int(summary.get("labours", 0)),
        "locations": int(summary.get("locations", 0)),
        "contractors": int(summary.get("contractors", 0)),
        "declared_wages": int(summary.get("declared_wages", 0)),
        "portal_users": int(user_count.get("portal_users", 0)),
    }


def contractor_labourers(contractor_name: str) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT name, skill, phone, location, wage, status, labour_username,
               client_name, work_start_date, work_end_date, work_start_time, work_end_time,
               leave_start_date, leave_end_date, leave_start_time, leave_end_time,
               leave_reason, leave_requested_by
        FROM labourers
        WHERE contractor_name = ?
        ORDER BY id DESC
        """,
        (contractor_name,),
    )


def location_overview() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            location,
            COUNT(*) AS workers,
            GROUP_CONCAT(DISTINCT skill) AS skills,
            ROUND(AVG(wage)) AS average_wage,
            GROUP_CONCAT(DISTINCT contractor_name) AS contractors
        FROM labourers
        GROUP BY location
        ORDER BY location
        """
    )


def available_labourers() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, name, skill, phone, location, wage, status, contractor_name AS contractor
        FROM labourers
        WHERE status = 'Available'
        ORDER BY location, name
        """
    )


def client_hires(client_name: str) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, name, skill, phone, location, wage, contractor_name AS contractor,
               work_start_date, work_end_date, work_start_time, work_end_time
        FROM labourers
        WHERE client_name = ?
        ORDER BY id DESC
        """,
        (client_name,),
    )


def admin_metrics() -> dict[str, int]:
    summary = fetch_one(
        """
        SELECT
            COUNT(*) AS total_labourers,
            COUNT(DISTINCT contractor_name) AS contractors,
            COUNT(DISTINCT location) AS locations,
            COALESCE(SUM(wage), 0) AS daily_wage_sum,
            COALESCE(SUM(CASE WHEN status = 'Assigned' THEN 1 ELSE 0 END), 0) AS assigned_workers
        FROM labourers
        """
    ) or {}
    users = fetch_one("SELECT COUNT(*) AS portal_users FROM users") or {}

    return {
        "Total Labourers": int(summary.get("total_labourers", 0)),
        "Contractors": int(summary.get("contractors", 0)),
        "Locations": int(summary.get("locations", 0)),
        "Daily Wage Sum": int(summary.get("daily_wage_sum", 0)),
        "Assigned Workers": int(summary.get("assigned_workers", 0)),
        "Portal Users": int(users.get("portal_users", 0)),
    }


def labour_record(username: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT name, skill, phone, location, wage, status, contractor_name AS contractor, client_name
             , work_start_date, work_end_date, work_start_time, work_end_time
             , last_client_name, client_review
             , leave_start_date, leave_end_date, leave_start_time, leave_end_time
             , leave_reason, leave_requested_by
        FROM labourers
        WHERE labour_username = ?
        """,
        (username,),
    )


def all_labourers() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT name, contractor_name AS contractor, client_name, labour_username, location, skill, wage, status,
               work_start_date, work_end_date, work_start_time, work_end_time,
               last_client_name, client_review,
               leave_start_date, leave_end_date, leave_start_time, leave_end_time,
               leave_reason, leave_requested_by
        FROM labourers
        ORDER BY id DESC
        """
    )


def all_contractors() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT full_name AS company_name, username
        FROM users
        WHERE role = 'contractor'
        ORDER BY full_name
        """
    )


def demo_users() -> list[dict[str, Any]]:
    users = fetch_all(
        """
        SELECT role, username, password_hash AS password
        FROM users
        WHERE role != 'labour' OR username = 'labour1'
        """
    )
    role_order = {"contractor": 0, "labour": 1, "client": 2, "admin": 3}
    return sorted(users, key=lambda item: role_order.get(item["role"], 99))


def slugify(value: str) -> str:
    cleaned = "".join(char.lower() for char in value if char.isalnum())
    return cleaned or "labour"


def create_labour_profile(name: str, username: str, contractor_name: str = "") -> None:
    user = fetch_one("SELECT phone FROM users WHERE username = ?", (username,)) or {}
    execute_query(
        """
        INSERT OR IGNORE INTO labourers
        (name, skill, phone, location, wage, status, contractor_name, labour_username,
         client_name, work_start_date, work_end_date, work_start_time, work_end_time,
         last_client_name, client_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            "Not Assigned",
            user.get("phone", "") or "Not Provided",
            "Not Assigned",
            0,
            "Available",
            contractor_name or "Self Registered",
            username,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ),
    )


@app.context_processor
def inject_defaults() -> dict[str, Any]:
    return {"summary": DEFAULT_SUMMARY}


@app.route("/", methods=["GET", "POST"])
def index():
    initialize_database()
    user = current_user()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        remember_me = request.form.get("remember_me") == "on"

        matched_user = fetch_one(
            """
        SELECT id, role, username, full_name AS name
            FROM users
            WHERE username = ? AND password_hash = ?
            """,
            (username, password),
        )

        if matched_user:
            session.permanent = remember_me
            session["username"] = matched_user["username"]
            session["role"] = matched_user["role"]
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid login. Please use a valid demo account.", "error")

    return render_template(
        "index.html",
        summary=build_summary(),
        demo_users=demo_users(),
        user=user,
    )


@app.route("/signup", methods=["POST"])
def signup():
    initialize_database()

    role = request.form.get("role", "").strip()
    full_name = request.form.get("full_name", "").strip()
    company_name = request.form.get("company_name", "").strip()
    phone = normalize_phone(request.form.get("phone", "").strip())
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if role not in {"labour", "contractor", "client"}:
        flash("Please choose a valid role for signup.", "error")
        return redirect(url_for("index"))

    if not all([full_name, username, password, confirm_password]):
        flash("Please fill all signup fields.", "error")
        return redirect(url_for("index"))

    if not valid_phone(phone, required=False):
        flash("Mobile number must be exactly 10 digits.", "error")
        return redirect(url_for("index"))

    if role == "contractor" and not company_name:
        flash("Please enter contractor name for contractor signup.", "error")
        return redirect(url_for("index"))

    if password != confirm_password:
        flash("Password and confirm password do not match.", "error")
        return redirect(url_for("index"))

    if username_exists(username):
        flash("That username is already taken. Please choose another one.", "error")
        return redirect(url_for("index"))

    execute_query(
        """
        INSERT INTO users (role, username, password_hash, full_name, phone)
        VALUES (?, ?, ?, ?, ?)
        """,
        (role, username, password, company_name if role == "contractor" else full_name, phone),
    )

    if role == "labour":
        create_labour_profile(full_name, username, company_name)

    flash("Signup successful. You can login with your new account now.", "success")
    return redirect(url_for("index"))


@app.route("/change-password", methods=["POST"])
@login_required
def change_password():
    initialize_database()
    user = current_user()
    assert user is not None

    current_password = request.form.get("current_password", "").strip()
    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not all([current_password, new_password, confirm_password]):
        flash("Please fill all password fields.", "error")
        return redirect(url_for("dashboard"))

    if new_password != confirm_password:
        flash("New password and confirm password do not match.", "error")
        return redirect(url_for("dashboard"))

    matched_user = fetch_one(
        """
        SELECT id
        FROM users
        WHERE username = ? AND password_hash = ?
        """,
        (user["username"], current_password),
    )
    if not matched_user:
        flash("Current password is incorrect.", "error")
        return redirect(url_for("dashboard"))

    execute_query(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (new_password, user["username"]),
    )
    flash("Password changed successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/profile/update", methods=["POST"])
@login_required
def update_profile():
    initialize_database()
    user = current_user()
    assert user is not None

    full_name = request.form.get("full_name", "").strip()
    phone = normalize_phone(request.form.get("phone", "").strip())

    if not full_name:
        flash("Profile name cannot be empty.", "error")
        return redirect(url_for("dashboard"))

    if not valid_phone(phone, required=False):
        flash("Mobile number must be exactly 10 digits.", "error")
        return redirect(url_for("dashboard"))

    old_name = user["name"]
    execute_query(
        "UPDATE users SET full_name = ?, phone = ? WHERE username = ?",
        (full_name, phone, user["username"]),
    )

    if user["role"] == "contractor":
        execute_query(
            "UPDATE labourers SET contractor_name = ? WHERE contractor_name = ?",
            (full_name, old_name),
        )
    elif user["role"] == "client":
        execute_query(
            "UPDATE labourers SET client_name = ? WHERE client_name = ?",
            (full_name, old_name),
        )
        execute_query(
            "UPDATE labourers SET last_client_name = ? WHERE last_client_name = ?",
            (full_name, old_name),
        )
    elif user["role"] == "labour":
        execute_query(
            "UPDATE labourers SET name = ?, phone = ? WHERE labour_username = ?",
            (full_name, phone or "Not Provided", user["username"]),
        )

    flash("Profile updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/contractor/labour/delete/<labour_username>", methods=["POST"])
@login_required
@role_required("contractor")
def delete_contractor_labour(labour_username: str):
    initialize_database()
    user = current_user()
    assert user is not None

    labour = fetch_one(
        """
        SELECT id, name
        FROM labourers
        WHERE labour_username = ? AND contractor_name = ?
        """,
        (labour_username, user["name"]),
    )
    if not labour:
        flash("That labour record does not belong to this contractor.", "error")
        return redirect(url_for("dashboard"))

    execute_query("DELETE FROM labourers WHERE labour_username = ?", (labour_username,))
    delete_user_by_username(labour_username)
    flash(f"{labour['name']} was deleted successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/contractor/labour/update/<labour_username>", methods=["POST"])
@login_required
@role_required("contractor")
def update_contractor_labour(labour_username: str):
    initialize_database()
    user = current_user()
    assert user is not None

    labour = fetch_one(
        """
        SELECT name
        FROM labourers
        WHERE labour_username = ? AND contractor_name = ?
        """,
        (labour_username, user["name"]),
    )
    if not labour:
        flash("That labour record does not belong to this contractor.", "error")
        return redirect(url_for("dashboard"))

    name = request.form.get("name", "").strip()
    skill = request.form.get("skill", "").strip()
    phone = normalize_phone(request.form.get("phone", "").strip())
    location = request.form.get("location", "").strip()
    wage_raw = request.form.get("wage", "").strip()
    status = request.form.get("status", "").strip()
    client_name = request.form.get("client_name", "").strip()
    work_start_date = request.form.get("work_start_date", "").strip()
    work_end_date = request.form.get("work_end_date", "").strip()
    work_start_time = request.form.get("work_start_time", "").strip()
    work_end_time = request.form.get("work_end_time", "").strip()
    leave_start_date = request.form.get("leave_start_date", "").strip()
    leave_end_date = request.form.get("leave_end_date", "").strip()
    leave_start_time = request.form.get("leave_start_time", "").strip()
    leave_end_time = request.form.get("leave_end_time", "").strip()
    leave_reason = request.form.get("leave_reason", "").strip()

    if not all([name, skill, phone, location, wage_raw, status]):
        flash("Please fill all labour edit fields.", "error")
        return redirect(url_for("dashboard"))

    if not valid_phone(phone, required=True):
        flash("Phone number must be exactly 10 digits.", "error")
        return redirect(url_for("dashboard"))

    try:
        wage = int(wage_raw)
    except ValueError:
        flash("Wage must be a number.", "error")
        return redirect(url_for("dashboard"))

    if status == "Assigned":
        execute_query(
            """
            UPDATE labourers
            SET name = ?, skill = ?, phone = ?, location = ?, wage = ?, status = ?,
                client_name = ?, work_start_date = ?, work_end_date = ?, work_start_time = ?,
                work_end_time = ?, leave_start_date = '', leave_end_date = '', leave_start_time = '',
                leave_end_time = '', leave_reason = '', leave_requested_by = ''
            WHERE labour_username = ?
            """,
            (
                name, skill, phone, location, wage, status, client_name,
                work_start_date, work_end_date, work_start_time, work_end_time,
                labour_username,
            ),
        )
    elif status == "On Leave":
        execute_query(
            """
            UPDATE labourers
            SET name = ?, skill = ?, phone = ?, location = ?, wage = ?, status = ?,
                client_name = '', work_start_date = '', work_end_date = '', work_start_time = '',
                work_end_time = '', leave_start_date = ?, leave_end_date = ?, leave_start_time = ?,
                leave_end_time = ?, leave_reason = ?, leave_requested_by = 'Contractor'
            WHERE labour_username = ?
            """,
            (
                name, skill, phone, location, wage, status,
                leave_start_date, leave_end_date, leave_start_time, leave_end_time, leave_reason,
                labour_username,
            ),
        )
    else:
        execute_query(
            """
            UPDATE labourers
            SET name = ?, skill = ?, phone = ?, location = ?, wage = ?, status = 'Available',
                client_name = '', work_start_date = '', work_end_date = '', work_start_time = '',
                work_end_time = '', leave_start_date = '', leave_end_date = '', leave_start_time = '',
                leave_end_time = '', leave_reason = '', leave_requested_by = ''
            WHERE labour_username = ?
            """,
            (name, skill, phone, location, wage, labour_username),
        )
    execute_query(
        "UPDATE users SET full_name = ? WHERE username = ? AND role = 'labour'",
        (name, labour_username),
    )

    flash(f"{name} was updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/labour/leave", methods=["POST"])
@login_required
@role_required("labour")
def labour_leave():
    initialize_database()
    user = current_user()
    assert user is not None

    leave_start_date = request.form.get("leave_start_date", "").strip()
    leave_end_date = request.form.get("leave_end_date", "").strip()
    leave_start_time = request.form.get("leave_start_time", "").strip()
    leave_end_time = request.form.get("leave_end_time", "").strip()
    leave_reason = request.form.get("leave_reason", "").strip()

    if not all([leave_start_date, leave_end_date, leave_reason]):
        flash("Please fill leave dates and reason.", "error")
        return redirect(url_for("dashboard"))

    execute_query(
        """
        UPDATE labourers
        SET status = 'On Leave',
            client_name = '',
            work_start_date = '',
            work_end_date = '',
            work_start_time = '',
            work_end_time = '',
            leave_start_date = ?,
            leave_end_date = ?,
            leave_start_time = ?,
            leave_end_time = ?,
            leave_reason = ?,
            leave_requested_by = 'Labour'
        WHERE labour_username = ?
        """,
        (
            leave_start_date, leave_end_date, leave_start_time,
            leave_end_time, leave_reason, user["username"],
        ),
    )

    flash("Leave details submitted successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/labour/delete/<labour_username>", methods=["POST"])
@login_required
@role_required("admin")
def delete_admin_labour(labour_username: str):
    initialize_database()
    labour = fetch_one(
        "SELECT name FROM labourers WHERE labour_username = ?",
        (labour_username,),
    )
    if not labour:
        flash("Labour record not found.", "error")
        return redirect(url_for("dashboard"))

    execute_query("DELETE FROM labourers WHERE labour_username = ?", (labour_username,))
    delete_user_by_username(labour_username)
    flash(f"{labour['name']} was deleted by admin.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/contractor/delete/<contractor_username>", methods=["POST"])
@login_required
@role_required("admin")
def delete_admin_contractor(contractor_username: str):
    initialize_database()
    user = current_user()
    assert user is not None

    if contractor_username == user["username"]:
        flash("Admin cannot delete the currently logged in admin account as a contractor.", "error")
        return redirect(url_for("dashboard"))

    contractor = fetch_one(
        """
        SELECT username, full_name
        FROM users
        WHERE username = ? AND role = 'contractor'
        """,
        (contractor_username,),
    )
    if not contractor:
        flash("Contractor account not found.", "error")
        return redirect(url_for("dashboard"))

    labour_usernames = fetch_all(
        "SELECT labour_username FROM labourers WHERE contractor_name = ?",
        (contractor["full_name"],),
    )
    for labour in labour_usernames:
        execute_query("DELETE FROM labourers WHERE labour_username = ?", (labour["labour_username"],))
        delete_user_by_username(labour["labour_username"])

    delete_user_by_username(contractor_username)
    flash(f"{contractor['full_name']} and linked labour records were deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    initialize_database()
    user = current_user()
    assert user is not None

    context: dict[str, Any] = {
        "summary": build_summary(),
        "user": user,
        "notifications": notifications_for_user(user["username"]),
    }

    if user["role"] == "contractor":
        context["labourers"] = contractor_labourers(user["name"])
        context["bills"] = contractor_bills(user["name"])
        return render_template("dashboard_contractor.html", **context)

    if user["role"] == "labour":
        context["labour_record"] = labour_record(user["username"])
        context["bills"] = labour_bills(user["username"])
        return render_template("dashboard_labour.html", **context)

    if user["role"] == "client":
        context["locations"] = location_overview()
        context["available_labourers"] = available_labourers()
        context["hired_labourers"] = client_hires(user["name"])
        context["bills"] = client_bills(user["name"])
        return render_template("dashboard_client.html", **context)

    context["metrics"] = admin_metrics()
    context["labourers"] = all_labourers()
    context["contractors"] = all_contractors()
    context["bills"] = all_bills()
    return render_template("dashboard_admin.html", **context)


@app.route("/contractor/labour/add", methods=["POST"])
@login_required
@role_required("contractor")
def add_labour():
    initialize_database()
    user = current_user()
    assert user is not None

    name = request.form.get("name", "").strip()
    skill = request.form.get("skill", "").strip()
    phone = normalize_phone(request.form.get("phone", "").strip())
    location = request.form.get("location", "").strip()
    wage_raw = request.form.get("wage", "").strip()
    status = request.form.get("status", "").strip()

    if not all([name, skill, phone, location, wage_raw, status]):
        flash("Please fill all labour form fields.", "error")
        return redirect(url_for("dashboard"))

    if not valid_phone(phone, required=True):
        flash("Phone number must be exactly 10 digits.", "error")
        return redirect(url_for("dashboard"))

    try:
        wage = int(wage_raw)
    except ValueError:
        flash("Wage must be a number.", "error")
        return redirect(url_for("dashboard"))

    next_id_row = fetch_one("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM labourers")
    next_id = int(next_id_row["next_id"]) if next_id_row else 1
    labour_username = f"{slugify(name)}{next_id}"

    execute_query(
        """
        INSERT INTO users (role, username, password_hash, full_name)
        VALUES (?, ?, ?, ?)
        """,
        ("labour", labour_username, "1234", name),
    )
    execute_query(
        """
        INSERT INTO labourers
        (name, skill, phone, location, wage, status, contractor_name, labour_username, client_name, work_start_date, work_end_date, work_start_time, work_end_time, last_client_name, client_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (name, skill, phone, location, wage, status, user["name"], labour_username, "", "", "", "", "", "", ""),
    )

    flash(f"Labour added successfully. New labour login: {labour_username} / 1234", "success")
    return redirect(url_for("dashboard"))


@app.route("/client/hire/<int:labour_id>", methods=["POST"])
@login_required
@role_required("client")
def hire_labour(labour_id: int):
    initialize_database()
    user = current_user()
    assert user is not None

    labour = fetch_one(
        """
        SELECT id, name, status, skill, location, wage, contractor_name, labour_username
        FROM labourers
        WHERE id = ?
        """,
        (labour_id,),
    )

    if not labour:
        flash("Selected labour record was not found.", "error")
        return redirect(url_for("dashboard"))

    if labour["status"] != "Available":
        flash("This labour is no longer available to hire.", "error")
        return redirect(url_for("dashboard"))

    work_start_date = request.form.get("work_start_date", "").strip()
    work_end_date = request.form.get("work_end_date", "").strip()
    work_start_time = request.form.get("work_start_time", "").strip()
    work_end_time = request.form.get("work_end_time", "").strip()

    if not all([work_start_date, work_end_date, work_start_time, work_end_time]):
        flash("Please select work start/end dates and times before buying labour.", "error")
        return redirect(url_for("dashboard"))

    work_start_at = parse_schedule_datetime(work_start_date, work_start_time)
    work_end_at = parse_schedule_datetime(work_end_date, work_end_time)
    total_days = calculate_total_days(work_start_date, work_end_date)

    if not work_start_at or not work_end_at or total_days is None or work_end_at < work_start_at:
        flash("Please select a valid work date and time range.", "error")
        return redirect(url_for("dashboard"))

    total_amount = int(labour["wage"]) * total_days

    execute_query(
        """
        UPDATE labourers
        SET status = ?, client_name = ?, work_start_date = ?, work_end_date = ?,
            work_start_time = ?, work_end_time = ?, last_client_name = ?, client_review = ''
        WHERE id = ?
        """,
        ("Assigned", user["name"], work_start_date, work_end_date, work_start_time, work_end_time, user["name"], labour_id),
    )

    contractor = contractor_account(labour["contractor_name"])
    bill_number = generate_bill_number(labour_id)
    bill_id = execute_insert(
        """
        INSERT INTO bills (
            bill_number, labour_id, labour_username, labour_name, contractor_username, contractor_name,
            client_username, client_name, skill, location, wage_per_day, total_days, total_amount,
            work_start_date, work_end_date, work_start_time, work_end_time, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bill_number,
            labour_id,
            labour["labour_username"],
            labour["name"],
            contractor["username"] if contractor else "",
            labour["contractor_name"],
            user["username"],
            user["name"],
            labour["skill"],
            labour["location"],
            int(labour["wage"]),
            total_days,
            total_amount,
            work_start_date,
            work_end_date,
            work_start_time,
            work_end_time,
            "Generated",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

    notification_message = (
        f"Bill generated for {labour['name']} from {work_start_date} {work_start_time} "
        f"to {work_end_date} {work_end_time}. Total amount: Rs. {total_amount}."
    )
    create_notification(
        user["username"],
        user["role"],
        "Labour hire confirmed",
        notification_message,
        labour["labour_username"],
        bill_id,
    )
    create_notification(
        labour["labour_username"],
        "labour",
        "New work assignment",
        f"You have been hired by {user['name']} for {labour['location']}. {notification_message}",
        labour["labour_username"],
        bill_id,
    )
    if contractor:
        create_notification(
            contractor["username"],
            contractor["role"],
            "Labour hired by client",
            f"{labour['name']} has been hired by {user['name']}. {notification_message}",
            labour["labour_username"],
            bill_id,
        )

    flash(f"{labour['name']} has been hired successfully and bill {bill_number} was generated.", "success")
    return redirect(url_for("dashboard"))


@app.route("/client/bill/pay/<bill_number>", methods=["POST"])
@login_required
@role_required("client")
def pay_bill(bill_number: str):
    initialize_database()
    user = current_user()
    assert user is not None

    bill = fetch_one(
        """
        SELECT bill_number, labour_id, labour_username, labour_name, contractor_username, contractor_name,
               client_username, client_name, total_amount, payment_status
        FROM bills
        WHERE bill_number = ? AND client_username = ?
        """,
        (bill_number, user["username"]),
    )

    if not bill:
        flash("Bill record was not found for this client account.", "error")
        return redirect(url_for("dashboard"))

    if bill["payment_status"] == "Paid":
        flash("This bill is already marked as paid.", "error")
        return redirect(url_for("dashboard"))

    payment_method = request.form.get("payment_method", "").strip()
    payment_reference = request.form.get("payment_reference", "").strip()
    valid_methods = {"UPI", "Net Banking", "Debit/Credit Card", "Cash on Field"}

    if payment_method not in valid_methods:
        flash("Please choose a valid payment method.", "error")
        return redirect(url_for("dashboard"))

    if payment_method in {"Net Banking", "Debit/Credit Card"} and not payment_reference:
        flash("Please enter a payment reference for the selected payment method.", "error")
        return redirect(url_for("dashboard"))

    if payment_method == "UPI" and not payment_reference:
        payment_reference = "UPI_APP"

    if payment_method == "Cash on Field" and not payment_reference:
        payment_reference = "CASH_ON_FIELD"

    execute_query(
        """
        UPDATE bills
        SET payment_method = ?, payment_status = 'Paid', payment_reference = ?, paid_at = ?
        WHERE bill_number = ?
        """,
        (payment_method, payment_reference, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bill_number),
    )

    updated_bill = dict(bill)
    updated_bill["payment_reference"] = payment_reference
    notify_bill_payment(updated_bill, payment_method, payment_reference)

    if payment_method == "UPI":
        return redirect(build_upi_link(updated_bill))

    flash(f"Payment for bill {bill_number} was recorded via {payment_method}.", "success")
    return redirect(url_for("dashboard"))


@app.route("/client/complete/<int:labour_id>", methods=["POST"])
@login_required
@role_required("client")
def complete_labour(labour_id: int):
    initialize_database()
    user = current_user()
    assert user is not None

    review = request.form.get("review", "").strip()
    labour = fetch_one(
        """
        SELECT id, name, client_name
        FROM labourers
        WHERE id = ?
        """,
        (labour_id,),
    )

    if not labour or labour["client_name"] != user["name"]:
        flash("This labour is not assigned to your client account.", "error")
        return redirect(url_for("dashboard"))

    execute_query(
        """
        UPDATE labourers
        SET status = ?, client_name = '', work_start_date = '', work_end_date = '',
            work_start_time = '', work_end_time = '', last_client_name = ?, client_review = ?
        WHERE id = ?
        """,
        ("Available", user["name"], review, labour_id),
    )

    execute_query(
        """
        UPDATE bills
        SET status = 'Completed', review = ?, completed_at = ?
        WHERE labour_id = ? AND client_username = ? AND status = 'Generated'
        """,
        (review, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), labour_id, user["username"]),
    )

    flash(f"Work completed for {labour['name']}. Review saved and labour is available again.", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    with app.app_context():
      initialize_database()
    app.run(debug=True, host="0.0.0.0", port=5000)
