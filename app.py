from flask_mail import Mail, Message
import random
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import mysql.connector
from werkzeug.utils import secure_filename
import os
import io
import secrets
import openpyxl
import qrcode
from dotenv import load_dotenv

load_dotenv()
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

app = Flask(__name__, template_folder="templet")
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
mail = Mail(app)
app.secret_key = os.getenv("SECRET_KEY")

# ==========================
# MySQL Configuration
# ==========================



ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==========================
# Database Connection
# ==========================

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )    

def fetch_filtered_registrations(cursor, search="", event_id="", payment_status="", event_date="", sort_by="", sort_order="ASC"):
    query = """
        SELECT
            registrations.registration_id,
            students.hall_ticket,
            students.student_name,
            students.mobile,
            students.email,
            events.event_name,
            events.event_date,
            events.fee,
            registrations.payment_status,
            registrations.payment_proof
        FROM registrations
        JOIN students ON registrations.student_id = students.id
        JOIN events ON registrations.event_id = events.event_id
        WHERE 1=1
    """
    params = []

    if search:
        query += """ AND (
            students.hall_ticket LIKE %s OR
            students.student_name LIKE %s OR
            students.mobile LIKE %s OR
            students.email LIKE %s OR
            events.event_name LIKE %s OR
            registrations.payment_status LIKE %s
        )"""
        s = f"%{search}%"
        params.extend([s, s, s, s, s, s])

    if event_id:
        query += " AND events.event_id = %s"
        params.append(event_id)

    if payment_status:
        query += " AND registrations.payment_status = %s"
        params.append(payment_status)

    if event_date:
        query += " AND events.event_date = %s"
        params.append(event_date)

    valid_sort = {
        "student_name": "students.student_name",
        "event_name": "events.event_name",
        "event_date": "events.event_date",
        "payment_status": "registrations.payment_status"
    }

    order_clause = "ORDER BY registrations.registration_id DESC"
    if sort_by in valid_sort:
        direction = "DESC" if sort_order.upper() == "DESC" else "ASC"
        order_clause = f"ORDER BY {valid_sort[sort_by]} {direction}"

    query += " " + order_clause
    cursor.execute(query, tuple(params))
    return cursor.fetchall()

# ==========================
# Web Pages & Routes
# ==========================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard.html")
def dashboard():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM events ORDER BY event_date")
    events = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("dashboard.html", events=events)

