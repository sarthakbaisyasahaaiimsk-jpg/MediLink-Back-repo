from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import requests
import re

drugs_bp = Blueprint('drugs', __name__)

OPENFDA_URL = "https://api.fda.gov/drug"
RXNORM_URL  = "https://rxnav.nlm.nih.gov/REST"


# ── Helpers ──────────────────────────────────────────────
def safe_get(data, *keys, default=""):
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        elif isinstance(data, list):
            if isinstance(key, int):
                data = data[key] if len(data) > key else default
            else:
                data = data[0] if data else default
        else:
            return default
    return data or default


def normalize(text):
    """Lowercase + strip punctuation/spaces for loose comparison."""
    if not text:
        return ""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def name_matches(query, candidate):
    """
    Returns True if the candidate drug name is a genuine match for the query.
    Uses token-based inclusion rather than full-string equality to handle
    things like 'metformin' matching 'METFORMIN HYDROCHLORIDE'.
    """
    if not query or not candidate:
        return False

    q = normalize(query)
    c = normalize(candidate)

    # Exact match
    if q == c:
        return True

    # Query is contained in candidate (e.g. 'metformin' in 'metforminhydrochloride')
    if q in c:
        return True

    # Candidate starts with query (handles prefix matches)
    if c.startswith(q):
        return True

    # Check individual tokens in the query against candidate
    # e.g. 'atorvastatin calcium' → tokens ['atorvastatin', 'calcium']
    q_tokens = re.sub(r'[^a-z0-9\s]', '', query.lower()).split()
    if q_tokens and normalize(q_tokens[0]) in c:
        return True

    return False


def best_fda_result(results, query):
    """
    From a list of OpenFDA label results, return the one whose
    generic_name / brand_name / substance_name best matches the query.
    Returns None if no result is a genuine match.
    """
    if not results:
        return None

    for r in results:
        openfda = r.get("openfda", {})

        candidates = []
        for field in ("generic_name", "substance_name", "brand_name"):
            val = openfda.get(field, [])
            if isinstance(val, list):
                candidates.extend(val)
            elif val:
                candidates.append(val)

        for candidate in candidates:
            if name_matches(query, candidate):
                return r

    return None


# ── Search drugs ─────────────────────────────────────────
@drugs_bp.route("/search", methods=["GET"])
@jwt_required()
def search_drugs():
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 10)), 50)

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        rxnorm_resp = requests.get(
            f"{RXNORM_URL}/drugs.json",
            params={"name": query},
            timeout=8
        )

        results = []

        if rxnorm_resp.status_code == 200:
            rx_data = rxnorm_resp.json()
            drug_group = rx_data.get("drugGroup", {})
            concept_groups = drug_group.get("conceptGroup", [])

            seen = set()
            for group in concept_groups:
                for concept in group.get("conceptProperties", []):
                    name  = concept.get("name", "")
                    rxcui = concept.get("rxcui", "")
                    tty   = concept.get("tty", "")

                    key = (name.lower(), tty)
                    if key not in seen and tty in ("IN", "BN", "SBD", "SCD", "MIN"):
                        seen.add(key)
                        results.append({
                            "rxcui": rxcui,
                            "name":  name,
                            "type":  "Brand" if tty == "BN" else "Generic"
                        })

            results = results[:limit]

        return jsonify({"results": results, "query": query}), 200

    except Exception as e:
        return jsonify({"error": "RxNorm API failure"}), 502


