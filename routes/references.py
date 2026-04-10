from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import SavedReference
import requests
import xml.etree.ElementTree as ET

references_bp = Blueprint('references', __name__)

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

CORS_ORIGINS = ["http://localhost:5173", "https://medilink-front-repo.onrender.com"]

def fetch_pubmed(query, max_results=7):
    search_res = requests.get(PUBMED_SEARCH, params={
        "db": "pubmed", "term": query,
        "retmode": "json", "retmax": max_results
    }).json()
    ids = search_res["esearchresult"]["idlist"]
    if not ids:
        return []

    fetch_res = requests.get(PUBMED_FETCH, params={
        "db": "pubmed", "id": ",".join(ids),
        "retmode": "xml", "rettype": "abstract"
    })

    papers = []
    root = ET.fromstring(fetch_res.content)
    for article in root.findall(".//PubmedArticle"):
        title = article.findtext(".//ArticleTitle") or ""
        abstract = article.findtext(".//AbstractText") or ""
        pmid = article.findtext(".//PMID") or ""
        year = article.findtext(".//PubDate/Year") or ""
        authors_els = article.findall(".//Author")
        authors = ", ".join(
            f"{a.findtext('LastName') or ''} {a.findtext('Initials') or ''}".strip()
            for a in authors_els[:3]
        )
        papers.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "year": year,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        })
    return papers


# ── Search ──────────────────────────────────────────────
@references_bp.route("/search", methods=["POST", "OPTIONS"])
@cross_origin(origins=CORS_ORIGINS, supports_credentials=True)
def search_references():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    data = request.get_json()
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400
    papers = fetch_pubmed(query)
    return jsonify({"results": papers, "query": query})


# ── Save a paper ─────────────────────────────────────────
@references_bp.route("/save", methods=["POST", "OPTIONS"])
@cross_origin(origins=CORS_ORIGINS, supports_credentials=True)
@jwt_required()
def save_reference():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user_id = get_jwt_identity()
    data = request.get_json()

    existing = SavedReference.query.filter_by(
        user_id=user_id, pmid=data.get("pmid")
    ).first()
    if existing:
        return jsonify({"message": "Already saved", "id": existing.id}), 200

    ref = SavedReference(
        user_id=user_id,
        pmid=data.get("pmid"),
        title=data.get("title"),
        authors=data.get("authors"),
        abstract=data.get("abstract"),
        year=data.get("year"),
        url=data.get("url"),
    )
    db.session.add(ref)
    db.session.commit()
    return jsonify({"message": "Saved", "id": ref.id}), 201


# ── Unsave a paper ───────────────────────────────────────
@references_bp.route("/unsave/<pmid>", methods=["DELETE", "OPTIONS"])
@cross_origin(origins=CORS_ORIGINS, supports_credentials=True)
@jwt_required()
def unsave_reference(pmid):
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user_id = get_jwt_identity()
    ref = SavedReference.query.filter_by(user_id=user_id, pmid=pmid).first()
    if ref:
        db.session.delete(ref)
        db.session.commit()
    return jsonify({"message": "Removed"}), 200


# ── Get saved library ────────────────────────────────────
@references_bp.route("/saved", methods=["GET", "OPTIONS"])
@cross_origin(origins=CORS_ORIGINS, supports_credentials=True)
@jwt_required()
def get_saved_references():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user_id = get_jwt_identity()
    refs = SavedReference.query.filter_by(user_id=user_id)\
        .order_by(SavedReference.saved_at.desc()).all()

    return jsonify({"results": [{
        "id": r.id,
        "pmid": r.pmid,
        "title": r.title,
        "authors": r.authors,
        "abstract": r.abstract,
        "year": r.year,
        "url": r.url,
        "saved_at": r.saved_at.isoformat()
    } for r in refs]}), 200