@app.route("/event/<int:event_id>")
def event(event_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM events WHERE event_id=%s", (event_id,))
    event_item = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template("event.html", event=event_item)

@app.route("/send-otp", methods=["POST"])
def send_otp():

    email = request.form.get("email", "").strip()

    if not email:
        return {
            "status": "failed",
            "message": "Email is required."
        }, 400

    otp = str(random.randint(100000, 999999))

    session["otp"] = otp
    session["otp_email"] = email
    session["otp_verified"] = False

    try:

        msg = Message(
            subject="College Event Registration OTP",
            sender=app.config["MAIL_USERNAME"],
            recipients=[email]
        )

        msg.body = f"""
College Event Management System

Your OTP for event registration is:

{otp}

This OTP is valid for this registration session.

Do not share this OTP with anyone.
"""

        mail.send(msg)

        print("OTP sent to:", email)
        print("OTP:", otp)

        return {
            "status": "success"
        }

    except Exception as e:

        print("EMAIL ERROR:", e)

        return {
            "status": "failed",
            "message": "Unable to send email."
        }, 500

@app.route("/verify-otp", methods=["POST"])
def verify_otp():

    entered_otp = request.form.get("otp", "").strip()

    saved_otp = session.get("otp")

    if saved_otp and entered_otp == saved_otp:

        session["otp_verified"] = True

        return {
            "status": "verified"
        }

    return {
        "status": "failed"
    }

@app.route("/register/<int:event_id>", methods=["GET", "POST"])
def register(event_id):

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM events WHERE event_id=%s",
        (event_id,)
    )

    event_item = cursor.fetchone()

    if request.method == "POST":

        hall_ticket = request.form["hall_ticket"]
        student_name = request.form["student_name"]
        mobile = request.form["mobile"]
        email = request.form["email"]

        # ==========================
        # OTP VERIFICATION
        # ==========================

        if not session.get("otp_verified"):
            cursor.close()
            conn.close()
            return "Please verify your OTP before registering."

        # Make sure the email is the same email
        # that was verified through OTP
        if session.get("otp_email") != email:
            cursor.close()
            conn.close()
            return "The verified email does not match the registration email."

        # ==========================
        # PAYMENT SCREENSHOT
        # ==========================

        payment_file = request.files.get("payment_proof")
        filename = ""

        if payment_file and payment_file.filename != "":

            if not allowed_file(payment_file.filename):
                cursor.close()
                conn.close()

                return (
                    "Invalid image format. "
                    "Only JPG, JPEG, and PNG files are allowed."
                )

            filename = secure_filename(payment_file.filename)

            payment_folder = os.path.join(
                app.static_folder or "static",
                "payments"
            )

            try:
                os.makedirs(payment_folder, exist_ok=True)
                payment_file.save(
                    os.path.join(payment_folder, filename)
                )
            except Exception as e:
                print("Payment proof save warning:", e)

        # ==========================
        # FIND / CREATE STUDENT
        # ==========================

        cursor.execute(
            "SELECT id FROM students WHERE hall_ticket=%s",
            (hall_ticket,)
        )

        student = cursor.fetchone()

        if student:

            student_id = student["id"]

        else:

            cursor.execute("""
                INSERT INTO students
                (hall_ticket, student_name, mobile, email)
                VALUES (%s, %s, %s, %s)
            """, (
                hall_ticket,
                student_name,
                mobile,
                email
            ))

            student_id = cursor.lastrowid

        # ==========================
        # DUPLICATE REGISTRATION
        # ==========================

        cursor.execute("""
            SELECT *
            FROM registrations
            WHERE student_id=%s
            AND event_id=%s
        """, (
            student_id,
            event_id
        ))

        registration = cursor.fetchone()

        if registration:

            cursor.close()
            conn.close()

            return "You have already registered for this event."

        # ==========================
        # CREATE REGISTRATION
        # ==========================

        cursor.execute("""
            INSERT INTO registrations
            (
                student_id,
                event_id,
                payment_status,
                payment_proof
            )
            VALUES (%s, %s, %s, %s)
        """, (
            student_id,
            event_id,
            "Pending",
            filename
        ))

        registration_id = cursor.lastrowid

        # ==========================
        # GENERATE PARTICIPANT CODE
        # ==========================

        participant_code = f"CE2026-{registration_id:06d}"

        pass_token = secrets.token_urlsafe(32)

        cursor.execute("""
            UPDATE registrations
            SET participant_code=%s,
		pass_token=%s
            WHERE registration_id=%s
        """, (
            participant_code,
            pass_token,
            registration_id
        ))

        # ==========================
        # UPDATE PARTICIPANT COUNT
        # ==========================

        cursor.execute("""
            UPDATE events
            SET participants = participants + 1
            WHERE event_id=%s
        """, (
            event_id,
        ))

        conn.commit()

        # ==========================
        # CLEAR OTP SESSION
        # ==========================

        session.pop("otp", None)
        session.pop("otp_email", None)
        session.pop("otp_verified", None)

        cursor.close()
        conn.close()

        # ==========================
        # SUCCESS PAGE
        # ==========================

        return render_template(
            "registration_success.html",
            participant_code=participant_code,
            student_name=student_name,
            hall_ticket=hall_ticket,
            event=event_item
        )

    # ==========================
    # GET REQUEST
    # ==========================

    cursor.close()
    conn.close()

    return render_template(
        "register.html",
        event=event_item
    )

