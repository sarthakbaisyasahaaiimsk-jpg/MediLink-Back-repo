
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import SavedReference
import requests
import xml.etree.ElementTree as ET

references_bp = Blueprint("references", __name__)

PUBMED_SEARCH = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
)
PUBMED_FETCH = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
)

CORS_ORIGINS = [
    "http://localhost:5173",
    "https://medilink-front-repo.onrender.com",
]


def fetch_pubmed(query, max_results=15, retstart=0, sort="relevance"):
    """Search PubMed and preserve the PMID order returned by ESearch."""

    max_results = max(1, min(int(max_results), 100))
    retstart = max(0, int(retstart))

    sort_value = {
        "relevance": "relevance",
        "pub_date": "pub date",
    }.get(sort, "relevance")

    search_response = requests.get(
        PUBMED_SEARCH,
        params={
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results,
            "retstart": retstart,
            "sort": sort_value,
            "tool": "medilink",
        },
        timeout=20,
    )
    search_response.raise_for_status()

    search_data = search_response.json()["esearchresult"]
    total = int(search_data.get("count", 0))
    ids = search_data.get("idlist", [])

    if not ids:
        return [], total

    fetch_response = requests.get(
        PUBMED_FETCH,
        params={
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml",
            "rettype": "abstract",
        },
        timeout=30,
    )
    fetch_response.raise_for_status()

    root = ET.fromstring(fetch_response.content)
    papers_by_pmid = {}

    for article in root.findall(".//PubmedArticle"):
        pmid = (
            article.findtext("./MedlineCitation/PMID") or ""
        ).strip()

        article_node = article.find(
            "./MedlineCitation/Article"
        )

        if not pmid or article_node is None:
            continue

        title_node = article_node.find("ArticleTitle")
        title = (
            "".join(title_node.itertext()).strip()
            if title_node is not None
            else ""
        )

        abstract_parts = []
        for abstract_node in article_node.findall(
            "./Abstract/AbstractText"
        ):
            text = "".join(abstract_node.itertext()).strip()
            label = abstract_node.attrib.get("Label")

            if text:
                abstract_parts.append(
                    f"{label}: {text}" if label else text
                )

        authors = []
        author_list = article_node.find("./AuthorList")

        if author_list is not None:
            for author in author_list.findall("./Author")[:3]:
                last_name = author.findtext("LastName") or ""
                initials = author.findtext("Initials") or ""
                collective = author.findtext("CollectiveName") or ""

                name = (
                    collective
                    or f"{last_name} {initials}".strip()
                )

                if name:
                    authors.append(name)

        pub_date = article_node.find(
            "./Journal/JournalIssue/PubDate"
        )
        year = ""

        if pub_date is not None:
            year = (
                pub_date.findtext("Year")
                or pub_date.findtext("MedlineDate")
                or ""
            )

        papers_by_pmid[pmid] = {
            "pmid": pmid,
            "title": title,
            "abstract": " ".join(abstract_parts),
            "authors": ", ".join(authors),
            "year": year,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        }

    # EFetch XML ordering may differ from the ESearch ID ordering.
    papers = [
        papers_by_pmid[pmid]
        for pmid in ids
        if pmid in papers_by_pmid
    ]

    return papers, total


@references_bp.route("/search", methods=["POST", "OPTIONS"])
@cross_origin(
    origins=CORS_ORIGINS,
    supports_credentials=True,
)
def search_references():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()

    try:
        page = max(1, int(data.get("page", 1)))
        retmax = max(1, min(int(data.get("retmax", 15)), 100))
    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid page or result limit"
        }), 400

    sort = data.get("sort", "relevance")
    if sort not in ("relevance", "pub_date"):
        sort = "relevance"

    if not query:
        return jsonify({"error": "Query is required"}), 400

    retstart = (page - 1) * retmax

    try:
        papers, total = fetch_pubmed(
            query=query,
            max_results=retmax,
            retstart=retstart,
            sort=sort,
        )
    except requests.RequestException:
        return jsonify({
            "error": "Unable to reach PubMed. Please try again."
        }), 502
    except (ValueError, KeyError, ET.ParseError):
        return jsonify({
            "error": "PubMed returned an invalid response."
        }), 502

    return jsonify({
        "results": papers,
        "query": query,
        "total": total,
        "page": page,
        "sort": sort,
        "has_more": (retstart + retmax) < total,
    })


# Keep your existing save, unsave, and saved-library routes below.
# Their database fields and authentication behavior should remain unchanged.
