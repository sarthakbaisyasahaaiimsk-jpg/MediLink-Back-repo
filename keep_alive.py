import os
import threading
import time
import requests

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
INTERVAL = 14 * 60  # 14 minutes

def _ping():
    if not RENDER_URL:
        return
    try:
        r = requests.get(f"{RENDER_URL}/health", timeout=10)
        print(f"[keep-alive] pinged → {r.status_code}")
    except Exception as e:
        print(f"[keep-alive] failed → {e}")

def start_keep_alive():
    def loop():
        while True:
            time.sleep(INTERVAL)
            _ping()
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    print("[keep-alive] scheduler started (every 14 min)")