# Community Hackathon - Render Deployment Guide

This guide walks you through deploying the **Community Hackathon Application** on [Render](https://render.com) with a cloud MySQL database.

---

## Architecture Overview

- **Web Service**: Render (Python 3.11+, Gunicorn WSGI, Flask)
- **Database**: Remote Cloud MySQL (TiDB Cloud Serverless, Aiven, or Railway)
- **Static & PDF Assets**: Handled in-process via ReportLab & Flask

---

## Step 1: Set Up a Free Cloud MySQL Database

Render provides managed PostgreSQL natively, but this application uses MySQL. You can use any of these fast, free cloud MySQL providers:

### Option A: TiDB Cloud Serverless (Recommended - Free Forever)
1. Sign up at [tidbcloud.com](https://tidbcloud.com/).
2. Create a free **Serverless Tier** cluster (takes 30 seconds).
3. Under **Overview** -> **Connect**, select **General** connection details to copy:
   - **Host**: e.g., `gateway01.us-east-1.prod.aws.tidbcloud.com`
   - **Port**: `4000`
   - **User**: e.g., `xxxxxx.root`
   - **Password**: Your generated password
   - **Database**: `test` (or create a database named `community_hackathon`)

### Option B: Aiven for MySQL (Free Trial / Tier)
1. Sign up at [aiven.io](https://aiven.io/).
2. Create a MySQL service and copy the Host, Port, User, Password, and DB Name.

### Option C: Railway MySQL
1. Sign up at [railway.app](https://railway.app/).
2. Click **New Project** -> **Provision MySQL**.
3. Under the **Connect** tab, copy the individual credentials or the `MYSQL_URL`.

---

## Step 2: Initialize Database Tables & Problem Statements

Before starting the web app, populate the database tables:

1. On your local machine, open your `.env` file (or set temporary environment variables) with the remote database credentials:
   ```env
   DB_HOST=your-cloud-host.com
   DB_PORT=3306 (or 4000 for TiDB)
   DB_USER=your-user
   DB_PASSWORD=your-password
   DB_NAME=community_hackathon
   DB_SSL_DISABLED=false
   DB_SSL_VERIFY_CERT=false
   ```
2. Run the initialization script:
   ```bash
   python init_db.py
   ```
   This automatically creates all tables from `database/schema.sql` and loads the initial problem statements.

3. Create your secure admin account:
   ```bash
   python create_admin.py
   ```
   Follow the prompts to specify your admin name, email, and password.

*(Alternatively, you can run these commands inside Render's web **Shell** tab after the service is created).*

---

## Step 3: Deploy to Render

### Method 1: Using the Render Blueprint (`render.yaml`) - Quickest
1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** -> **Blueprint**.
3. Connect your repository: `https://github.com/sarthak110306/cep`.
4. Render will detect `render.yaml` automatically.
5. Fill in the prompted database environment variables (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`).
6. Click **Apply**. Render will automatically build and deploy the app!

---

### Method 2: Manual Web Service Setup
1. On the Render Dashboard, click **New +** -> **Web Service**.
2. Connect your GitHub repository: `sarthak110306/cep`.
3. Configure settings:
   - **Name**: `community-hackathon`
   - **Region**: Choose closest to you (e.g., Oregon, Frankfurt, Singapore)
   - **Branch**: `main`
   - **Root Directory**: leave empty
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Instance Type**: `Free`
4. Expand **Advanced** -> **Add Environment Variable**:

| Variable | Value | Notes |
| :--- | :--- | :--- |
| `SECRET_KEY` | *(Click "Generate" or paste random string)* | Required |
| `SESSION_COOKIE_SECURE` | `true` | Required for HTTPS |
| `FLASK_DEBUG` | `false` | Production mode |
| `DB_HOST` | `your-db-host.com` | Remote DB host |
| `DB_PORT` | `3306` (or `4000`) | Remote DB port |
| `DB_USER` | `your-db-user` | Remote DB username |
| `DB_PASSWORD` | `your-db-password` | Remote DB password |
| `DB_NAME` | `community_hackathon` | Remote DB name |
| `DB_SSL_DISABLED` | `false` | Enable TLS/SSL |
| `DB_SSL_VERIFY_CERT` | `false` | Relax cloud CA verification |

5. Click **Create Web Service**.

---

## Step 4: Verify Deployment

1. Once Render finishes building, you will see a green **Live** badge.
2. Click on the URL provided by Render (e.g., `https://community-hackathon.onrender.com`).
3. Verify:
   - Landing page loads properly.
   - User registration and login work.
   - Admin login (`/admin/login`) functions with the admin user created in Step 2.
   - PDF ticket generation and problem statement browsing work as expected.