@app.route("/admin.html")
def admin():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    search = request.args.get("search", "").strip()
    event_id = request.args.get("event_id", "").strip()
    payment_status = request.args.get("payment_status", "").strip()
    event_date = request.args.get("event_date", "").strip()
    sort_by = request.args.get("sort_by", "").strip()
    sort_order = request.args.get("sort_order", "ASC").strip()

    cursor.execute("SELECT * FROM events ORDER BY event_date DESC")
    events = cursor.fetchall()

    registrations = fetch_filtered_registrations(cursor, search, event_id, payment_status, event_date, sort_by, sort_order)

    cursor.execute("SELECT COUNT(*) AS total_events FROM events")
    total_events = cursor.fetchone()["total_events"] or 0

    cursor.execute("SELECT COUNT(*) AS total_registrations FROM registrations")
    total_registrations = cursor.fetchone()["total_registrations"] or 0

    cursor.execute("SELECT COUNT(*) AS todays_events FROM events WHERE event_date = CURDATE()")
    todays_events = cursor.fetchone()["todays_events"] or 0

    cursor.execute("SELECT COUNT(*) AS paid_registrations FROM registrations WHERE payment_status = 'Paid'")
    paid_registrations = cursor.fetchone()["paid_registrations"] or 0

    cursor.execute("SELECT COUNT(*) AS pending_registrations FROM registrations WHERE payment_status = 'Pending'")
    pending_registrations = cursor.fetchone()["pending_registrations"] or 0

    cursor.execute("SELECT COUNT(*) AS rejected_registrations FROM registrations WHERE payment_status = 'Rejected'")
    rejected_registrations = cursor.fetchone()["rejected_registrations"] or 0

    cursor.execute("""
        SELECT
            SUM(events.fee) AS total_revenue,
            SUM(CASE WHEN registrations.payment_status = 'Paid' THEN events.fee ELSE 0 END) AS collected_revenue,
            SUM(CASE WHEN registrations.payment_status = 'Pending' THEN events.fee ELSE 0 END) AS pending_revenue
        FROM registrations
        JOIN events ON registrations.event_id = events.event_id
    """)
    rev = cursor.fetchone()
    total_revenue = rev["total_revenue"] or 0
    collected_revenue = rev["collected_revenue"] or 0
    pending_revenue = rev["pending_revenue"] or 0

    chart_events = [e["event_name"] for e in events]
    chart_participants = [e["participants"] for e in events]

    cursor.close()
    conn.close()

    return render_template(
        "admin.html",
        events=events,
        registrations=registrations,
        total_events=total_events,
        total_registrations=total_registrations,
        todays_events=todays_events,
        paid_registrations=paid_registrations,
        pending_registrations=pending_registrations,
        rejected_registrations=rejected_registrations,
        total_revenue=total_revenue,
        collected_revenue=collected_revenue,
        pending_revenue=pending_revenue,
        chart_events=chart_events,
        chart_participants=chart_participants,
        search=search,
        selected_event_id=event_id,
        selected_payment_status=payment_status,
        selected_event_date=event_date,
        selected_sort_by=sort_by,
        selected_sort_order=sort_order
    )

@app.route("/mark-paid/<int:registration_id>")
def mark_paid(registration_id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:

        # ==========================================
        # GET REGISTRATION
        # ==========================================

        sql = """
            SELECT
                registrations.registration_id,
                registrations.participant_code,
                registrations.pass_token,
                registrations.payment_status,
                students.student_name,
                students.email,
                events.event_name
            FROM registrations
            JOIN students
                ON registrations.student_id = students.id
            JOIN events
                ON registrations.event_id = events.event_id
            WHERE registrations.registration_id = %s
        """

        print("STEP 1: Getting registration")

        cursor.execute(sql, (registration_id,))

        registration = cursor.fetchone()

        if not registration:
            return "Registration not found."

        print("STEP 1 SUCCESS:", registration)

        participant_code = registration["participant_code"]
        pass_token = registration["pass_token"]

        if not participant_code:
            return "Participant code is missing."

        if not pass_token:
            return "Pass token is missing."


        # ==========================================
        # MARK PAYMENT AS PAID
        # ==========================================

        print("STEP 2: Marking payment as Paid")

        cursor.execute(
            """
            UPDATE registrations
            SET payment_status = %s
            WHERE registration_id = %s
            """,
            ("Paid", registration_id)
        )

        print("STEP 2 SUCCESS")


        # ==========================================
        # CREATE QR FOLDER
        # ==========================================

        print("STEP 3: Creating QR")

        qr_folder = os.path.join(
            app.static_folder or "static",
            "qrcodes"
        )

        try:
            os.makedirs(qr_folder, exist_ok=True)
            qr_filename = f"{participant_code}.png"
            qr_path = os.path.join(qr_folder, qr_filename)

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4
            )
            qr.add_data(participant_code)
            qr.make(fit=True)
            qr_image = qr.make_image()
            qr_image.save(qr_path)
            print("STEP 3 SUCCESS:", qr_path)
        except Exception as e:
            qr_filename = f"{participant_code}.png"
            print("QR code generation warning:", e)


        # ==========================================
        # SAVE QR FILE NAME
        # ==========================================

        print("STEP 4: Saving QR filename")

        cursor.execute(
            """
            UPDATE registrations
            SET qr_code = %s
            WHERE registration_id = %s
            """,
            (qr_filename, registration_id)
        )

        print("STEP 4 SUCCESS")


        # ==========================================
        # COMMIT DATABASE
        # ==========================================

        conn.commit()

        print("STEP 5: Database committed")


        # ==========================================
        # SEND EMAIL
        # ==========================================

        print("STEP 6: Sending event pass email")

        student_email = registration["email"]

        pass_link = url_for(
            "event_pass",
            pass_token=pass_token,
            _external=True
        )

        msg = Message(
            subject="Event Registration Approved - Your Event Pass",
            sender=app.config["MAIL_USERNAME"],
            recipients=[student_email]
        )

        msg.body = f"""
Hello {registration["student_name"]},

Your payment for the event "{registration["event_name"]}" has been approved.

Your registration is now confirmed.

Participant Code:
{participant_code}

Your Event Pass:
{pass_link}

Please open the Event Pass and save or print it.

You will need to show the QR code at the event entrance.

Thank you,
College Event Management System
"""

        mail.send(msg)

        print("STEP 6 SUCCESS: Email sent")


        cursor.close()
        conn.close()

        return redirect(url_for("admin"))


    except Exception as e:

        conn.rollback()

        print("================================")
        print("MARK PAID ERROR:")
        print(e)
        print("================================")

        cursor.close()
        conn.close()

        return f"Error approving payment: {e}"

