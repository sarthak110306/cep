"""
Community Hackathon for Social Innovation - Flask Application
"""
import os
import re
from datetime import datetime, date, time, timedelta
from functools import wraps
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm


from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    send_file,
)
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from database.db import dict_cursor, get_db_connection

app = Flask(__name__)
app.template_folder = "templates"
app.config.from_object(Config)

# ---------------------------------------------------------------------------
# Issue #15 - session / cookie security settings.
# SESSION_COOKIE_SECURE is left dependent on FLASK_ENV/config so local HTTP
# development still works (browsers drop "Secure" cookies over plain HTTP).
# ---------------------------------------------------------------------------
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = Config.SESSION_COOKIE_SECURE
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

csrf = CSRFProtect()
csrf.init_app(app)

# Issue #14 - rate limiting for abuse-sensitive endpoints (login/signup/admin
# auth). In-memory storage is fine for a single-process college project;
# no external dependency (e.g. Redis) is required.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# Behind Render / reverse proxies: trust forwarded headers for client IP and HTTPS
from werkzeug.middleware.proxy_fix import ProxyFix
if os.getenv("RENDER") or os.getenv("USE_PROXY_FIX", "false").strip().lower() in ("1", "true", "yes"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


@app.route("/healthz")
@app.route("/ping")
def healthz():
    """Lightweight health check endpoint for monitoring and Render keep-alive."""
    return jsonify({
        "status": "healthy",
        "service": "community-hackathon",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "database": "supabase-postgres" if Config.IS_POSTGRES else "mysql"
    }), 200


# In-process keep-alive pinger for Render free tier
import threading
import time as time_module
import requests

def _run_render_keep_alive():
    url = Config.RENDER_EXTERNAL_URL
    if not url:
        return
    ping_url = f"{url.rstrip('/')}/healthz"
    interval = max(60, Config.KEEP_ALIVE_INTERVAL_MINUTES * 60)
    app.logger.info("Render keep-alive started targeting: %s (interval: %ss)", ping_url, interval)
    while True:
        try:
            time_module.sleep(interval)
            resp = requests.get(ping_url, timeout=15)
            app.logger.info("Render keep-alive ping %s: HTTP %s", ping_url, resp.status_code)
        except Exception as err:
            app.logger.warning("Render keep-alive ping failed: %s", err)

if Config.RENDER_EXTERNAL_URL:
    threading.Thread(target=_run_render_keep_alive, daemon=True, name="RenderKeepAlive").start()




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_email(email):
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email or ""))


def validate_phone(phone):
    return bool(re.match(r"^[0-9]{10}$", (phone or "").strip()))


