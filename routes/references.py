
import os
import logging
import requests
import xml.etree.ElementTree as ET

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import cross_origin
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import SavedReference, User


# --------------------------------------------------
# BLUEPRINT CONFIGURATION
# --------------------------------------------------

references_bp = Blueprint("references", __name__)

CORS_ORIGINS = [
    "http://localhost:5173",
    "https://medilink-front-repo.onrender.com",
]

NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY")

logger = logging.getLogger(__name__)


# --------------------------------------------------
# AUTHENTICATED USER HELPER
# --------------------------------------------------

def get_current_reference_user():
    """
    Resolve the JWT identity to an existing User.

    Supports identities represented as:
    - Numeric user ID
    - Numeric string user ID
    - Email address
    - Dictionary containing id, user_id, or email
    """

    identity = get_jwt_identity()

    if identity is None:
        return None

    if isinstance(identity, dict):
        user_id = identity.get("id") or identity.get("user_id")
        email = identity.get("email")

        if user_id is not None:
            try:
                user = db.session.get(User, int(user_id))
                if user:
                    return user
            except (ValueError, TypeError):
                pass

        if email:
            return User.query.filter_by(email=email).first()

        return None

    try:
        user_id = int(identity)
        user = db.session.get(User, user_id)

        if user:
            return user
    except (ValueError, TypeError):
        pass

    if isinstance(identity, str):
        return User.query.filter_by(email=identity).first()

    return None


# --------------------------------------------------
# PUBMED SEARCH HELPERS
# --------------------------------------------------

def _get_text(element, path, default=""):
    """Safely extract text from an XML element."""

    if element is None:
        return default

    found = element.find(path)

    if found is None:
        return default

    return "".join(found.itertext()).strip() or default


def _parse_pubmed_article(article):
    """Convert a PubMed XML article into the frontend paper format."""

    pmid = _get_text(article, ".//MedlineCitation/PMID")

    article_node = article.find(".//MedlineCitation/Article")

    title = _get_text(
        article_node,
        "ArticleTitle",
        "Untitled article"
    )

    authors = []

    author_list = (
        article_node.find("AuthorList")
        if article_node is not None
        else None
    )

    if author_list is not None:
        for author in author_list.findall("Author"):
            collective_name = _get_text(author, "CollectiveName")

            if collective_name:
                authors.append(collective_name)
                continue

            last_name = _get_text(author, "LastName")
            fore_name = _get_text(author, "ForeName")
            initials = _get_text(author, "Initials")

            full_name = " ".join(
                part for part in [fore_name or initials, last_name]
                if part
            )

            if full_name:
                authors.append(full_name)

    abstract_parts = []

    if article_node is not None:
        abstract_node = article_node.find("Abstract")

        if abstract_node is not None:
            for abstract_section in abstract_node.findall("AbstractText"):
                section_text = "".join(
                    abstract_section.itertext()
                ).strip()

                label = abstract_section.attrib.get("Label")

                if section_text:
                    if label:
                        abstract_parts.append(
                            f"{label}: {section_text}"
                        )
                    else:
                        abstract_parts.append(section_text)

    abstract = " ".join(abstract_parts)

    year = ""

    if article_node is not None:
        journal_issue = article_node.find("Journal/JournalIssue/PubDate")

        if journal_issue is not None:
            year = _get_text(journal_issue, "Year")

            if not year:
                medline_date = _get_text(
                    journal_issue,
                    "MedlineDate"
                )

                if medline_date:
                    year = medline_date[:4]

    if not year and article_node is not None:
        history = article_node.find("Journal/JournalIssue")

        if history is not None:
            year = _get_text(history, ".//PubDate/Year")

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "year": year,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


# --------------------------------------------------
# SEARCH PUBMED
# POST /api/references/search
# --------------------------------------------------

