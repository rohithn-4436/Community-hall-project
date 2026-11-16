from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for
)
from functools import wraps
import sqlite3
import os
from pathlib import Path
from datetime import datetime, date

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Set the SECRET_KEY environment variable.")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_PASSWORD:
    raise RuntimeError("Set the ADMIN_PASSWORD environment variable.")

DATABASE = Path("instance/community_hall.db")

HALL_CAPACITIES = {
    "Hall A": 300,
    "Hall B": 150,
    "Hall C": 100
}


# DATABASE CONNECTION
def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# DATABASE INITIALIZATION
def initialize_database():
    DATABASE.parent.mkdir(exist_ok=True)

    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                hall TEXT NOT NULL,
                booking_date TEXT NOT NULL,
                guests INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


# ADMIN AUTHENTICATION
def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# HOME PAGE
@app.route("/")
def home():
    return render_template("index.html")


# CREATE BOOKING
@app.route("/bookings", methods=["POST"])
def create_booking():
    data = request.get_json(silent=True) or {}

    required_fields = [
        "full_name", "email", "phone", "hall",
        "date", "guests", "event_type",
        "start_time", "end_time"
    ]

    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    hall = data["hall"]

    if hall not in HALL_CAPACITIES:
        return jsonify({"error": "Invalid hall selected"}), 400

    try:
        booking_date = date.fromisoformat(data["date"])
        start = datetime.strptime(data["start_time"], "%H:%M")
        end = datetime.strptime(data["end_time"], "%H:%M")
        guests = int(data["guests"])
    except (ValueError, TypeError):
        return jsonify({"error": "Please enter valid booking details"}), 400

    if booking_date < date.today():
        return jsonify({"error": "Booking date cannot be in the past"}), 400

    if end <= start:
        return jsonify({"error": "Ending time must be after starting time"}), 400

    if guests < 1 or guests > HALL_CAPACITIES[hall]:
        return jsonify({
            "error": f"{hall} supports up to {HALL_CAPACITIES[hall]} guests"
        }), 400

    with get_db() as db:
        conflict = db.execute("""
            SELECT id FROM bookings
            WHERE hall = ?
            AND booking_date = ?
            AND status IN ('Pending', 'Approved')
            AND start_time < ?
            AND end_time > ?
        """, (
            hall, data["date"], data["end_time"], data["start_time"]
        )).fetchone()

        if conflict:
            return jsonify({
                "error": "This hall already has a booking during that time."
            }), 409

        cursor = db.execute("""
            INSERT INTO bookings (
                full_name, email, phone, hall, booking_date,
                guests, event_type, start_time, end_time, description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["full_name"].strip(),
            data["email"].strip(),
            data["phone"].strip(),
            hall,
            data["date"],
            guests,
            data["event_type"],
            data["start_time"],
            data["end_time"],
            data.get("description", "").strip()
        ))

        booking_id = cursor.lastrowid

    return jsonify({
        "message": "Booking request submitted successfully!",
        "booking_id": booking_id
    }), 201


# ADMIN DASHBOARD
@app.route("/admin")
@admin_required
def admin_dashboard():
    with get_db() as db:
        bookings = db.execute("""
            SELECT * FROM bookings
            ORDER BY created_at DESC
        """).fetchall()

    return render_template("admin.html", bookings=bookings)


# APPROVE OR REJECT BOOKINGS
@app.route("/admin/booking/<int:booking_id>/status", methods=["POST"])
@admin_required
def update_booking_status(booking_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")

    if status not in ["Approved", "Rejected"]:
        return jsonify({"error": "Invalid booking status"}), 400

    with get_db() as db:
        booking = db.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,)
        ).fetchone()

        if booking is None:
            return jsonify({"error": "Booking not found"}), 404

        if status == "Approved":
            conflict = db.execute("""
                SELECT id FROM bookings
                WHERE hall = ?
                AND booking_date = ?
                AND status = 'Approved'
                AND id != ?
                AND start_time < ?
                AND end_time > ?
            """, (
                booking["hall"],
                booking["booking_date"],
                booking_id,
                booking["end_time"],
                booking["start_time"]
            )).fetchone()

            if conflict:
                return jsonify({
                    "error": "Another approved booking conflicts with this request."
                }), 409

        db.execute("""
            UPDATE bookings
            SET status = ?
            WHERE id = ?
        """, (status, booking_id))

    return jsonify({
        "message": f"Booking #{booking_id} {status.lower()} successfully."
    })

@app.route("/check-availability", methods=["GET", "POST"])
def check_availability():
    results = []
    error = None
    selected_hall = ""
    selected_date = ""

    if request.method == "POST":
        selected_hall = request.form.get("hall", "")
        selected_date = request.form.get("date", "")

        if selected_hall not in HALL_CAPACITIES:
            error = "Please select a valid hall."
        else:
            try:
                booking_date = date.fromisoformat(selected_date)

                if booking_date < date.today():
                    error = "Please select today or a future date."
                else:
                    with get_db() as db:
                        results = db.execute("""
                            SELECT start_time, end_time, status
                            FROM bookings
                            WHERE hall = ?
                            AND booking_date = ?
                            AND status IN ('Pending', 'Approved')
                            ORDER BY start_time
                        """, (selected_hall, selected_date)).fetchall()

            except ValueError:
                error = "Please select a valid date."

    return render_template(
        "availability.html",
        results=results,
        error=error,
        today=date.today().isoformat(),
        selected_hall=selected_hall,
        selected_date=selected_date
    )

@app.route("/booking-status", methods=["GET", "POST"])
def booking_status():
    booking = None
    error = None

    if request.method == "POST":
        booking_id = request.form.get("booking_id", "").strip()
        email = request.form.get("email", "").strip()

        if not booking_id or not email:
            error = "Please enter both Booking ID and email."
        else:
            with get_db() as db:
                booking = db.execute("""
                    SELECT id, full_name, email, hall,
                           booking_date, guests, event_type,
                           start_time, end_time, status
                    FROM bookings
                    WHERE id = ? AND email = ?
                """, (booking_id, email)).fetchone()

            if booking is None:
                error = "No booking found. Check your Booking ID and email."

    return render_template(
        "booking_status.html",
        booking=booking,
        error=error
    )

# START APPLICATION
initialize_database()

if __name__ == "__main__":
    app.run(debug=True)