@app.route("/reject-payment/<int:registration_id>")
def reject_payment(registration_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE registrations SET payment_status = 'Rejected' WHERE registration_id = %s", (registration_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/delete-registration/<int:registration_id>")
def delete_registration(registration_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT event_id FROM registrations WHERE registration_id = %s", (registration_id,))
    reg = cursor.fetchone()
    if reg:
        event_id = reg[0]
        cursor.execute("UPDATE events SET participants = GREATEST(0, participants - 1) WHERE event_id = %s", (event_id,))

    cursor.execute("DELETE FROM registrations WHERE registration_id = %s", (registration_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/bulk-action", methods=["POST"])
def bulk_action():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    action = request.form.get("action")
    reg_ids = request.form.getlist("registration_ids")

    if reg_ids:
        conn = get_connection()
        cursor = conn.cursor()
        format_strings = ','.join(['%s'] * len(reg_ids))
        if action == "mark_paid":
            cursor.execute(f"UPDATE registrations SET payment_status = 'Paid' WHERE registration_id IN ({format_strings})", tuple(reg_ids))
        elif action == "delete":
            for rid in reg_ids:
                cursor.execute("SELECT event_id FROM registrations WHERE registration_id = %s", (rid,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("UPDATE events SET participants = GREATEST(0, participants - 1) WHERE event_id = %s", (row[0],))
            cursor.execute(f"DELETE FROM registrations WHERE registration_id IN ({format_strings})", tuple(reg_ids))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for("admin"))

@app.route("/export-excel")
def export_excel():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    search = request.args.get("search", "").strip()
    event_id = request.args.get("event_id", "").strip()
    payment_status = request.args.get("payment_status", "").strip()
    event_date = request.args.get("event_date", "").strip()
    sort_by = request.args.get("sort_by", "").strip()
    sort_order = request.args.get("sort_order", "ASC").strip()

    registrations = fetch_filtered_registrations(cursor, search, event_id, payment_status, event_date, sort_by, sort_order)
    cursor.close()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Registrations"

    headers = ["ID", "Hall Ticket", "Student Name", "Mobile", "Email", "Event", "Event Date", "Fee", "Payment Status"]
    ws.append(headers)

    for r in registrations:
        ws.append([
            r.get("registration_id"),
            r.get("hall_ticket"),
            r.get("student_name"),
            r.get("mobile"),
            r.get("email"),
            r.get("event_name"),
            str(r.get("event_date")),
            r.get("fee"),
            r.get("payment_status")
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, download_name="registrations_report.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/export-pdf")
def export_pdf():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    search = request.args.get("search", "").strip()
    event_id = request.args.get("event_id", "").strip()
    payment_status = request.args.get("payment_status", "").strip()
    event_date = request.args.get("event_date", "").strip()
    sort_by = request.args.get("sort_by", "").strip()
    sort_order = request.args.get("sort_order", "ASC").strip()

    registrations = fetch_filtered_registrations(cursor, search, event_id, payment_status, event_date, sort_by, sort_order)
    cursor.close()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor("#1e40af"), alignment=1)

    elements.append(Paragraph("College Event Management System", title_style))
    elements.append(Paragraph("Participant Registration Report", styles['Normal']))
    elements.append(Spacer(1, 15))

    data = [["Hall Ticket", "Student Name", "Mobile", "Event", "Status"]]
    for r in registrations:
        data.append([
            str(r.get("hall_ticket", "")),
            str(r.get("student_name", "")),
            str(r.get("mobile", "")),
            str(r.get("event_name", "")),
            str(r.get("payment_status", ""))
        ])

    table = Table(data, colWidths=[100, 140, 100, 130, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2563eb")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return send_file(buffer, download_name="participant_report.pdf", as_attachment=True, mimetype="application/pdf")

@app.route("/add-event", methods=["POST"])
def add_event():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    event_name = request.form["event_name"]
    event_date = request.form["event_date"]
    venue = request.form["venue"]
    fee = request.form["fee"]
    description = request.form["description"]

    # Duplicate Event Detection Check
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM events WHERE event_name = %s AND event_date = %s", (event_name, event_date))
    existing = cursor.fetchone()
    if existing:
        cursor.close()
        conn.close()
        return "An event with the same name and date already exists."

    events_folder = os.path.join("static", "events")
    if not os.path.exists(events_folder):
        os.makedirs(events_folder)

    filename = None
    if "event_image" in request.files:
        image = request.files["event_image"]
        if image and image.filename != "":
            if not allowed_file(image.filename):
                cursor.close()
                conn.close()
                return "Invalid image format. Only JPG, JPEG, and PNG files are allowed."
            filename = secure_filename(image.filename)
            image.save(os.path.join("static", "events", filename))

    cursor.execute("""
        INSERT INTO events (event_name, event_date, venue, fee, description, event_image, participants)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (event_name, event_date, venue, fee, description, filename, 0))

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/edit-event/<int:event_id>", methods=["GET", "POST"])
def edit_event(event_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        event_name = request.form["event_name"]
        event_date = request.form["event_date"]
        venue = request.form["venue"]
        fee = request.form["fee"]
        description = request.form["description"]

        cursor.execute("""
            UPDATE events
            SET event_name=%s, event_date=%s, venue=%s, fee=%s, description=%s
            WHERE event_id=%s
        """, (event_name, event_date, venue, fee, description, event_id))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for("admin"))

    cursor.execute("SELECT * FROM events WHERE event_id=%s", (event_id,))
    event_item = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template("edit_event.html", event=event_item)

@app.route("/delete-event/<int:event_id>")
def delete_event(event_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events WHERE event_id=%s", (event_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM admin WHERE username=%s",
            (username,)
        )

        admin = cursor.fetchone()

        cursor.close()
        conn.close()

        if admin and admin["password"] == password:
            session["admin"] = admin["username"]
            return redirect(url_for("admin"))

        return render_template(
            "admin_login.html",
            error="Invalid Username or Password"
        )

    return render_template("admin_login.html")
@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.route("/db-status")
def db_status():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE();")
        db = cursor.fetchone()
        cursor.close()
        conn.close()
        return f"✅ Connected Successfully to Database : {db[0]}"
    except Exception as e:
        return f"❌ Error : {e}"

@app.route("/event-pass/<pass_token>")
def event_pass(pass_token):

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            registrations.registration_id,
            registrations.participant_code,
            registrations.qr_code,
            registrations.payment_status,

            students.student_name,
            students.hall_ticket,
            students.email,

            events.event_name,
            events.event_date,
            events.venue

        FROM registrations

        JOIN students
            ON registrations.student_id = students.id

        JOIN events
            ON registrations.event_id = events.event_id

        WHERE registrations.pass_token = %s
    """, (pass_token,))

    registration = cursor.fetchone()

    cursor.close()
    conn.close()

    if not registration:
        return "Invalid event pass."

    if registration["payment_status"] != "Paid":
        return """
        <h2>Payment Pending</h2>
        <p>Your payment has not been approved yet.</p>
        """

    if not registration["qr_code"]:
        return "Your event pass has not been generated yet."

    return render_template(
        "event_pass.html",
        registration=registration
    )

if __name__ == "__main__":
    app.run(debug=True)