def require_admin_fields(values, max_length=500):
    """Issue #9: minimal shared server-side validation for admin add/edit
    forms. `values` is a dict of {field_name: value}. Returns an error
    string if any value is missing/blank or too long, else None."""
    for field_name, value in values.items():
        if value is None or not str(value).strip():
            return f"'{field_name}' is required."
        if len(str(value)) > max_length:
            return f"'{field_name}' is too long (max {max_length} characters)."
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            flash("Admin login required.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


def get_current_user():
    if "user_id" not in session:
        return None
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def generate_registration_id(registration_row_id):
    """Build the public registration ID from the registration's own unique,
    database-assigned AUTO_INCREMENT id.

    The previous implementation used SELECT COUNT(*)+1, which is not safe
    under concurrent registrations: two requests can read the same count
    before either commits, producing duplicate registration_id values.
    Using the row's own primary key avoids the race entirely because MySQL
    guarantees AUTO_INCREMENT values are unique, while preserving the
    existing "HACK2026-00001" display format.
    """
    return f"HACK2026-{registration_row_id:05d}"


def problem_to_frontend(row):
    """Convert DB problem row to the JSON shape expected by existing JS."""
    return {
        "id": row["id"],
        "category": row["category"],
        "icon": row.get("icon") or "🎯",
        "title": row["title"],
        "desc": row["description"],
        "tech": row.get("technologies") or "",
        "impact": row.get("social_impact") or "",
        "example": row.get("example_text") or "",
        "solution": row.get("solution_text") or "",
        "importance": row.get("importance_text") or "",
        "difficulty": row.get("difficulty") or "Medium",
    }


def person_to_frontend(row):
    skills = [s.strip() for s in (row.get("expertise") or "").split(",") if s.strip()]
    return {
        "id": row["id"],
        "role": row["type"],
        "name": row["name"],
        "title": row.get("role") or "",
        "company": row.get("organization") or "",
        "skills": skills,
        "experience": row.get("experience") or "",
        "photo": row.get("image") or "https://i.pravatar.cc/300?img=1",
        "intro": row.get("bio") or "",
        "email": "",
        "linkedin": "#",
    }


def event_to_frontend(row):
    dt = datetime.combine(row["event_date"], (datetime.min + row["event_time"]).time() if hasattr(row["event_time"], "total_seconds") else row["event_time"])
    return {
        "id": row["id"],
        "time": dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "name": row["event_name"],
        "category": row.get("category") or "General",
        "duration": row.get("duration") or "",
        "location": row.get("venue") or "",
        "desc": row.get("description") or "",
    }


# 
#     conn = get_db_connection()
#     cursor = dict_cursor(conn)
#     try:
#         cursor.execute(
#             """
#             SELECT u.name AS user_name, u.email AS user_email,
#                    t.team_name, t.team_leader, t.college, t.email AS team_email,
#                    t.phone, ps.title AS problem_title, ps.category, ps.difficulty,
#                    r.registration_id, r.status,
#                    (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id = t.id) + 1 AS member_count
#             FROM users u
#             LEFT JOIN teams t ON t.user_id = u.id
#             LEFT JOIN problem_statements ps ON ps.id = t.problem_statement_id
#             LEFT JOIN registrations r ON r.user_id = u.id
#             WHERE u.id = %s
#             """,
#             (user_id,),
#         )
#         summary = cursor.fetchone()
#         if summary and summary.get("team_name"):
#             cursor.execute(
#                 "SELECT member_name FROM team_members WHERE team_id = "
#                 "(SELECT id FROM teams WHERE user_id = %s)",
#                 (user_id,),
#             )
#             members = [m["member_name"] for m in cursor.fetchall()]
#             summary["members"] = members
#         cursor.execute(
#             """
#             SELECT event_name, event_date, venue
#             FROM events ORDER BY event_date, event_time LIMIT 1
#             """
#         )
#         summary = summary or {}
#         summary["main_event"] = cursor.fetchone()
#         return summary
#     finally:
#         cursor.close()
#         conn.close()


def get_user_registration_summary(user_id):
    conn = get_db_connection()
    cursor = dict_cursor(conn)

    try:
        cursor.execute(
            """
            SELECT u.name AS user_name, u.email AS user_email,
                   t.team_name, t.team_leader, t.college,
                   t.email AS team_email, t.phone,
                   ps.title AS problem_title,
                   ps.category, ps.difficulty,
                   r.registration_id, r.status,
                   (SELECT COUNT(*) FROM team_members tm
                    WHERE tm.team_id = t.id) + 1 AS member_count
            FROM users u
            LEFT JOIN teams t ON t.user_id = u.id
            LEFT JOIN problem_statements ps
                ON ps.id = t.problem_statement_id
            LEFT JOIN registrations r
                ON r.user_id = u.id
            WHERE u.id = %s
            """,
            (user_id,),
        )

        summary = cursor.fetchone()

        if summary and summary.get("team_name"):
            cursor.execute(
                """
                SELECT member_name
                FROM team_members
                WHERE team_id = (
                    SELECT id FROM teams WHERE user_id = %s
                )
                """,
                (user_id,),
            )

            summary["members"] = [
                m["member_name"] for m in cursor.fetchall()
            ]

        summary = summary or {}

        # Event & Schedule
        cursor.execute(
            """
            SELECT e.id, e.event_name, e.event_date, e.event_time,
                   e.venue, e.description, e.category, e.duration
            FROM events e
            JOIN user_event_selections ues
                ON ues.event_id = e.id
            WHERE ues.user_id = %s
            ORDER BY e.event_date, e.event_time
            """,
            (user_id,),
        )

        summary["events"] = cursor.fetchall()

        # Judges & Mentors
        cursor.execute(
            """
            SELECT jm.id, jm.name, jm.role, jm.organization, jm.expertise,
                   jm.experience, jm.bio, jm.image, jm.type
            FROM judges_mentors jm
            JOIN user_judge_selections ujs
                ON ujs.judge_mentor_id = jm.id
            WHERE ujs.user_id = %s
            ORDER BY jm.type, jm.name
            """,
            (user_id,),
        )

        summary["judges_mentors"] = cursor.fetchall()

        # FAQs - only selected FAQs
        cursor.execute(
            """
            SELECT f.id, f.category, f.question, f.answer
            FROM faqs f
            JOIN user_faq_selections ufs
                ON ufs.faq_id = f.id
            WHERE ufs.user_id = %s
            ORDER BY f.id
            """,
            (user_id,),
        )

        summary["faqs"] = cursor.fetchall()

                # FAQ Personal Message
        cursor.execute(
            """
            SELECT name, email, message, created_at
            FROM user_faq_messages
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )

        summary["faq_message"] = cursor.fetchone()

        # Keep first event for existing Event Details section
        summary["main_event"] = (
            summary["events"][0] if summary["events"] else None
        )

        return summary

    finally:
        cursor.close()
        conn.close()
# ---------------------------------------------------------------------------
# Public / User Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("home"))
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email and password are required.", "error")
        return redirect(url_for("index"))
    if len(email) > 150 or len(password) > 200:
        flash("Invalid email or password.", "error")
        return redirect(url_for("index"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["login_date"] = datetime.now().strftime("%d %B %Y")
            flash("Login successful! Welcome back.", "success")
            return redirect(url_for("home"))
        flash("Invalid email or password.", "error")
        return redirect(url_for("index"))
    except Exception:
        conn.rollback()
        app.logger.exception("LOGIN ERROR")
        flash("Unable to log in right now. Please try again.", "error")
        return redirect(url_for("index"))
    finally:
        cursor.close()
        conn.close()


@app.route("/signup", methods=["POST"])
@limiter.limit("10 per minute")
def signup():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not name:
        flash("Please enter your full name.", "error")
        return redirect(url_for("index"))
    if len(name) > 100:
        flash("Name is too long.", "error")
        return redirect(url_for("index"))
    if not validate_email(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("index"))
    if len(email) > 150:
        flash("Email is too long.", "error")
        return redirect(url_for("index"))
    if len(password) < 5:
        flash("Password must be at least 5 characters.", "error")
        return redirect(url_for("index"))
    if len(password) > 200:
        flash("Password is too long.", "error")
        return redirect(url_for("index"))
    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("index"))
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            flash("An account with this email already exists.", "error")
            return redirect(url_for("index"))

        cursor.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()

        # Auto-login after successful signup
        cursor.execute(
            "SELECT id, name FROM users WHERE email = %s",
            (email,)
        )
        new_user = cursor.fetchone()

        if new_user:
            session.clear()
            session.permanent = True
            session["user_id"] = new_user["id"]
            session["user_name"] = new_user["name"]
            session["login_date"] = datetime.now().strftime("%d %B %Y")
        flash(f"Welcome, {name}! Your account has been created.", "success")
        return redirect(url_for("home"))

    except Exception:
        conn.rollback()
        app.logger.exception("SIGNUP ERROR")
        flash("Unable to create your account right now. Please try again.", "error")
        return redirect(url_for("index"))

    finally:
        cursor.close()
        conn.close()


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------
# NOTE: The OTP-based password reset (forgot_password / verify_reset_otp /
# reset_password / send_reset_otp_email) that was added in recent work has
# been intentionally removed at the project owner's request.
#
# The pre-OTP password-reset implementation could NOT be recovered: this
# project has no .git history and no backup/previous copy of app.py was
# available in the provided project archive. Per instructions, no new
# password-reset architecture has been invented to replace it.
#
# Current state: there is no working "forgot password" route. The
# corresponding frontend UI has also been removed from login.html/login.js
# (see report, Issue G) so the page does not link to a dead endpoint.
#
# To restore the exact original flow, please supply the pre-OTP version of
# app.py (or the relevant routes) and it will be wired back in unchanged.

@app.route("/home")
@login_required
def home():
    return render_template("home.html", user=session.get("user_name"))


@app.route("/about")
@login_required
def about():
    return render_template("about.html")


@app.route("/problems")
@login_required
def problems():
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT * FROM problem_statements ORDER BY id")
        problems_list = [problem_to_frontend(r) for r in cursor.fetchall()]

        selected_id = None
        cursor.execute(
            "SELECT problem_statement_id FROM user_problem_selections WHERE user_id = %s",
            (session["user_id"],),
        )
        sel = cursor.fetchone()
        if sel:
            selected_id = sel["problem_statement_id"]

        return render_template(
            "problem-statements.html",
            problems=problems_list,
            selected_id=selected_id,
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/problems/<int:problem_id>")
@login_required
def problem_detail(problem_id):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT * FROM problem_statements WHERE id = %s", (problem_id,))
        problem = cursor.fetchone()
        if not problem:
            flash("Problem statement not found.", "error")
            return redirect(url_for("problems"))
        return render_template(
            "problem-detail.html",
            problem=problem_to_frontend(problem),
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/problems/<int:problem_id>/select", methods=["POST"])
@login_required
def select_problem(problem_id):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT id FROM problem_statements WHERE id = %s", (problem_id,))
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "Problem not found"}), 404

        cursor.execute(
            "DELETE FROM user_problem_selections WHERE user_id = %s",
            (session["user_id"],)
        )
        cursor.execute(
            """
            INSERT INTO user_problem_selections (user_id, problem_statement_id)
            VALUES (%s, %s)
            """,
            (session["user_id"], problem_id),
        )
        conn.commit()
        cursor.execute(
            "SELECT title FROM problem_statements WHERE id = %s", (problem_id,)
        )
        title = cursor.fetchone()["title"]
        return jsonify({"success": True, "message": f"Selected: {title}", "title": title})
    except Exception:
        conn.rollback()
        app.logger.exception("SELECT PROBLEM ERROR")
        return jsonify({"success": False, "message": "Unable to save your selection. Please try again."}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/team-registration", methods=["GET", "POST"])
@login_required
def team_registration():
    conn = get_db_connection()
    cursor = dict_cursor(conn)

    try:
        cursor.execute(
            "SELECT * FROM problem_statements ORDER BY category, title"
        )
        all_problems = cursor.fetchall()

        cursor.execute(
            "SELECT problem_statement_id FROM user_problem_selections WHERE user_id = %s",
            (session["user_id"],),
        )
        selected = cursor.fetchone()
        selected_problem_id = (
            selected["problem_statement_id"] if selected else None
        )

        # -------------------------
        # GET REQUEST
        # -------------------------
        if request.method == "GET":
            cursor.execute(
                "SELECT * FROM teams WHERE user_id = %s",
                (session["user_id"],)
            )
            existing = cursor.fetchone()

            members = []

            if existing:
                cursor.execute(
                    "SELECT member_name FROM team_members WHERE team_id = %s",
                    (existing["id"],),
                )
                members = [
                    m["member_name"]
                    for m in cursor.fetchall()
                ]

            return render_template(
                "team-registration.html",
                problems=all_problems,
                selected_problem_id=selected_problem_id,
                existing_team=existing,
                existing_members=members,
            )

        # -------------------------
        # GET FORM DATA
        # -------------------------
        team_name = request.form.get("team_name", "").strip()
        college = request.form.get("college", "").strip()
        leader_name = request.form.get("leader_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        problem_id = request.form.get("problem_statement_id")
        member_names = request.form.getlist("members")

        # -------------------------
        # REQUIRED FIELD VALIDATION
        # -------------------------
        if not all([
            team_name,
            college,
            leader_name,
            phone,
            email,
            problem_id
        ]):
            flash(
                "Please fill in all required fields.",
                "error"
            )
            return redirect(url_for("team_registration"))

        # -------------------------
        # EMAIL VALIDATION
        # -------------------------
        if not validate_email(email):
            flash(
                "Please enter a valid email address.",
                "error"
            )
            return redirect(url_for("team_registration"))

        # -------------------------
        # PHONE VALIDATION
        # -------------------------
        if not validate_phone(phone):
            flash(
                "Please enter a valid 10-digit phone number.",
                "error"
            )
            return redirect(url_for("team_registration"))

        # -------------------------
        # FIELD LENGTH VALIDATION
        # -------------------------
        if (
            len(team_name) > 150
            or len(college) > 200
            or len(leader_name) > 100
        ):
            flash(
                "One or more fields exceed the allowed length.",
                "error"
            )
            return redirect(url_for("team_registration"))

        # -------------------------
        # PROBLEM ID VALIDATION
        # -------------------------
        if not problem_id.isdigit():
            flash(
                "Please select a valid problem statement.",
                "error"
            )
            return redirect(url_for("team_registration"))

        # -------------------------
        # TEAM MEMBER VALIDATION
        # -------------------------
        cleaned_members = [
            m.strip()
            for m in member_names
        ]

        # Blank member names
        if any(m == "" for m in cleaned_members):
            flash(
                "Please enter the name of every team member.",
                "error"
            )

            existing_team_data = {
                "team_name": team_name,
                "college": college,
                "team_leader": leader_name,
                "phone": phone,
                "email": email,
                "problem_statement_id": int(problem_id),
            }

            return render_template(
                "team-registration.html",
                problems=all_problems,
                selected_problem_id=int(problem_id),
                existing_team=existing_team_data,
                existing_members=member_names,
            )

        # Member name length
        if any(len(m) > 100 for m in cleaned_members):
            flash(
                "One or more member names exceed the allowed length.",
                "error"
            )

            existing_team_data = {
                "team_name": team_name,
                "college": college,
                "team_leader": leader_name,
                "phone": phone,
                "email": email,
                "problem_statement_id": int(problem_id),
            }

            return render_template(
                "team-registration.html",
                problems=all_problems,
                selected_problem_id=int(problem_id),
                existing_team=existing_team_data,
                existing_members=member_names,
            )

        # At least 1 additional member
        if len(cleaned_members) < 1:
            flash(
                "A team must have at least 1 additional member.",
                "error"
            )

            existing_team_data = {
                "team_name": team_name,
                "college": college,
                "team_leader": leader_name,
                "phone": phone,
                "email": email,
                "problem_statement_id": int(problem_id),
            }

            return render_template(
                "team-registration.html",
                problems=all_problems,
                selected_problem_id=int(problem_id),
                existing_team=existing_team_data,
                existing_members=member_names,
            )

        # Maximum 3 additional members
        if len(cleaned_members) > 3:
            flash(
                "A team can have a maximum of 3 additional members.",
                "error"
            )

            existing_team_data = {
                "team_name": team_name,
                "college": college,
                "team_leader": leader_name,
                "phone": phone,
                "email": email,
                "problem_statement_id": int(problem_id),
            }

            return render_template(
                "team-registration.html",
                problems=all_problems,
                selected_problem_id=int(problem_id),
                existing_team=existing_team_data,
                existing_members=member_names,
            )

        member_names = cleaned_members

        # -------------------------
        # DUPLICATE TEAM NAME CHECK
        # -------------------------
        cursor.execute(
            """
            SELECT id
            FROM teams
            WHERE team_name = %s
            AND user_id != %s
            """,
            (
                team_name,
                session["user_id"]
            )
        )

        if cursor.fetchone():
            flash(
                "This team name is already taken. Please choose another.",
                "error"
            )

            existing_team_data = {
                "team_name": team_name,
                "college": college,
                "team_leader": leader_name,
                "phone": phone,
                "email": email,
                "problem_statement_id": int(problem_id),
            }

            return render_template(
                "team-registration.html",
                problems=all_problems,
                selected_problem_id=int(problem_id),
                existing_team=existing_team_data,
                existing_members=member_names,
            )

        # -------------------------
        # CHECK CURRENT USER TEAM
        # -------------------------
        cursor.execute(
            "SELECT id FROM teams WHERE user_id = %s",
            (session["user_id"],)
        )
        existing_team = cursor.fetchone()

        # -------------------------
        # UPDATE EXISTING TEAM
        # -------------------------
        if existing_team:
            team_id = existing_team["id"]

            cursor.execute(
                """
                UPDATE teams
                SET team_name=%s,
                    team_leader=%s,
                    college=%s,
                    email=%s,
                    phone=%s,
                    problem_statement_id=%s
                WHERE id=%s
                """,
                (
                    team_name,
                    leader_name,
                    college,
                    email,
                    phone,
                    problem_id,
                    team_id,
                ),
            )

            cursor.execute(
                "DELETE FROM team_members WHERE team_id = %s",
                (team_id,)
            )

        # -------------------------
        # CREATE NEW TEAM
        # -------------------------
        else:
            cursor.execute(
                "SELECT id FROM teams WHERE team_name = %s",
                (team_name,)
            )

            if cursor.fetchone():
                flash(
                    "This team name is already taken. Please choose another.",
                    "error"
                )
                return redirect(
                    url_for("team_registration")
                )

            cursor.execute(
                """
                INSERT INTO teams
                (
                    user_id,
                    team_name,
                    team_leader,
                    college,
                    email,
                    phone,
                    problem_statement_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session["user_id"],
                    team_name,
                    leader_name,
                    college,
                    email,
                    phone,
                    problem_id,
                ),
            )

            team_id = cursor.lastrowid

        # -------------------------
        # SAVE TEAM MEMBERS
        # -------------------------
        for name in member_names:
            cursor.execute(
                """
                INSERT INTO team_members
                (team_id, member_name)
                VALUES (%s, %s)
                """,
                (team_id, name),
            )

        # -------------------------
        # REGISTRATION RECORD
        # -------------------------
        cursor.execute(
            "SELECT id FROM registrations WHERE user_id = %s",
            (session["user_id"],)
        )

        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO registrations
                (user_id, team_id, status)
                VALUES (%s, %s, 'Pending')
                """,
                (
                    session["user_id"],
                    team_id
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE registrations
                SET team_id = %s,
                    status = 'Pending'
                WHERE user_id = %s
                """,
                (
                    team_id,
                    session["user_id"]
                ),
            )

        # -------------------------
        # SAVE ALL CHANGES
        # -------------------------
        conn.commit()

        if existing_team:
            flash(
                "Team details updated successfully! Continue through Judges & Mentors, Event Schedule, Gallery, FAQ, and Contact Us to review your registration.",
                "success"
            )
        else:
            flash(
                "Team registered successfully! Continue through Judges & Mentors, Event Schedule, Gallery, FAQ, and Contact Us to review your registration.",
                "success"
            )

        return redirect(
            url_for("judges_mentors")
        )

    except Exception:
        conn.rollback()

        app.logger.exception(
            "TEAM REGISTRATION ERROR"
        )

        flash(
            "We couldn't save your team registration. Please check your details and try again.",
            "error"
        )

        return redirect(
            url_for("team_registration")
        )

    finally:
        cursor.close()
        conn.close()
