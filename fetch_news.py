"""
fetch_news.py  —  standalone cron script
Run manually:  python fetch_news.py
Add to crontab (every hour):
    0 * * * * cd /path/to/your/backend && python fetch_news.py >> logs/news.log 2>&1
"""

from dotenv import load_dotenv
load_dotenv()

from app import app
from routes.news import fetch_and_store_all
from datetime import datetime

with app.app_context():
    print(f"[{datetime.now().isoformat()}] Starting RSS fetch...")
    results = fetch_and_store_all()
    for source, info in results.items():
        print(f"  {source}: +{info['added']} new  ({info['errors']} errors)")
    print("Done.")