@references_bp.route("/search", methods=["POST", "OPTIONS"])
@cross_origin(
    origins=CORS_ORIGINS,
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization"],
    methods=["POST", "OPTIONS"],
)
def search_references():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}

    query = str(data.get("query", "")).strip()

    if not query:
        return jsonify({"error": "Search query is required"}), 400

    try:
        page = max(1, int(data.get("page", 1)))
        retmax = min(100, max(1, int(data.get("retmax", 15))))
    except (ValueError, TypeError):
        return jsonify({
            "error": "Page and retmax must be valid integers"
        }), 400

    sort = str(data.get("sort", "relevance")).lower()

    # PubMed supports relevance and date ordering.
    sort_options = {
        "relevance": "relevance",
        "date": "date",
        "pub_date": "date",
    }

    sort = sort_options.get(sort, "relevance")
    start = (page - 1) * retmax

    params = {
        "db": "pubmed",
        "term": query,
        "retstart": start,
        "retmax": retmax,
        "sort": sort,
        "retmode": "json",
    }

    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    try:
        search_response = requests.get(
            f"{NCBI_BASE_URL}/esearch.fcgi",
            params=params,
            timeout=20,
        )
        search_response.raise_for_status()
        search_data = search_response.json()

        search_result = search_data.get("esearchresult", {})
        pmids = search_result.get("idlist", [])

        try:
            total = int(search_result.get("count", 0))
        except (ValueError, TypeError):
            total = 0

        if not pmids:
            return jsonify({
                "results": [],
                "query": query,
                "total": total,
                "page": page,
                "sort": sort,
                "has_more": False,
            }), 200

        fetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }

        if NCBI_API_KEY:
            fetch_params["api_key"] = NCBI_API_KEY

        fetch_response = requests.get(
            f"{NCBI_BASE_URL}/efetch.fcgi",
            params=fetch_params,
            timeout=30,
        )
        fetch_response.raise_for_status()

        root = ET.fromstring(fetch_response.content)

        articles = []

        for article in root.findall(".//PubmedArticle"):
            parsed = _parse_pubmed_article(article)

            if parsed["pmid"]:
                articles.append(parsed)

        return jsonify({
            "results": articles,
            "query": query,
            "total": total,
            "page": page,
            "sort": sort,
            "has_more": start + len(pmids) < total,
        }), 200

    except requests.RequestException:
        logger.exception("PubMed request failed")
        return jsonify({
            "error": "Could not connect to PubMed. Please try again."
        }), 502

    except (ValueError, ET.ParseError):
        logger.exception("Could not parse PubMed response")
        return jsonify({
            "error": "Could not process PubMed search results"
        }), 502

    except Exception:
        logger.exception("Unexpected PubMed search error")
        return jsonify({
            "error": "An unexpected error occurred during search"
        }), 500


# --------------------------------------------------
# GET SAVED REFERENCES
# GET /api/references/saved
# --------------------------------------------------

@references_bp.route("/saved", methods=["GET", "OPTIONS"])
@jwt_required()
def get_saved_references():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user = get_current_reference_user()

    if not user:
        return jsonify({"error": "Authenticated user not found"}), 401

    try:
        saved_references = (
            SavedReference.query
            .filter_by(user_id=user.id)
            .order_by(SavedReference.saved_at.desc())
            .all()
        )

        return jsonify({
            "results": [
                reference.to_dict()
                for reference in saved_references
            ]
        }), 200

    except Exception:
        logger.exception("Failed to load saved references")
        return jsonify({
            "error": "Could not load saved references"
        }), 500


# --------------------------------------------------
# SAVE A REFERENCE
# POST /api/references/save
# --------------------------------------------------

@references_bp.route("/save", methods=["POST", "OPTIONS"])
@jwt_required()
def save_reference():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user = get_current_reference_user()

    if not user:
        return jsonify({"error": "Authenticated user not found"}), 401

    paper = request.get_json(silent=True) or {}

    pmid = str(paper.get("pmid", "")).strip()

    if not pmid:
        return jsonify({"error": "Paper PMID is required"}), 400

    try:
        existing = SavedReference.query.filter_by(
            user_id=user.id,
            pmid=pmid,
        ).first()

        if existing:
            return jsonify({
                "message": "Reference already saved",
                "result": existing.to_dict(),
            }), 200

        authors = paper.get("authors", "")

        if isinstance(authors, list):
            authors = ", ".join(
                str(author) for author in authors
            )

        saved_reference = SavedReference(
            user_id=user.id,
            pmid=pmid,
            title=paper.get("title") or "",
            authors=authors or "",
            abstract=paper.get("abstract") or "",
            year=(
                str(paper.get("year"))
                if paper.get("year") is not None
                else ""
            ),
            url=(
                paper.get("url")
                or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            ),
        )

        db.session.add(saved_reference)
        db.session.commit()

        return jsonify({
            "message": "Reference saved successfully",
            "result": saved_reference.to_dict(),
        }), 201

    except IntegrityError:
        db.session.rollback()

        # A concurrent request may have saved this PMID already.
        existing = SavedReference.query.filter_by(
            user_id=user.id,
            pmid=pmid,
        ).first()

        if existing:
            return jsonify({
                "message": "Reference already saved",
                "result": existing.to_dict(),
            }), 200

        return jsonify({
            "error": "Could not save reference"
        }), 500

    except Exception:
        db.session.rollback()
        logger.exception("Failed to save reference")

        return jsonify({
            "error": "Could not save reference"
        }), 500


# --------------------------------------------------
# UNSAVE A REFERENCE
# DELETE /api/references/unsave/<pmid>
# --------------------------------------------------

@references_bp.route(
    "/unsave/<string:pmid>",
    methods=["DELETE", "OPTIONS"],
)
@jwt_required()
def unsave_reference(pmid):
    if request.method == "OPTIONS":
        return jsonify({}), 200

    user = get_current_reference_user()

    if not user:
        return jsonify({"error": "Authenticated user not found"}), 401

    try:
        saved_reference = SavedReference.query.filter_by(
            user_id=user.id,
            pmid=pmid,
        ).first()

        if not saved_reference:
            return jsonify({
                "error": "Saved reference not found"
            }), 404

        db.session.delete(saved_reference)
        db.session.commit()

        return jsonify({
            "message": "Reference removed successfully",
            "pmid": pmid,
        }), 200

    except Exception:
        db.session.rollback()
        logger.exception("Failed to remove saved reference")

        return jsonify({
            "error": "Could not remove reference"
        }), 500