@app.route("/judges-mentors")
@login_required
def judges_mentors():
    conn = get_db_connection()
    cursor = dict_cursor(conn)

    try:
        cursor.execute("SELECT * FROM judges_mentors ORDER BY type, name")
        people = [person_to_frontend(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT judge_mentor_id
            FROM user_judge_selections
            WHERE user_id = %s
            """,
            (session["user_id"],)
        )

        selected_judge_ids = [
            row["judge_mentor_id"]
            for row in cursor.fetchall()
        ]

        return render_template(
            "judges-mentors.html",
            people=people,
            selected_judge_ids=selected_judge_ids
        )

    finally:
        cursor.close()
        conn.close()


@app.route("/save-judge-selection", methods=["POST"])
@login_required
def save_judge_selection():
    data = request.get_json(silent=True) or {}
    selected_ids = data.get("selected_ids", [])
    if not isinstance(selected_ids, list):
        return jsonify({"success": False, "message": "Invalid selection."}), 400
    try:
        selected_ids = [int(pid) for pid in selected_ids]
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid selection."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "DELETE FROM user_judge_selections WHERE user_id = %s",
            (session["user_id"],)
        )

        for person_id in selected_ids:
            cursor.execute(
                """
                INSERT INTO user_judge_selections
                (user_id, judge_mentor_id)
                VALUES (%s, %s)
                """,
                (session["user_id"], person_id)
            )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Judge and mentor selection saved successfully."
        })

    except Exception:
        conn.rollback()
        app.logger.exception("SAVE JUDGE SELECTION ERROR")
        return jsonify({
            "success": False,
            "message": "Unable to save your selection. Please try again."
        }), 500

    finally:
        cursor.close()
        conn.close()

@app.route("/save-event-selection", methods=["POST"])
@login_required
def save_event_selection():
    data = request.get_json() or {}
    selected_ids = data.get("selected_ids", [])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Remove previous selections
        cursor.execute(
            "DELETE FROM user_event_selections WHERE user_id = %s",
            (session["user_id"],)
        )

        # Save newly selected events
        for event_id in selected_ids:
            cursor.execute(
                """
                INSERT INTO user_event_selections
                (user_id, event_id)
                VALUES (%s, %s)
                """,
                (session["user_id"], event_id)
            )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Event selection saved successfully."
        })

    except Exception:
        conn.rollback()
        app.logger.exception("SAVE EVENT SELECTION ERROR")

        return jsonify({
            "success": False,
            "message": "Unable to save your selection. Please try again."
        }), 500

    finally:
        cursor.close()
        conn.close()

@app.route("/save-faq-selection", methods=["POST"])
@login_required
def save_faq_selection():
    data = request.get_json() or {}
    selected_ids = data.get("selected_ids", [])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Remove previous FAQ selections
        cursor.execute(
            "DELETE FROM user_faq_selections WHERE user_id = %s",
            (session["user_id"],)
        )

        # Save new FAQ selections
        for faq_id in selected_ids:
            cursor.execute(
                """
                INSERT INTO user_faq_selections
                (user_id, faq_id)
                VALUES (%s, %s)
                """,
                (session["user_id"], faq_id)
            )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "FAQ selection saved successfully."
        })

    except Exception:
        conn.rollback()
        app.logger.exception("SAVE FAQ SELECTION ERROR")

        return jsonify({
            "success": False,
            "message": "Unable to save your selection. Please try again."
        }), 500

    finally:
        cursor.close()
        conn.close()

@app.route("/save-faq-message", methods=["POST"])
@login_required
def save_faq_message():
    data = request.get_json() or {}

    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    message = data.get("message", "").strip()

    if not name or not email or not message:
        return jsonify({
            "success": False,
            "message": "Please fill in all fields."
        }), 400

    if not validate_email(email):
        return jsonify({
            "success": False,
            "message": "Please enter a valid email address."
        }), 400

    # Issue #9 - basic server-side length limits (client-side only before)
    if len(name) > 100 or len(message) > 2000:
        return jsonify({
            "success": False,
            "message": "Name or message is too long."
        }), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO user_faq_messages
            (user_id, name, email, message)
            VALUES (%s, %s, %s, %s)
            """,
            (
                session["user_id"],
                name,
                email,
                message
            )
        )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Your message has been saved successfully."
        })

    except Exception:
        conn.rollback()
        app.logger.exception("SAVE FAQ MESSAGE ERROR")

        return jsonify({
            "success": False,
            "message": "Unable to save your message. Please try again."
        }), 500

    finally:
        cursor.close()
        conn.close()

