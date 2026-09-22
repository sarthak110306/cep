# Community Hackathon for Social Innovation

Flask + MySQL full-stack hackathon registration platform.

## Required Software

- **Python 3.10+**
- **MySQL Server 8.0+** (or MariaDB)
- **VS Code** (recommended)
- **Git** (optional)

## Setup Instructions

### 1. Open Project in VS Code

Open the folder `C:\New folder\fyit18\fyit18` in VS Code.

### 2. Create Virtual Environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Python Packages

```powershell
pip install -r requirements.txt
```

### 4. Configure MySQL Database

1. Start MySQL service
2. Import the schema:

```powershell
mysql -u root -p < database\schema.sql
```

Or use MySQL Workbench to run `database/schema.sql`.

### 5. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your own values:

```powershell
copy .env.example .env
```

```env
SECRET_KEY=change-this-to-a-long-random-value
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=community_hackathon
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USERNAME=
MAIL_PASSWORD=
FLASK_DEBUG=false
SESSION_COOKIE_SECURE=false
```

`FLASK_DEBUG=true` re-enables Flask's debugger for local development only -
never enable it in production. `SESSION_COOKIE_SECURE=true` should only be
set once the app is served over HTTPS (it will otherwise silently prevent
login from working over plain HTTP).

### 6. Run the Application

```powershell
python app.py
```

Open your browser: **http://127.0.0.1:5000**

## Admin Account Setup

This project no longer ships with a hardcoded default admin account
(the previous `admin@hackathon.local` / `admin123` credentials have been
removed - they were a security risk since they were publicly documented
here). After importing the schema, create your own admin account by
running, from the project root:

```powershell
python create_admin.py
```

You'll be prompted for a name, email and password (min 8 characters).
The password is hashed before it's stored - it's never saved in plain
text. Run the same command again with an existing admin's email if you
ever need to reset that admin's password.

Admin dashboard: **http://127.0.0.1:5000/admin/login**

## User Flow

1. Sign up → Login
2. Home → Problem Statements → Select a challenge
3. Team Registration → Event Schedule
4. Registration Summary → Confirm Registration
5. Receive Registration ID (e.g. `HACK2026-00001`)

## Project Structure

```
manus code/
├── app.py                 # Main Flask application
├── config.py              # Configuration (reads .env)
├── create_admin.py        # One-time/reset admin account setup (Issue #4)
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (not committed)
├── .env.example           # Template for .env (no real secrets)
├── database/
│   ├── db.py                    # MySQL connection helper
│   ├── schema.sql               # Database schema + seed data
│   └── migration_security.sql   # Optional cleanup migration (Issue #4)
├── templates/             # Jinja2 HTML templates
│   ├── login.html
│   ├── home.html
│   ├── about.html
│   ├── problem-statements.html
│   ├── problem-detail.html
│   ├── team-registration.html
│   ├── judges-mentors.html
│   ├── event.html
│   ├── gallery.html
│   ├── faq.html
│   ├── contact.html
│   ├── registration-summary.html
│   ├── certificates.html
│   ├── admin-login.html
│   ├── admin-signup.html
│   ├── admin-dashboard.html
│   ├── _nav.html
│   └── _flash.html
├── static/
│   ├── css/               # Stylesheets
│   └── js/                # JavaScript files
└── tests/                 # Automated test suite (Issue #13)
```

## Security Notes

- Passwords are hashed with Werkzeug (never stored in plain text)
- User and admin sessions are separate, with HTTPOnly/SameSite cookies and a 2-hour lifetime
- SQL queries use parameterized statements
- Database credentials are loaded from `.env`, not hardcoded (no default fallback password)
- CSRF protection (Flask-WTF) is enforced on every POST route
- Login/signup/admin-login/admin-signup are rate-limited against brute-force abuse
- There is currently **no "Forgot Password" feature for users**. A previous
  OTP-based implementation was removed; the original pre-OTP implementation
  could not be recovered from this project's history (no git history or
  backup found). Until a replacement is built, a user's password can only
  be reset manually by an admin updating `users.password_hash` directly
  (using `werkzeug.security.generate_password_hash` - never store it in
  plain text).

## Running Tests

From the project root:

```powershell
python -m pytest tests -v
```

See `tests/README_TESTS.md` for what's covered and what requires a live database.

## Troubleshooting

**Database connection error:** Check MySQL is running and `.env` credentials are correct.

**Module not found:** Activate virtual environment and run `pip install -r requirements.txt`.

**Port already in use:** Change port in `app.py`: `app.run(port=5001)`.
