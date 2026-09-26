# Community Hackathon - Render & Supabase Production Deployment Guide

This guide walks you through deploying the **Community Hackathon Application** on [Render](https://render.com) using your **Supabase PostgreSQL** backend, complete with automated keep-alive configurations so the service never sleeps on the free plan.

---

## 1. Architecture Overview

- **Web Server**: Render Free Plan (Python 3.11+, Gunicorn WSGI, Flask)
- **Database**: Supabase PostgreSQL (`db.pfphsnbguxoybnmnogcx.supabase.co:5432/postgres`)
- **Backend APIs**: Supabase REST / Auth (`https://pfphsnbguxoybnmnogcx.supabase.co`)
- **Anti-Sleep Keep-Alive**: Multi-layer pinger (GitHub Actions + in-app daemon + `keep_alive.py`)

---

## 2. Supabase Database Status

All 16 tables and seed data have been initialized on your Supabase project:
- `users`, `admins`, `problem_statements`, `user_problem_selections`
- `teams`, `team_members`, `registrations`, `judges_mentors`
- `events`, `faqs`, `contact_messages`, `user_judge_selections`
- `user_event_selections`, `user_faq_selections`, `user_faq_messages`, `certificates`

To create an admin account on the Supabase database:
```bash
python create_admin.py
```

---

## 3. Deploy to Render

### Method 1: Deploy with Blueprint (`render.yaml`) - 1 Click
1. Go to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Blueprint**.
3. Select your repository: `https://github.com/sarthak110306/cep`.
4. Render reads `render.yaml` and pre-populates all configurations and Supabase credentials automatically.
5. Click **Apply**. Render will build and deploy the web service immediately!

---

### Method 2: Manual Web Service Setup
1. Click **New +** -> **Web Service**.
2. Connect `sarthak110306/cep`.
3. Configure settings:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **Health Check Path**: `/healthz`
4. Add Environment Variables:
   - `DATABASE_URL`: `postgresql://postgres:sarthak%402026V@db.pfphsnbguxoybnmnogcx.supabase.co:5432/postgres`
   - `SUPABASE_URL`: `https://pfphsnbguxoybnmnogcx.supabase.co`
   - `SUPABASE_KEY`: `sb_publishable_jY1aBwwwf6SkDKq-Jxet7A_YHm4-PV9`
   - `SESSION_COOKIE_SECURE`: `true`
   - `FLASK_DEBUG`: `false`
   - `RENDER_EXTERNAL_URL`: `https://your-service-name.onrender.com`

---

## 4. Preventing Render Free Tier From Sleeping

Render spins down free web services after 15 minutes of inactivity. We have provided three automatic solutions:

### Solution 1: Automated GitHub Actions Pinger (Cloud-based, 24/7)
The repository includes `.github/workflows/keep_alive.yml`.
1. Once deployed, note your Render URL (e.g. `https://community-hackathon.onrender.com`).
2. In your GitHub repository: go to **Settings** -> **Secrets and variables** -> **Actions**.
3. Add a repository secret named `RENDER_APP_URL` with your Render URL.
4. GitHub Actions will automatically send a GET request to `/healthz` every 12 minutes completely free, keeping Render awake 24/7!

### Solution 2: In-App Self-Pinger Daemon
In Render's dashboard under Environment Variables, set:
```
RENDER_EXTERNAL_URL=https://your-service-name.onrender.com
KEEP_ALIVE_INTERVAL_MINUTES=10
```
The Flask application will automatically start a background thread that pings itself via Render's public router every 10 minutes.

### Solution 3: Free Web Monitor (cron-job.org / UptimeRobot)
1. Sign up for free at [cron-job.org](https://cron-job.org) or [uptimerobot.com](https://uptimerobot.com).
2. Create a new monitor pointing to: `https://your-service-name.onrender.com/healthz`.
3. Set the check interval to **10 minutes**.
4. Save. This will ping your app around the clock with zero maintenance.

### Solution 4: Standalone Python Script
Run locally on your laptop or machine whenever you want:
```bash
python keep_alive.py https://your-service-name.onrender.com
```