@app.route("/events")
@login_required
def events():

    conn = get_db_connection()
    cursor = dict_cursor(conn)

    try:
        cursor.execute(
            "SELECT * FROM events ORDER BY event_date, event_time"
        )
        events_list = [event_to_frontend(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT event_id
            FROM user_event_selections
            WHERE user_id = %s
            """,
            (session["user_id"],)
        )

        selected_event_ids = [
            row["event_id"]
            for row in cursor.fetchall()
        ]

        return render_template(
            "event.html",
            events=events_list,
            selected_event_ids=selected_event_ids
        )

    finally:
        cursor.close()
        conn.close()

@app.route("/gallery")
@login_required
def gallery():
    return render_template("gallery.html")


@app.route("/faq")
@login_required
def faq():
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT * FROM faqs ORDER BY id")
        faqs = [
            {
                "id": r["id"],
                "category": r.get("category") or "General",
                "q": r["question"],
                "a": r["answer"],
            }
            for r in cursor.fetchall()
        ]
        return render_template("faq.html", faqs=faqs)
    finally:
        cursor.close()
        conn.close()


@app.route("/contact", methods=["GET", "POST"])
@login_required
def contact():
    if request.method == "GET":
        return render_template("contact.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if not all([name, email, subject, message]):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("contact"))
    if not validate_email(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("contact"))
    if len(name) > 100 or len(subject) > 200 or len(message) > 5000:
        flash("One or more fields exceed the allowed length.", "error")
        return redirect(url_for("contact"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            """
            INSERT INTO contact_messages (name, email, subject, message)
            VALUES (%s, %s, %s, %s)
            """,
            (name, email, subject, message),
        )
        conn.commit()
        flash("Your message has been sent successfully! We will get back to you soon.", "success")
        return redirect(url_for("contact"))
    except Exception:
        conn.rollback()
        app.logger.exception("CONTACT MESSAGE ERROR")
        flash("Unable to send your message. Please try again.", "error")
        return redirect(url_for("contact"))
    finally:
        cursor.close()
        conn.close()


@app.route("/registration-summary")
@login_required
def registration_summary():
    summary = get_user_registration_summary(session["user_id"])
    if not summary or not summary.get("team_name"):
        flash("Please complete team registration first.", "error")
        return redirect(url_for("team_registration"))
    return render_template("registration-summary.html", summary=summary)


@app.route("/registration-summary/confirm", methods=["POST"])
@login_required
def confirm_registration():
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            "SELECT * FROM registrations WHERE user_id = %s", (session["user_id"],)
        )
        reg = cursor.fetchone()
        if not reg:
            flash("No registration found. Please register your team first.", "error")
            return redirect(url_for("team_registration"))

        reg_id = reg.get("registration_id") or generate_registration_id(reg["id"])
        cursor.execute(
            """
            UPDATE registrations
            SET status = 'Confirmed', registration_id = %s, confirmed_at = NOW()
            WHERE user_id = %s
            """,
            (reg_id, session["user_id"]),
        )
        conn.commit()
        flash(f"Registration confirmed! Your Registration ID is {reg_id}", "success")
        return redirect(url_for("registration_summary"))
    except Exception:
        conn.rollback()
        app.logger.exception("CONFIRM REGISTRATION ERROR")
        flash("Unable to confirm your registration right now. Please try again.", "error")
        return redirect(url_for("team_registration"))
    finally:
        cursor.close()
        conn.close()

# =========================
# Certificate Routes
# =========================

@app.route("/certificate-design-preview")
def certificate_design_preview():
    return render_template(
        "certificate-design.html",
        participant_name="Sarthak Dhamankar",
        team_name="FGH Teams",
        problem_statement="Emergency Safety Companion",
        event_name="Community Hackathon 2026",
        issued_date="02 October 2026",
        certificate_id="CERT-HACK2026-00006"
    )


@app.route("/certificates")
@login_required
def certificates():
    conn = get_db_connection()
    cursor = dict_cursor(conn)

    try:
        cursor.execute(
            """
            SELECT certificate_id,
                   certificate_type,
                   position,
                   team_name,
                   problem_statement,
                   issued_at
            FROM certificates
            WHERE user_id = %s
            ORDER BY issued_at DESC
            """,
            (session["user_id"],)
        )

        certificate_list = cursor.fetchall()

        return render_template(
            "certificates.html",
            certificates=certificate_list
        )

    finally:
        cursor.close()
        conn.close()


@app.route("/download-certificate/<certificate_id>")
@login_required
def download_certificate(certificate_id):

    conn = get_db_connection()
    cursor = dict_cursor(conn)

    try:
        # =========================================================
        # 1. GET CERTIFICATE DATA
        # =========================================================
        cursor.execute(
            """
            SELECT certificate_id,
                   certificate_type,
                   position,
                   team_name,
                   problem_statement,
                   issued_at
            FROM certificates
            WHERE certificate_id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (certificate_id, session["user_id"])
        )

        certificate = cursor.fetchone()

        if not certificate:
            flash("Certificate not found.", "error")
            return redirect(url_for("certificates"))


        # =========================================================
        # 2. GET CURRENT TEAM + TEAM LEADER + PROBLEM STATEMENT
        # =========================================================
        cursor.execute(
            """
            SELECT
                t.team_leader,
                t.team_name,
                ps.title AS problem_title
            FROM teams t
            LEFT JOIN problem_statements ps
                ON ps.id = t.problem_statement_id
            WHERE t.user_id = %s
            ORDER BY t.id DESC
            LIMIT 1
            """,
            (session["user_id"],)
        )

        team_data = cursor.fetchone()


        # =========================================================
        # 3. PARTICIPANT NAME
        # =========================================================
        participant_name = "Participant"

        if team_data and team_data.get("team_leader"):
            participant_name = team_data["team_leader"].strip()


        # =========================================================
        # 4. TEAM NAME
        # =========================================================
        team_name = certificate.get("team_name") or "N/A"

        if team_data and team_data.get("team_name"):
            team_name = team_data["team_name"].strip()


        # =========================================================
        # 5. PROBLEM STATEMENT
        # =========================================================
        problem_statement = certificate.get("problem_statement") or "N/A"

        if team_data and team_data.get("problem_title"):
            problem_statement = team_data["problem_title"].strip()


        # =========================================================
        # 6. GET SELECTED EVENT
        # =========================================================
        event_name = "N/A"

        try:
            cursor.execute(
                """
                SELECT e.event_name
                FROM events e
                JOIN user_event_selections ues
                    ON ues.event_id = e.id
                WHERE ues.user_id = %s
                ORDER BY e.event_date, e.event_time
                LIMIT 1
                """,
                (session["user_id"],)
            )

            event_data = cursor.fetchone()

            if event_data and event_data.get("event_name"):
                event_name = event_data["event_name"].strip()

        except Exception:
            # If event selection is unavailable,
            # certificate generation should still continue.
            event_name = "Community Hackathon 2026"


        # =========================================================
        # 7. DATE OF ISSUE
        # =========================================================
        # Actual date on which certificate is downloaded.
        from datetime import datetime

        issued_date = datetime.now().strftime("%d %B %Y")


        # =========================================================
        # 8. CERTIFICATE ID
        # =========================================================
        actual_certificate_id = (
            certificate.get("certificate_id")
            or certificate_id
        )


        # =========================================================
        # 9. CREATE PDF BUFFER
        # =========================================================
        from io import BytesIO

        buffer = BytesIO()

        # A4 LANDSCAPE
        page_width = A4[1]
        page_height = A4[0]

        pdf = canvas.Canvas(
            buffer,
            pagesize=(page_width, page_height)
        )


        # =========================================================
        # 10. COLORS
        # =========================================================
        navy = colors.HexColor("#123B63")
        blue = colors.HexColor("#2E75B6")
        light_blue = colors.HexColor("#EAF3FA")
        dark_text = colors.HexColor("#243447")
        grey = colors.HexColor("#667085")
        border = colors.HexColor("#D5DEE8")
        white = colors.white


        # =========================================================
        # 11. BACKGROUND
        # =========================================================
        pdf.setFillColor(white)
        pdf.rect(
            0,
            0,
            page_width,
            page_height,
            fill=1,
            stroke=0
        )


        # =========================================================
        # 12. OUTER BORDER
        # =========================================================
        pdf.setStrokeColor(navy)
        pdf.setLineWidth(2)
        pdf.rect(
            15 * mm,
            15 * mm,
            page_width - 30 * mm,
            page_height - 30 * mm,
            fill=0,
            stroke=1
        )


        # Inner border
        pdf.setStrokeColor(border)
        pdf.setLineWidth(0.7)
        pdf.rect(
            19 * mm,
            19 * mm,
            page_width - 38 * mm,
            page_height - 38 * mm,
            fill=0,
            stroke=1
        )


        # =========================================================
        # 13. TOP BLUE LINE
        # =========================================================
        pdf.setFillColor(navy)
        pdf.roundRect(
            30 * mm,
            page_height - 30 * mm,
            page_width - 60 * mm,
            3 * mm,
            1.5 * mm,
            fill=1,
            stroke=0
        )


        # =========================================================
        # 14. COLLEGE LOGO
        # =========================================================
        logo_path = os.path.join(
            app.root_path,
            "static",
            "assets",
            "college-logo.png"
        )

        if os.path.exists(logo_path):
            try:
                pdf.drawImage(
                    logo_path,
                    28 * mm,
                    page_height - 48 * mm,
                    width=24 * mm,
                    height=24 * mm,
                    preserveAspectRatio=True,
                    mask="auto"
                )
            except Exception:
                pass


        # =========================================================
        # 15. HACKATHON BRANDING
        # =========================================================
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 13)

        pdf.drawString(
            56 * mm,
            page_height - 35 * mm,
            "COMMUNITY HACKATHON"
        )

        pdf.setFillColor(blue)
        pdf.setFont("Helvetica", 8.5)

        pdf.drawString(
            56 * mm,
            page_height - 41 * mm,
            "INNOVATE  •  BUILD  •  CREATE IMPACT"
        )


        # =========================================================
        # 16. COLLEGE NAME
        # =========================================================
        pdf.setFillColor(dark_text)
        pdf.setFont("Helvetica-Bold", 9.5)

        pdf.drawRightString(
            page_width - 30 * mm,
            page_height - 35 * mm,
            "ANNASAHEB VARTAK COLLEGE"
        )

        pdf.setFont("Helvetica", 8)

        pdf.setFillColor(grey)

        pdf.drawRightString(
            page_width - 30 * mm,
            page_height - 41 * mm,
            "Vasai West, Maharashtra"
        )


        # =========================================================
        # 17. CERTIFICATE TITLE
        # =========================================================
        title_y = page_height - 67 * mm

        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 25)

        pdf.drawCentredString(
            page_width / 2,
            title_y,
            "CERTIFICATE"
        )

        pdf.setFillColor(blue)
        pdf.setFont("Helvetica-Bold", 10)

        pdf.drawCentredString(
            page_width / 2,
            title_y - 8 * mm,
            "OF PARTICIPATION"
        )


        # =========================================================
        # 18. PARTICIPATION TEXT
        # =========================================================
        pdf.setFillColor(grey)
        pdf.setFont("Helvetica", 9.5)

        pdf.drawCentredString(
            page_width / 2,
            title_y - 20 * mm,
            "This certificate is proudly presented to"
        )


        # =========================================================
        # 19. PARTICIPANT NAME
        # =========================================================
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 22)

        pdf.drawCentredString(
            page_width / 2,
            title_y - 32 * mm,
            participant_name
        )

        # underline
        name_width = pdf.stringWidth(
            participant_name,
            "Helvetica-Bold",
            22
        )

        pdf.setStrokeColor(blue)
        pdf.setLineWidth(1)

        pdf.line(
            (page_width - name_width) / 2,
            title_y - 34 * mm,
            (page_width + name_width) / 2,
            title_y - 34 * mm
        )


        # =========================================================
        # 20. DESCRIPTION
        # =========================================================
        pdf.setFillColor(dark_text)
        pdf.setFont("Helvetica", 9)

        pdf.drawCentredString(
            page_width / 2,
            title_y - 43 * mm,
            "for successfully participating in the"
        )

        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 10)

        pdf.drawCentredString(
            page_width / 2,
            title_y - 49 * mm,
            event_name
        )


        # =========================================================
        # 21. INFORMATION CARDS
        # =========================================================
        card_y = 58 * mm
        card_height = 24 * mm
        card_gap = 7 * mm

        total_card_width = page_width - 70 * mm
        card_width = (
            total_card_width - (2 * card_gap)
        ) / 3

        cards = [
            ("TEAM", team_name),
            ("PROBLEM STATEMENT", problem_statement),
            ("EVENT", event_name)
        ]

        start_x = 35 * mm

        for index, (label, value) in enumerate(cards):

            x = start_x + index * (card_width + card_gap)

            # Card background
            pdf.setFillColor(light_blue)

            pdf.roundRect(
                x,
                card_y,
                card_width,
                card_height,
                4 * mm,
                fill=1,
                stroke=0
            )

            # Card border
            pdf.setStrokeColor(border)
            pdf.setLineWidth(0.7)

            pdf.roundRect(
                x,
                card_y,
                card_width,
                card_height,
                4 * mm,
                fill=0,
                stroke=1
            )

            # Label
            pdf.setFillColor(blue)
            pdf.setFont("Helvetica-Bold", 7.5)

            pdf.drawCentredString(
                x + card_width / 2,
                card_y + 16 * mm,
                label
            )

            # Value
            pdf.setFillColor(dark_text)
            pdf.setFont("Helvetica-Bold", 8.5)

            display_value = str(value)

            max_chars = 32

            if len(display_value) > max_chars:
                display_value = (
                    display_value[:max_chars - 3]
                    + "..."
                )

            pdf.drawCentredString(
                x + card_width / 2,
                card_y + 8 * mm,
                display_value
            )


        # =========================================================
        # 22. SIGNATURES
        # =========================================================
        signature_y = 32 * mm

        left_signature_x = 58 * mm
        right_signature_x = page_width - 58 * mm

        meenal_signature = os.path.join(
            app.root_path,
            "static",
            "assets",
            "meenal-signature.png"
        )

        rohan_signature = os.path.join(
            app.root_path,
            "static",
            "assets",
            "rohan-signature.png"
        )

        # Meenal signature
        if os.path.exists(meenal_signature):
            try:
                pdf.drawImage(
                    meenal_signature,
                    left_signature_x - 22 * mm,
                    signature_y + 5 * mm,
                    width=44 * mm,
                    height=13 * mm,
                    preserveAspectRatio=True,
                    mask="auto"
                )
            except Exception:
                pass

        # Rohan signature
        if os.path.exists(rohan_signature):
            try:
                pdf.drawImage(
                    rohan_signature,
                    right_signature_x - 22 * mm,
                    signature_y + 5 * mm,
                    width=44 * mm,
                    height=13 * mm,
                    preserveAspectRatio=True,
                    mask="auto"
                )
            except Exception:
                pass


        # Signature lines
        pdf.setStrokeColor(grey)
        pdf.setLineWidth(0.6)

        pdf.line(
            left_signature_x - 25 * mm,
            signature_y + 3 * mm,
            left_signature_x + 25 * mm,
            signature_y + 3 * mm
        )

        pdf.line(
            right_signature_x - 25 * mm,
            signature_y + 3 * mm,
            right_signature_x + 25 * mm,
            signature_y + 3 * mm
        )


        # Signature names
        pdf.setFillColor(dark_text)
        pdf.setFont("Helvetica-Bold", 8)

        pdf.drawCentredString(
            left_signature_x,
            signature_y - 2 * mm,
            "Dr. Meenal Deshpande"
        )

        pdf.drawCentredString(
            right_signature_x,
            signature_y - 2 * mm,
            "Prof. Rohan Kulkarni"
        )


        # Designations
        pdf.setFillColor(grey)
        pdf.setFont("Helvetica", 7)

        pdf.drawCentredString(
            left_signature_x,
            signature_y - 6 * mm,
            "Event Coordinator"
        )

        pdf.drawCentredString(
            right_signature_x,
            signature_y - 6 * mm,
            "Head of Department"
        )


        # =========================================================
        # 23. DATE OF ISSUE
        # =========================================================
        pdf.setFillColor(grey)
        pdf.setFont("Helvetica", 7)

        pdf.drawString(
            30 * mm,
            22 * mm,
            "DATE OF ISSUE"
        )

        pdf.setFillColor(dark_text)
        pdf.setFont("Helvetica-Bold", 8)

        pdf.drawString(
            30 * mm,
            17.5 * mm,
            issued_date
        )


        # =========================================================
        # 24. CERTIFICATE ID
        # =========================================================
        pdf.setFillColor(grey)
        pdf.setFont("Helvetica", 7)

        pdf.drawRightString(
            page_width - 30 * mm,
            22 * mm,
            "CERTIFICATE ID"
        )

        pdf.setFillColor(dark_text)
        pdf.setFont("Helvetica-Bold", 8)

        pdf.drawRightString(
            page_width - 30 * mm,
            17.5 * mm,
            actual_certificate_id
        )


        # =========================================================
        # 25. QR CODE
        # =========================================================
        qr_value = (
            f"Certificate ID: {actual_certificate_id}\n"
            f"Participant: {participant_name}\n"
            f"Team: {team_name}\n"
            f"Problem: {problem_statement}\n"
            f"Event: {event_name}"
        )

        try:
            from reportlab.graphics.barcode.qr import QrCodeWidget
            from reportlab.graphics.shapes import Drawing
            from reportlab.graphics import renderPDF

            qr = QrCodeWidget(qr_value)

            qr_size = 18 * mm

            qr.barWidth = qr_size
            qr.barHeight = qr_size

            drawing = Drawing(
                qr_size,
                qr_size
            )

            drawing.add(qr)

            renderPDF.draw(
                drawing,
                pdf,
                page_width / 2 - qr_size / 2,
                17 * mm
            )

        except Exception:
            pass


        # =========================================================
        # 26. FINISH PDF
        # =========================================================
        pdf.showPage()
        pdf.save()

        buffer.seek(0)


        # =========================================================
        # 27. DOWNLOAD
        # =========================================================
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"{actual_certificate_id}.pdf",
            mimetype="application/pdf"
        )


    except Exception as e:

        conn.rollback()

        app.logger.exception(
            "CERTIFICATE DOWNLOAD ERROR"
        )

        return f"""
        <h2>Certificate Generation Error</h2>
        <pre>{e}</pre>
        """, 500

    finally:

        cursor.close()
        conn.close()

