from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import requests
import xml.etree.ElementTree as ET

references_bp = Blueprint('references', __name__)

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

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


@references_bp.route("/search", methods=["POST", "OPTIONS"])
@cross_origin(origins=["http://localhost:5173", "https://medilink-front-repo.onrender.com"], supports_credentials=True)
def search_references():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json()
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400

    papers = fetch_pubmed(query)
    return jsonify({"results": papers, "query": query})