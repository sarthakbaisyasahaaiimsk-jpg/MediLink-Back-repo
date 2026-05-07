"""
routes/news.py  —  RSS aggregator for MediLink
Install:  pip install feedparser
Register: from routes.news import news_bp
          app.register_blueprint(news_bp, url_prefix="/api")
"""

import feedparser
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from extensions import db
from sqlalchemy import text
from flask_jwt_extended import jwt_required

news_bp = Blueprint("news", __name__)

# ─── RSS feed registry ────────────────────────────────────────────────────────
RSS_FEEDS = [
    {
        "source": "WHO",
        "url": "https://www.who.int/rss-feeds/news-english.xml",
    },
    {
        "source": "CDC",
        "url": "https://tools.cdc.gov/api/v2/resources/media/316422.rss",
    },
    {
        "source": "NIH",
        "url": "https://www.nih.gov/news-releases/feed.xml",
    },
    {
        "source": "NICE",
        "url": "https://www.nice.org.uk/guidance/published/feed",
    },
    {
        "source": "MOHFW",
        "url": "https://news.google.com/rss/search?q=Ministry+of+Health+India+MOHFW&hl=en-IN&gl=IN&ceid=IN:en",
        "fallback_url": "https://mohfw.gov.in/rss.xml",
    },
    {
        "source": "ICMR",
        "url": "https://news.google.com/rss/search?q=ICMR+Indian+Council+Medical+Research&hl=en-IN&gl=IN&ceid=IN:en"
        "fallback_url": "https://www.icmr.gov.in/rss.xml",
    },
    {
        "source": "Hindu Health",
        "url": "https://www.thehindu.com/sci-tech/health/feeder/default.rss",
    },
]


# ─── DB helpers ───────────────────────────────────────────────────────────────

def ensure_table():
    """Create news_articles table if it doesn't exist yet (runs once at startup)."""
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS news_articles (
            id           SERIAL PRIMARY KEY,
            source       VARCHAR(100),
            title        TEXT,
            url          TEXT UNIQUE,
            published_at TIMESTAMP WITH TIME ZONE,
            summary      TEXT,
            fetched_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))
    db.session.commit()


def upsert_article(source: str, title: str, url: str, published_at, summary: str):
    """Insert article if url not already stored. Silently skips duplicates."""
    db.session.execute(text("""
        INSERT INTO news_articles (source, title, url, published_at, summary)
        VALUES (:source, :title, :url, :published_at, :summary)
        ON CONFLICT (url) DO NOTHING
    """), {
        "source":       source,
        "title":        (title or "")[:500],
        "url":          url,
        "published_at": published_at,
        "summary":      (summary or "")[:2000],
    })


def parse_date(entry) -> datetime | None:
    """Try to pull a timezone-aware datetime out of a feedparser entry."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return None


# ─── Core fetch logic (also called by cron) ───────────────────────────────────

def fetch_and_store_all():
    """
    Pull every RSS feed, store new articles.
    Returns a dict with per-source counts.
    Call this from your cron job:
        from routes.news import fetch_and_store_all
        with app.app_context():
            fetch_and_store_all()
    """
    ensure_table()
    results = {}

    for feed_cfg in RSS_FEEDS:
        source = feed_cfg["source"]
        added  = 0
        errors = 0

        try:
            feed = feedparser.parse(feed_cfg["url"])
            for entry in feed.entries:
                url = getattr(entry, "link", None)
                if not url:
                    continue

                title   = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                pub     = parse_date(entry)

                try:
                    upsert_article(source, title, url, pub, summary)
                    added += 1
                except Exception:
                    db.session.rollback()
                    errors += 1

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            errors += 1
            print(f"[news] Error fetching {source}: {e}")

        results[source] = {"added": added, "errors": errors}

    return results


# ─── Routes ───────────────────────────────────────────────────────────────────

@news_bp.route("/news", methods=["GET"])
@jwt_required()
def get_news():
    """
    GET /api/news
    Query params:
      source  — filter by source name (case-insensitive: WHO, CDC, NIH, NICE, MOHFW, ICMR, Hindu Health)
      limit   — max articles (default 60, max 200)
      offset  — pagination offset
    """
    # FIX: preserve original casing from the request; use UPPER() in SQL for
    # case-insensitive comparison so "Hindu Health" and "HINDU HEALTH" both match.
    source = request.args.get("source", "").strip()
    limit  = min(int(request.args.get("limit",  60)), 200)
    offset = int(request.args.get("offset", 0))

    try:
        ensure_table()

        # FIX: case-insensitive WHERE clause so filtering works regardless of
        # how the source name is cased in the DB or the request parameter.
        where  = "WHERE UPPER(source) = UPPER(:source)" if source else ""
        params = {"limit": limit, "offset": offset}
        if source:
            params["source"] = source

        rows = db.session.execute(text(f"""
            SELECT id, source, title, url, published_at, summary
            FROM   news_articles
            {where}
            ORDER  BY published_at DESC NULLS LAST
            LIMIT  :limit OFFSET :offset
        """), params).fetchall()

        articles = [
            {
                "id":           r.id,
                "source":       r.source,
                "title":        r.title,
                "url":          r.url,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "summary":      r.summary,
            }
            for r in rows
        ]
        return jsonify(articles), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@news_bp.route("/news/refresh", methods=["POST"])
@jwt_required()
def refresh_news():
    """
    POST /api/news/refresh
    Manually trigger an RSS fetch. Useful during development.
    In production, use a cron job instead (see fetch_news.py).
    """
    try:
        results = fetch_and_store_all()
        total   = sum(v["added"] for v in results.values())
        return jsonify({"message": f"Fetched {total} new articles", "details": results}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500