@app.route("/admin/events/add", methods=["POST"])
@admin_required
def admin_add_event():
    event_name = request.form.get("event_name", "").strip()
    event_date = request.form.get("event_date", "").strip()
    event_time = request.form.get("event_time", "").strip()
    venue = request.form.get("venue", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()
    duration = request.form.get("duration", "").strip()

    error = require_admin_fields({"event_name": event_name, "event_date": event_date, "venue": venue})
    if not error:
        try:
            datetime.strptime(event_date, "%Y-%m-%d")
            if event_time:
                datetime.strptime(event_time, "%H:%M")
        except ValueError:
            error = "Please enter a valid event date/time."
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            """
            INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (event_name, event_date, event_time, venue, description, category, duration),
        )
        conn.commit()
        flash("Event added.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("ADD EVENT ERROR")
        flash("Unable to add event. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/events/<int:eid>/edit", methods=["POST"])
@admin_required
def admin_edit_event(eid):
    event_name = request.form.get("event_name", "").strip()
    event_date = request.form.get("event_date", "").strip()
    event_time = request.form.get("event_time", "").strip()
    venue = request.form.get("venue", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()
    duration = request.form.get("duration", "").strip()

    error = require_admin_fields({"event_name": event_name, "event_date": event_date, "venue": venue})
    if not error:
        try:
            datetime.strptime(event_date, "%Y-%m-%d")
            if event_time:
                datetime.strptime(event_time, "%H:%M")
        except ValueError:
            error = "Please enter a valid event date/time."
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            """
            UPDATE events SET event_name=%s, event_date=%s, event_time=%s,
            venue=%s, description=%s, category=%s, duration=%s WHERE id=%s
            """,
            (event_name, event_date, event_time, venue, description, category, duration, eid),
        )
        conn.commit()
        flash("Event updated.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("EDIT EVENT ERROR")
        flash("Unable to update event. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/events/<int:eid>/delete", methods=["POST"])
@admin_required
def admin_delete_event(eid):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("DELETE FROM events WHERE id = %s", (eid,))
        conn.commit()
        flash("Event deleted.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("DELETE EVENT ERROR")
        flash("Unable to delete event. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


# --- Admin CRUD: FAQs ---

@app.route("/admin/faqs/add", methods=["POST"])
@admin_required
def admin_add_faq():
    question = request.form.get("question", "").strip()
    answer = request.form.get("answer", "").strip()
    category = request.form.get("category", "General").strip()

    error = require_admin_fields({"question": question, "answer": answer}, max_length=2000)
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            "INSERT INTO faqs (question, answer, category) VALUES (%s, %s, %s)",
            (question, answer, category),
        )
        conn.commit()
        flash("FAQ added.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("ADD FAQ ERROR")
        flash("Unable to add FAQ. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/faqs/<int:fid>/edit", methods=["POST"])
@admin_required
def admin_edit_faq(fid):
    question = request.form.get("question", "").strip()
    answer = request.form.get("answer", "").strip()
    category = request.form.get("category", "").strip()

    error = require_admin_fields({"question": question, "answer": answer}, max_length=2000)
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            "UPDATE faqs SET question=%s, answer=%s, category=%s WHERE id=%s",
            (question, answer, category, fid),
        )
        conn.commit()
        flash("FAQ updated.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("EDIT FAQ ERROR")
        flash("Unable to update FAQ. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/faqs/<int:fid>/delete", methods=["POST"])
@admin_required
def admin_delete_faq(fid):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("DELETE FROM faqs WHERE id = %s", (fid,))
        conn.commit()
        flash("FAQ deleted.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("DELETE FAQ ERROR")
        flash("Unable to delete FAQ. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


# --- Admin: Contact Messages ---

@app.route("/admin/messages/<int:mid>/read", methods=["POST"])
@admin_required
def admin_mark_message_read(mid):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("UPDATE contact_messages SET is_read=1 WHERE id=%s", (mid,))
        conn.commit()
        flash("Message marked as read.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("MARK MESSAGE READ ERROR")
        flash("Unable to update message. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/messages/<int:mid>/delete", methods=["POST"])
@admin_required
def admin_delete_message(mid):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("DELETE FROM contact_messages WHERE id = %s", (mid,))
        conn.commit()
        flash("Message deleted.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("DELETE MESSAGE ERROR")
        flash("Unable to delete message. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))



if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").strip().lower() in ("1", "true", "yes")
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "127.0.0.1" if debug_mode else "0.0.0.0")
    app.run(debug=debug_mode, host=host, port=port)

