import csv
from io import StringIO
from flask import (
    Flask, Response, render_template, request, jsonify,
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
        # Existing bookings table
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

        # New maintenance table
        db.execute("""
            CREATE TABLE IF NOT EXISTS maintenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hall TEXT NOT NULL,
                maintenance_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'Scheduled',
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

        # Check scheduled maintenance
        maintenance_conflict = db.execute("""
            SELECT id FROM maintenance
            WHERE hall = ?
            AND maintenance_date = ?
            AND status = 'Scheduled'
            AND start_time < ?
            AND end_time > ?
        """, (
            hall, data["date"], data["end_time"], data["start_time"]
        )).fetchone()

        if maintenance_conflict:
            return jsonify({
                "error": "This hall is unavailable due to scheduled maintenance during that time."
            }), 409

        # Check existing bookings
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

        # Save booking
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
        # Existing booking records
        bookings = db.execute("""
            SELECT * FROM bookings
            ORDER BY created_at DESC
        """).fetchall()

        # Total maintenance records
        total_maintenance = db.execute("""
            SELECT COUNT(*) FROM maintenance
        """).fetchone()[0]

        # Scheduled maintenance records
        scheduled_maintenance = db.execute("""
            SELECT COUNT(*) FROM maintenance
            WHERE status = 'Scheduled'
        """).fetchone()[0]

        hall_stats = [
            dict(row) for row in db.execute("""
                SELECT hall, COUNT(*) AS total
                FROM bookings
                GROUP BY hall
                ORDER BY total DESC
            """).fetchall()
        ]

        monthly_stats = [
            dict(row) for row in db.execute("""
                SELECT
                    strftime('%Y-%m', booking_date) AS month,
                    COUNT(*) AS total
                FROM bookings
                GROUP BY month
                ORDER BY month
            """).fetchall()
        ]

        status_stats = [
            dict(row) for row in db.execute("""
                SELECT status, COUNT(*) AS total
                FROM bookings
                GROUP BY status
            """).fetchall()
        ]

    return render_template(
        "admin.html",
        bookings=bookings,
        total_maintenance=total_maintenance,
        scheduled_maintenance=scheduled_maintenance,
        hall_stats=hall_stats,
        monthly_stats=monthly_stats,
        status_stats=status_stats
    )

@app.route("/admin/download-report")
@admin_required
def download_report():
    output = StringIO()
    writer = csv.writer(output)

    # CSV column headings
    writer.writerow([
        "Booking ID",
        "Customer Name",
        "Email",
        "Phone",
        "Hall",
        "Booking Date",
        "Guests",
        "Event Type",
        "Start Time",
        "End Time",
        "Status"
    ])

    with get_db() as db:
        bookings = db.execute("""
            SELECT * FROM bookings
            ORDER BY booking_date DESC
        """).fetchall()

        for booking in bookings:
            writer.writerow([
                booking["id"],
                booking["full_name"],
                booking["email"],
                booking["phone"],
                booking["hall"],
                booking["booking_date"],
                booking["guests"],
                booking["event_type"],
                booking["start_time"],
                booking["end_time"],
                booking["status"]
            ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=community_hall_bookings.csv"
    )

    return response

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
    start_time = ""
    end_time = ""

    if request.method == "POST":
        selected_hall = request.form.get("hall", "")
        selected_date = request.form.get("date", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")

        if selected_hall not in HALL_CAPACITIES:
            error = "Please select a valid hall."

        else:
            try:
                booking_date = date.fromisoformat(selected_date)

                datetime.strptime(start_time, "%H:%M")
                datetime.strptime(end_time, "%H:%M")

                if booking_date < date.today():
                    error = "Please select today or a future date."

                elif end_time <= start_time:
                    error = "Ending time must be after starting time."

                else:
                    with get_db() as db:
                        results = db.execute("""
                            SELECT start_time, end_time, status
                            FROM bookings
                            WHERE hall = ?
                            AND booking_date = ?
                            AND status IN ('Pending', 'Approved')
                            AND start_time < ?
                            AND end_time > ?
                            ORDER BY start_time
                        """, (
                            selected_hall,
                            selected_date,
                            end_time,
                            start_time
                        )).fetchall()

            except ValueError:
                error = "Please enter valid date and time details."

    return render_template(
        "availability.html",
        results=results,
        error=error,
        selected_hall=selected_hall,
        selected_date=selected_date,
        start_time=start_time,
        end_time=end_time,
        today=date.today().isoformat()
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

@app.route("/admin/maintenance", methods=["GET", "POST"])
@admin_required
def maintenance():
    error = None

    if request.method == "POST":
        hall = request.form.get("hall", "")
        maintenance_date = request.form.get("maintenance_date", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")
        description = request.form.get("description", "").strip()

        try:
            selected_date = date.fromisoformat(maintenance_date)
            datetime.strptime(start_time, "%H:%M")
            datetime.strptime(end_time, "%H:%M")

            if hall not in HALL_CAPACITIES:
                error = "Please select a valid hall."
            elif selected_date < date.today():
                error = "Maintenance date cannot be in the past."
            elif end_time <= start_time:
                error = "End time must be after start time."
            elif not description:
                error = "Please enter a description."
            else:
                with get_db() as db:
                    conflict = db.execute("""
                        SELECT id FROM maintenance
                        WHERE hall = ?
                        AND maintenance_date = ?
                        AND status = 'Scheduled'
                        AND start_time < ?
                        AND end_time > ?
                    """, (
                        hall, maintenance_date, end_time, start_time
                    )).fetchone()

                    if conflict:
                        error = "Another maintenance schedule overlaps this time."
                    else:
                        db.execute("""
                            INSERT INTO maintenance
                            (hall, maintenance_date, start_time,
                             end_time, description)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            hall, maintenance_date, start_time,
                            end_time, description
                        ))

        except ValueError:
            error = "Please enter valid date and time details."

    with get_db() as db:
        maintenance_records = db.execute("""
            SELECT * FROM maintenance
            ORDER BY maintenance_date, start_time
        """).fetchall()

    return render_template(
        "maintenance.html",
        halls=HALL_CAPACITIES.keys(),
        maintenance_records=maintenance_records,
        today=date.today().isoformat(),
        error=error
    )

@app.route("/admin/maintenance/<int:maintenance_id>/complete", methods=["POST"])
@admin_required
def complete_maintenance(maintenance_id):

    with get_db() as db:
        cursor = db.execute("""
            UPDATE maintenance
            SET status = 'Completed'
            WHERE id = ?
            AND status = 'Scheduled'
        """, (maintenance_id,))

        if cursor.rowcount == 0:
            return "Maintenance record not found or already completed.", 404

    return redirect(url_for("maintenance"))

# START APPLICATION
initialize_database()

if __name__ == "__main__":
    app.run(debug=True)
