from flask import Blueprint, request, jsonify, redirect
from flask_cors import cross_origin
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import User, SavedReference
import requests
import os
from requests_oauthlib import OAuth1Session

zotero_bp = Blueprint('zotero', __name__)

CORS_ORIGINS = ["http://localhost:5173", "https://medilink-front-repo.onrender.com"]

CLIENT_KEY    = os.environ.get("ZOTERO_CLIENT_KEY")
CLIENT_SECRET = os.environ.get("ZOTERO_CLIENT_SECRET")
FRONTEND_URL  = os.environ.get("FRONTEND_URL", "http://localhost:5173")

REQUEST_TOKEN_URL = "https://www.zotero.org/oauth/request"
AUTHORIZE_URL     = "https://www.zotero.org/oauth/authorize"
ACCESS_TOKEN_URL  = "https://www.zotero.org/oauth/access"
ZOTERO_API        = "https://api.zotero.org"


def ref_to_csl(ref):
    """Convert a SavedReference to Zotero-compatible CSL-JSON."""
    authors = []
    for name in (ref.authors or "").split(","):
        name = name.strip()
        if not name:
            continue
        parts = name.split(" ", 1)
        authors.append({
            "creatorType": "author",
            "lastName": parts[0] if parts else name,
            "firstName": parts[1] if len(parts) > 1 else ""
        })
    return {
        "itemType": "journalArticle",
        "title": ref.title or "",
        "creators": authors,
        "date": ref.year or "",
        "abstractNote": ref.abstract or "",
        "url": ref.url or "",
        "extra": f"PMID: {ref.pmid}" if ref.pmid else ""
    }


# ── Status check ─────────────────────────────────────────
@zotero_bp.route("/status", methods=["GET", "OPTIONS"])
@cross_origin(origins=CORS_ORIGINS, supports_credentials=True)
@jwt_required()
def zotero_status():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user = User.query.get(get_jwt_identity())
    connected = bool(
        user.zotero_api_key and not user.zotero_api_key.startswith("pending:")
    )
    return jsonify({"connected": connected}), 200


# ── Step 1: Start OAuth — frontend calls this ────────────
@zotero_bp.route("/connect", methods=["GET", "OPTIONS"])
@cross_origin(origins=CORS_ORIGINS, supports_credentials=True)
@jwt_required()
def zotero_connect():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    # Already connected — skip OAuth
    if user.zotero_api_key and not user.zotero_api_key.startswith("pending:"):
        return jsonify({"connected": True}), 200

    callback_url = (
        f"https://medilink-back-repo-1.onrender.com"
        f"/api/zotero/callback?uid={user_id}"
    )

    oauth = OAuth1Session(
        CLIENT_KEY,
        client_secret=CLIENT_SECRET,
        callback_uri=callback_url
    )

    try:
        tokens = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    except Exception as e:
        return jsonify({"error": f"Failed to get request token: {str(e)}"}), 500

    # Store pending token temporarily in the api_key field
    user.zotero_api_key = f"pending:{tokens['oauth_token']}:{tokens['oauth_token_secret']}"
    db.session.commit()

    auth_url = f"{AUTHORIZE_URL}?oauth_token={tokens['oauth_token']}"
    return jsonify({"auth_url": auth_url}), 200


# ── Step 2: Zotero redirects back here ───────────────────
@zotero_bp.route("/callback", methods=["GET"])
def zotero_callback():
    user_id        = request.args.get("uid")
    oauth_verifier = request.args.get("oauth_verifier")

    if not user_id or not oauth_verifier:
        return redirect(f"{FRONTEND_URL}/references?zotero=error")

    user = User.query.get(user_id)
    if not user or not (user.zotero_api_key or "").startswith("pending:"):
        return redirect(f"{FRONTEND_URL}/references?zotero=error")

    try:
        _, req_token, req_secret = user.zotero_api_key.split(":", 2)
    except ValueError:
        return redirect(f"{FRONTEND_URL}/references?zotero=error")

    oauth = OAuth1Session(
        CLIENT_KEY,
        client_secret=CLIENT_SECRET,
        resource_owner_key=req_token,
        resource_owner_secret=req_secret,
        verifier=oauth_verifier
    )

    try:
        tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)
    except Exception:
        return redirect(f"{FRONTEND_URL}/references?zotero=error")

    user.zotero_api_key = tokens["oauth_token"]
    user.zotero_user_id = tokens["userID"]
    db.session.commit()

    return redirect(f"{FRONTEND_URL}/references?zotero=connected")


# ── Step 3: Push selected (or all) refs to Zotero ────────
@zotero_bp.route("/push", methods=["POST", "OPTIONS"])
@cross_origin(origins=CORS_ORIGINS, supports_credentials=True)
@jwt_required()
def zotero_push():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user.zotero_api_key or user.zotero_api_key.startswith("pending:"):
        return jsonify({"error": "Zotero not connected"}), 403

    data  = request.get_json() or {}
    pmids = data.get("pmids")  # optional — if omitted, push all saved refs

    query = SavedReference.query.filter_by(user_id=user_id)
    if pmids:
        query = query.filter(SavedReference.pmid.in_(pmids))
    refs = query.all()

    if not refs:
        return jsonify({"error": "No references found"}), 404

    items = [ref_to_csl(r) for r in refs]

    # Zotero accepts max 50 items per request
    results = []
    for i in range(0, len(items), 50):
        chunk = items[i:i + 50]
        resp = requests.post(
            f"{ZOTERO_API}/users/{user.zotero_user_id}/items",
            json=chunk,
            headers={
                "Zotero-API-Key": user.zotero_api_key,
                "Zotero-API-Version": "3",
                "Content-Type": "application/json"
            }
        )
        if resp.status_code not in (200, 201):
            return jsonify({
                "error": "Zotero API error",
                "detail": resp.text
            }), 502
        results.append(resp.json())

    return jsonify({
        "message": f"{len(items)} reference(s) pushed to Zotero",
        "results": results
    }), 200


# ── Disconnect ────────────────────────────────────────────
@zotero_bp.route("/disconnect", methods=["DELETE", "OPTIONS"])
@cross_origin(origins=CORS_ORIGINS, supports_credentials=True)
@jwt_required()
def zotero_disconnect():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user = User.query.get(get_jwt_identity())
    user.zotero_api_key = None
    user.zotero_user_id = None
    db.session.commit()
    return jsonify({"message": "Disconnected"}), 200