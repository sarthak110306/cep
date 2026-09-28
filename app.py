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

        certificates = cursor.fetchall()

        return render_template(
            "certificates.html",
            certificates=certificates
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

        cursor.execute(
            """
            SELECT name
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (session["user_id"],)
        )

        user = cursor.fetchone()

        participant_name = (
            user["name"]
            if user and user.get("name")
            else "Participant"
        )

        buffer = BytesIO()

        pdf = canvas.Canvas(
            buffer,
            pagesize=A4
        )

        width, height = A4

        # Outer Border
        pdf.setStrokeColor(colors.HexColor("#1f5c42"))
        pdf.setLineWidth(5)
        pdf.rect(
            15 * mm,
            15 * mm,
            width - 30 * mm,
            height - 30 * mm
        )

        # Inner Border
        pdf.setStrokeColor(colors.HexColor("#d9a441"))
        pdf.setLineWidth(2)
        pdf.rect(
            21 * mm,
            21 * mm,
            width - 42 * mm,
            height - 42 * mm
        )

        # Title
        pdf.setFillColor(colors.HexColor("#1f5c42"))
        pdf.setFont("Helvetica-Bold", 30)
        pdf.drawCentredString(
            width / 2,
            height - 65 * mm,
            "CERTIFICATE"
        )

        # Certificate Type
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawCentredString(
            width / 2,
            height - 78 * mm,
            "OF PARTICIPATION"
            if certificate["certificate_type"] == "Participation"
            else "OF ACHIEVEMENT"
        )

        # Main Text
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 13)
        pdf.drawCentredString(
            width / 2,
            height - 105 * mm,
            "This certificate is proudly presented to"
        )

        # Participant Name
        pdf.setFillColor(colors.HexColor("#1f5c42"))
        pdf.setFont("Helvetica-Bold", 25)
        pdf.drawCentredString(
            width / 2,
            height - 120 * mm,
            participant_name
        )

        # Achievement Text
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 12)

        if certificate["certificate_type"] == "Winner":
            pdf.drawCentredString(
                width / 2,
                height - 137 * mm,
                "for achieving"
            )

            pdf.setFillColor(colors.HexColor("#d9a441"))
            pdf.setFont("Helvetica-Bold", 20)

            pdf.drawCentredString(
                width / 2,
                height - 148 * mm,
                certificate["position"] or "Winner"
            )
        else:
            pdf.drawCentredString(
                width / 2,
                height - 137 * mm,
                "for successfully participating in the"
            )

        # Hackathon Name
        pdf.setFillColor(colors.HexColor("#1f5c42"))
        pdf.setFont("Helvetica-Bold", 17)

        pdf.drawCentredString(
            width / 2,
            height - 164 * mm,
            "Community Based Hackathon"
        )

        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 12)

        pdf.drawCentredString(
            width / 2,
            height - 174 * mm,
            "for Social Innovation"
        )

        # Team
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(
            45 * mm,
            67 * mm,
            "Team:"
        )

        pdf.setFont("Helvetica", 11)

        team_name = certificate["team_name"] or "N/A"

        if len(team_name) > 45:
            team_name = team_name[:42] + "..."

        pdf.drawString(
            62 * mm,
            67 * mm,
            team_name
        )

        # Problem Statement
        pdf.setFont("Helvetica-Bold", 11)

        pdf.drawString(
            45 * mm,
            57 * mm,
            "Challenge:"
        )

        pdf.setFont("Helvetica", 10)

        problem = certificate["problem_statement"] or "N/A"

        if len(problem) > 55:
            problem = problem[:52] + "..."

        pdf.drawString(
            68 * mm,
            57 * mm,
            problem
        )

        # Certificate ID
        pdf.setFont("Helvetica-Bold", 10)

        pdf.drawString(
            45 * mm,
            45 * mm,
            "Certificate ID:"
        )

        pdf.setFont("Helvetica", 10)

        pdf.drawString(
            72 * mm,
            45 * mm,
            certificate["certificate_id"]
        )

        # Issue Date
        issued_date = certificate["issued_at"]

        if issued_date:
            issued_date = issued_date.strftime("%d %B %Y")
        else:
            issued_date = "N/A"

        pdf.setFont("Helvetica-Bold", 10)

        pdf.drawString(
            45 * mm,
            37 * mm,
            "Issued Date:"
        )

        pdf.setFont("Helvetica", 10)

        pdf.drawString(
            72 * mm,
            37 * mm,
            issued_date
        )

        # Signature
        pdf.setStrokeColor(colors.HexColor("#1f5c42"))

        pdf.line(
            width - 75 * mm,
            45 * mm,
            width - 35 * mm,
            45 * mm
        )

        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 10)

        pdf.drawCentredString(
            width - 55 * mm,
            37 * mm,
            "Hackathon Organizer"
        )

        # Finish PDF
        pdf.showPage()
        pdf.save()

        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"{certificate_id}.pdf",
            mimetype="application/pdf"
        )

    finally:
        cursor.close()
        conn.close()

@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def admin_login():
    if request.method == "GET":
        if session.get("admin_id"):
            return redirect(url_for("admin_dashboard"))
        return render_template("admin-login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password or len(email) > 150 or len(password) > 200:
        flash("Invalid admin credentials.", "error")
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
        admin = cursor.fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["name"]
            flash("Admin login successful.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "error")
        return redirect(url_for("admin_login"))
    except Exception:
        conn.rollback()
        app.logger.exception("ADMIN LOGIN ERROR")
        flash("Unable to log in right now. Please try again.", "error")
        return redirect(url_for("admin_login"))
    finally:
        cursor.close()
        conn.close()

@app.route("/admin/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def admin_signup():

    if request.method == "GET":
        if session.get("admin_id"):
            return redirect(url_for("admin_dashboard"))

        return render_template("admin-signup.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password:
        flash("Please fill all required fields.", "error")
        return redirect(url_for("admin_signup"))

    if not validate_email(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("admin_signup"))

    if len(name) > 100 or len(email) > 150:
        flash("Name or email is too long.", "error")
        return redirect(url_for("admin_signup"))

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("admin_signup"))

    if len(password) < 6 or len(password) > 200:
        flash("Password must be between 6 and 200 characters.", "error")
        return redirect(url_for("admin_signup"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)

    try:
        cursor.execute(
            "SELECT id FROM admins WHERE email = %s",
            (email,)
        )

        existing_admin = cursor.fetchone()

        if existing_admin:
            flash("An admin with this email already exists.", "error")
            return redirect(url_for("admin_signup"))

        password_hash = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO admins (name, email, password_hash)
            VALUES (%s, %s, %s)
            """,
            (name, email, password_hash)
        )

        conn.commit()

        flash("Admin account created successfully. Please login.", "success")
        return redirect(url_for("admin_login"))

    except Exception:
        conn.rollback()
        app.logger.exception("ADMIN SIGNUP ERROR")
        flash("Error creating admin account. Please try again.", "error")
        return redirect(url_for("admin_signup"))

    finally:
        cursor.close()
        conn.close()

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Admin logged out.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        stats = {}
        for table, key in [
            ("users", "total_users"),
            ("teams", "total_teams"),
            ("registrations", "total_registrations"),
            ("problem_statements", "total_problems"),
            ("contact_messages", "total_messages"),
        ]:
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
            stats[key] = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM judges_mentors WHERE type='Judge'")
        stats["total_judges"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM judges_mentors WHERE type='Mentor'")
        stats["total_mentors"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM contact_messages WHERE is_read=0")
        stats["unread_messages"] = cursor.fetchone()["cnt"]

        cursor.execute(
            """
            SELECT u.id, u.name, u.email, u.created_at
            FROM users u ORDER BY u.created_at DESC LIMIT 50
            """
        )
        users = cursor.fetchall()

        cursor.execute(
            """
            SELECT t.*, ps.title AS problem_title, r.status, r.registration_id,
                   (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id = t.id) AS extra_members
            FROM teams t
            JOIN problem_statements ps ON ps.id = t.problem_statement_id
            LEFT JOIN registrations r ON r.team_id = t.id
            ORDER BY t.created_at DESC
            """
        )
        teams = cursor.fetchall()

        cursor.execute("SELECT * FROM problem_statements ORDER BY id")
        problems = cursor.fetchall()

        cursor.execute("SELECT * FROM judges_mentors ORDER BY type, name")
        judges_mentors_list = cursor.fetchall()

        cursor.execute("SELECT * FROM events ORDER BY event_date, event_time")
        events_list = cursor.fetchall()

        cursor.execute("SELECT * FROM faqs ORDER BY id")
        faqs_list = cursor.fetchall()

        cursor.execute(
            "SELECT * FROM contact_messages ORDER BY created_at DESC"
        )
        messages = cursor.fetchall()

                # Certificates
        cursor.execute(
            """
            SELECT
                c.id,
                c.certificate_id,
                c.certificate_type,
                c.position,
                c.team_name,
                c.problem_statement,
                c.issued_at,
                u.name AS user_name,
                u.email AS user_email
            FROM certificates c
            JOIN users u ON u.id = c.user_id
            ORDER BY c.issued_at DESC
            """
        )
        certificates = cursor.fetchall()

        return render_template(
            "admin-dashboard.html",
            stats=stats,
            users=users,
            teams=teams,
            problems=problems,
            judges_mentors=judges_mentors_list,
            events=events_list,
            faqs=faqs_list,
            messages=messages,
            admin_name=session.get("admin_name"),
                        certificates=certificates,
        )
    finally:
        cursor.close()
        conn.close()

# =========================
# Admin Certificate Route
# =========================

@app.route("/admin/issue-certificate", methods=["POST"])
@admin_required
def admin_issue_certificate():

    user_id = request.form.get("user_id", "").strip()
    certificate_type = request.form.get("certificate_type", "Participation").strip()
    position = request.form.get("position", "").strip()

    if not user_id:
        flash("Please select a user.", "error")
        return redirect(url_for("admin_dashboard"))

    if certificate_type not in ["Participation", "Winner"]:
        flash("Invalid certificate type.", "error")
        return redirect(url_for("admin_dashboard"))

    if certificate_type == "Winner" and not position:
        flash("Please enter the winner position.", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)

    try:
        # Check user
        cursor.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        user = cursor.fetchone()

        if not user:
            flash("User not found.", "error")
            return redirect(url_for("admin_dashboard"))

        # Get user's team and selected problem
        cursor.execute(
            """
            SELECT
                t.team_name,
                ps.title AS problem_title
            FROM teams t
            LEFT JOIN problem_statements ps
                ON t.problem_statement_id = ps.id
            WHERE t.user_id = %s
            ORDER BY t.id DESC
            LIMIT 1
            """,
            (user_id,)
        )

        team = cursor.fetchone()

        team_name = team["team_name"] if team else None
        problem_statement = team["problem_title"] if team else None

        # Generate unique certificate ID
        cursor.execute(
            "SELECT COUNT(*) AS total FROM certificates"
        )

        result = cursor.fetchone()
        total = (result["total"] or 0) + 1

        certificate_id = f"CERT-HACK2026-{total:05d}"

        # Make sure ID is unique
        while True:
            cursor.execute(
                """
                SELECT id
                FROM certificates
                WHERE certificate_id = %s
                LIMIT 1
                """,
                (certificate_id,)
            )

            existing = cursor.fetchone()

            if not existing:
                break

            total += 1
            certificate_id = f"CERT-HACK2026-{total:05d}"

        # Insert certificate
        cursor.execute(
            """
            INSERT INTO certificates
            (
                user_id,
                certificate_id,
                certificate_type,
                position,
                team_name,
                problem_statement
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                certificate_id,
                certificate_type,
                position if certificate_type == "Winner" else None,
                team_name,
                problem_statement
            )
        )

        conn.commit()

        flash(
            f"Certificate {certificate_id} issued successfully to {user['name']}.",
            "success"
        )

    except Exception:
        conn.rollback()
        app.logger.exception("ISSUE CERTIFICATE ERROR")
        flash(
            "Error issuing certificate. Please check the details and try again.",
            "error"
        )

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))
# --- Admin CRUD: Users ---

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        flash("User deleted.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("DELETE USER ERROR")
        flash("Unable to delete user. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


# --- Admin CRUD: Problem Statements ---

@app.route("/admin/problems/add", methods=["POST"])
@admin_required
def admin_add_problem():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    difficulty = request.form.get("difficulty", "Medium").strip()
    technologies = request.form.get("technologies", "").strip()
    social_impact = request.form.get("social_impact", "").strip()

    error = require_admin_fields(
        {"title": title, "category": category, "description": description},
        max_length=2000,
    )
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            """
            INSERT INTO problem_statements
            (title, category, description, difficulty, technologies, social_impact)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (title, category, description, difficulty, technologies, social_impact),
        )
        conn.commit()
        flash("Problem statement added.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("ADD PROBLEM ERROR")
        flash("Unable to add problem statement. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/problems/<int:pid>/edit", methods=["POST"])
@admin_required
def admin_edit_problem(pid):
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    difficulty = request.form.get("difficulty", "").strip()
    technologies = request.form.get("technologies", "").strip()
    social_impact = request.form.get("social_impact", "").strip()

    error = require_admin_fields(
        {"title": title, "category": category, "description": description},
        max_length=2000,
    )
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            """
            UPDATE problem_statements SET title=%s, category=%s, description=%s,
            difficulty=%s, technologies=%s, social_impact=%s WHERE id=%s
            """,
            (title, category, description, difficulty, technologies, social_impact, pid),
        )
        conn.commit()
        flash("Problem statement updated.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("EDIT PROBLEM ERROR")
        flash("Unable to update problem statement. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/problems/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_delete_problem(pid):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        # Issue #7: a problem statement that has already been selected by a
        # team cannot be removed without breaking referential integrity
        # (teams.problem_statement_id has a foreign key with no cascade).
        # Check for references first and give a clear message instead of
        # letting the FK error bubble up as a raw 500.
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM teams WHERE problem_statement_id = %s",
            (pid,),
        )
        in_use = cursor.fetchone()["cnt"] > 0

        if in_use:
            flash(
                "This problem statement is already selected by one or more "
                "registered teams and cannot be deleted. Edit it instead, "
                "or reassign/remove the affected teams first.",
                "error",
            )
            return redirect(url_for("admin_dashboard"))

        cursor.execute("DELETE FROM problem_statements WHERE id = %s", (pid,))
        conn.commit()
        flash("Problem statement deleted.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("DELETE PROBLEM STATEMENT ERROR")
        flash("Unable to delete this problem statement. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


# --- Admin CRUD: Judges & Mentors ---

@app.route("/admin/judges-mentors/add", methods=["POST"])
@admin_required
def admin_add_judge_mentor():
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "").strip()
    organization = request.form.get("organization", "").strip()
    expertise = request.form.get("expertise", "").strip()
    experience = request.form.get("experience", "").strip()
    bio = request.form.get("bio", "").strip()
    image = request.form.get("image", "").strip()
    jm_type = request.form.get("type", "").strip()

    error = require_admin_fields({"name": name, "role": role, "type": jm_type})
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            """
            INSERT INTO judges_mentors
            (name, role, organization, expertise, experience, bio, image, type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (name, role, organization, expertise, experience, bio, image, jm_type),
        )
        conn.commit()
        flash("Judge/Mentor added.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("ADD JUDGE/MENTOR ERROR")
        flash("Unable to add judge/mentor. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/judges-mentors/<int:jid>/edit", methods=["POST"])
@admin_required
def admin_edit_judge_mentor(jid):
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "").strip()
    organization = request.form.get("organization", "").strip()
    expertise = request.form.get("expertise", "").strip()
    experience = request.form.get("experience", "").strip()
    bio = request.form.get("bio", "").strip()
    image = request.form.get("image", "").strip()
    jm_type = request.form.get("type", "").strip()

    error = require_admin_fields({"name": name, "role": role, "type": jm_type})
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute(
            """
            UPDATE judges_mentors SET name=%s, role=%s, organization=%s,
            expertise=%s, experience=%s, bio=%s, image=%s, type=%s WHERE id=%s
            """,
            (name, role, organization, expertise, experience, bio, image, jm_type, jid),
        )
        conn.commit()
        flash("Judge/Mentor updated.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("EDIT JUDGE/MENTOR ERROR")
        flash("Unable to update judge/mentor. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/judges-mentors/<int:jid>/delete", methods=["POST"])
@admin_required
def admin_delete_judge_mentor(jid):
    conn = get_db_connection()
    cursor = dict_cursor(conn)
    try:
        cursor.execute("DELETE FROM judges_mentors WHERE id = %s", (jid,))
        conn.commit()
        flash("Judge/Mentor deleted.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("DELETE JUDGE/MENTOR ERROR")
        flash("Unable to delete judge/mentor. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


# --- Admin CRUD: Events ---

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

