"""
Render Keep-Alive Pinger Script.

Render free tier Web Services automatically spin down after 15 minutes of inactivity.
This script periodically sends an HTTP GET request to your Render app's /healthz endpoint
(every 10-12 minutes) to keep the instance active and responsive 24/7.

Usage:
    python keep_alive.py https://your-app-name.onrender.com
    # or set the RENDER_URL environment variable:
    python keep_alive.py
"""
import os
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("Error: 'requests' module not found. Install it with: pip install requests")
    sys.exit(1)


def ping_server(url):
    target = url.rstrip("/")
    if not (target.endswith("/healthz") or target.endswith("/ping")):
        target = f"{target}/healthz"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        start = time.time()
        resp = requests.get(target, timeout=20)
        elapsed = round((time.time() - start) * 1000)
        print(f"[{now}] Pinged {target} -> Status: {resp.status_code} ({elapsed}ms)")
        return resp.status_code == 200
    except Exception as exc:
        print(f"[{now}] Ping to {target} failed: {exc}")
        return False


def main():
    if len(sys.argv) > 1:
        target_url = sys.argv[1].strip()
    else:
        target_url = os.getenv("RENDER_URL") or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("APP_URL")

    if not target_url:
        print("Usage: python keep_alive.py <RENDER_APP_URL>")
        print("Example: python keep_alive.py https://community-hackathon.onrender.com")
        print("\nOr set the RENDER_URL environment variable.")
        sys.exit(1)

    interval_minutes = int(os.getenv("PING_INTERVAL_MINUTES", "10"))
    interval_seconds = interval_minutes * 60

    print("=" * 65)
    print(" Render Free Tier Keep-Alive Pinger Active")
    print(f" Target URL : {target_url}")
    print(f" Interval   : Every {interval_minutes} minutes")
    print(" Press Ctrl+C to stop.")
    print("=" * 65)

    # Initial ping
    ping_server(target_url)

    while True:
        try:
            time.sleep(interval_seconds)
            ping_server(target_url)
        except KeyboardInterrupt:
            print("\nKeep-alive pinger stopped by user.")
            break


if __name__ == "__main__":
    main()