# ── Drug detail ──────────────────────────────────────────
@drugs_bp.route("/detail", methods=["GET"])
@jwt_required()
def drug_detail():
    name  = request.args.get("name", "").strip()
    rxcui = request.args.get("rxcui", "").strip()

    if not name and not rxcui:
        return jsonify({"error": "name or rxcui is required"}), 400

    result = {}

    try:
        fda_result = None

        # ── Strategy 1: RxCUI lookup (most precise) ──────
        # Always try this first — it's a direct ID match, never wrong
        if rxcui:
            try:
                resp = requests.get(
                    f"{OPENFDA_URL}/label.json",
                    params={"search": f'openfda.rxcui:"{rxcui}"', "limit": 5},
                    timeout=8
                )
                if resp.status_code == 200:
                    fda_result = best_fda_result(resp.json().get("results", []), name or rxcui)
            except Exception:
                pass

        # ── Strategy 2: Exact generic name match ─────────
        # Only runs if rxcui lookup didn't find a verified match
        if not fda_result and name:
            # Use the FULL name the user searched — don't strip/mangle it
            search_name = name.strip()

            for field in ("openfda.generic_name", "openfda.substance_name", "openfda.brand_name"):
                try:
                    resp = requests.get(
                        f"{OPENFDA_URL}/label.json",
                        params={
                            # Fetch more results so best_fda_result can pick the right one
                            "search": f'{field}:"{search_name}"',
                            "limit": 5
                        },
                        timeout=8
                    )
                    if resp.status_code == 200:
                        candidate = best_fda_result(resp.json().get("results", []), search_name)
                        if candidate:
                            fda_result = candidate
                            break
                except Exception:
                    continue

        # ── Strategy 3: First-word fallback ONLY if both above failed ──
        # Deliberately narrow — only try the first meaningful token
        if not fda_result and name:
            first_word = name.strip().split()[0]
            # Skip single-character tokens and very short words
            if len(first_word) >= 4:
                try:
                    resp = requests.get(
                        f"{OPENFDA_URL}/label.json",
                        params={
                            "search": f'openfda.generic_name:"{first_word}"',
                            "limit": 5
                        },
                        timeout=8
                    )
                    if resp.status_code == 200:
                        # Still verify — first_word must match the returned drug
                        candidate = best_fda_result(resp.json().get("results", []), first_word)
                        if candidate:
                            fda_result = candidate
                except Exception:
                    pass

        # ── Parse the verified OpenFDA result ────────────
        if fda_result:
            r = fda_result
            openfda = r.get("openfda", {})

            result.update({
                "brand_name":            safe_get(openfda, "brand_name"),
                "generic_name":          safe_get(openfda, "generic_name"),
                "manufacturer":          safe_get(openfda, "manufacturer_name"),
                "route":                 safe_get(openfda, "route"),
                "dosage_form":           safe_get(openfda, "dosage_form"),
                "substance_name":        safe_get(openfda, "substance_name"),
                "product_type":          safe_get(openfda, "product_type"),

                # Clinical
                "indications":           safe_get(r, "indications_and_usage"),
                "mechanism":             safe_get(r, "mechanism_of_action"),
                "pharmacodynamics":      safe_get(r, "pharmacodynamics"),
                "pharmacokinetics":      safe_get(r, "clinical_pharmacology"),
                "contraindications":     safe_get(r, "contraindications"),
                "dosage_administration": safe_get(r, "dosage_and_administration"),

                # Safety
                "warnings":              safe_get(r, "warnings"),
                "warnings_boxed":        safe_get(r, "boxed_warning"),
                "adverse_reactions":     safe_get(r, "adverse_reactions"),
                "drug_interactions":     safe_get(r, "drug_interactions"),
                "precautions":           safe_get(r, "precautions"),
                "overdosage":            safe_get(r, "overdosage"),
                "pregnancy":             safe_get(r, "pregnancy"),
                "pediatric_use":         safe_get(r, "pediatric_use"),
                "geriatric_use":         safe_get(r, "geriatric_use"),
                "storage":               safe_get(r, "storage_and_handling"),
            })
        else:
            # No verified match found — return minimal info rather than wrong data
            result["generic_name"] = name
            result["no_fda_data"]  = True

        # ── RxNorm interactions ─────────────────────────
        if rxcui:
            try:
                interact_resp = requests.get(
                    f"{RXNORM_URL}/interaction/interaction.json",
                    params={"rxcui": rxcui},
                    timeout=8
                )

                interactions = []
                if interact_resp.status_code == 200:
                    i_data = interact_resp.json()
                    groups = i_data.get("interactionTypeGroup") or []
                    for group in groups:
                        for itype in group.get("interactionType", []):
                            for pair in itype.get("interactionPair", []):
                                desc  = pair.get("description", "")
                                drugs = [
                                    c.get("minConceptItem", {}).get("name", "")
                                    for c in pair.get("interactionConcept", [])
                                ]
                                if desc:
                                    interactions.append({
                                        "drugs":       drugs,
                                        "description": desc,
                                        "severity":    pair.get("severity", "")
                                    })

                result["interactions"] = interactions[:20]

            except Exception:
                result["interactions"] = []

        # ── Adverse events ──────────────────────────────
        # Use the verified generic name from FDA, not the raw search query
        ae_term = result.get("generic_name") or name
        if ae_term:
            try:
                ae_resp = requests.get(
                    f"{OPENFDA_URL}/event.json",
                    params={
                        "search": f'patient.drug.medicinalproduct:"{ae_term}"',
                        "count":  "patient.reaction.reactionmeddrapt.exact",
                        "limit":  10
                    },
                    timeout=8
                )
                if ae_resp.status_code == 200:
                    result["top_adverse_events"] = ae_resp.json().get("results", [])
            except Exception:
                result["top_adverse_events"] = []

        if not result.get("generic_name") and name:
            result["generic_name"] = name

        return jsonify(result), 200

    except Exception:
        return jsonify({"error": "Drug detail fetch failed"}), 502