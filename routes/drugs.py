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


def extract_base_name(full_name):
    if not full_name:
        return ""

    name = full_name.lower()

    # Remove dosage info
    name = re.sub(r'\d+(\.\d+)?\s*(mg|mcg|ml|mg/ml|mg/5ml|%|iu|units?)[^\]]*', '', name)

    # Remove bracket content
    name = re.sub(r'\[.*?\]', '', name)

    # Remove dosage forms
    name = re.sub(
        r'\b(oral|tablet|capsule|solution|injection|cream|gel|patch|syrup|suspension|topical|extended|release|delayed)\b',
        '',
        name
    )

    # Remove unwanted symbols
    name = re.sub(r'[^a-zA-Z0-9\s/]', ' ', name)

    # Normalize spaces
    name = re.sub(r'\s+', ' ', name).strip()

    return name


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
                    name = concept.get("name", "")
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
        # ── Clean name for OpenFDA ───────────────────────
        base_name = extract_base_name(name) if name else ""

        if not base_name and name:
            base_name = name.split()[0].lower()

        search_attempts = []

        if base_name:
            search_attempts.extend([
                f'openfda.generic_name:"{base_name}"',
                f'openfda.substance_name:"{base_name}"',
                f'openfda.brand_name:"{base_name}"',
            ])

        if name:
            search_attempts.append(f'openfda.generic_name:"{name}"')

        fda_resp = None

        for attempt in search_attempts:
            try:
                resp = requests.get(
                    f"{OPENFDA_URL}/label.json",
                    params={"search": attempt, "limit": 1},
                    timeout=8
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("results"):
                        fda_resp = resp
                        break
            except Exception:
                continue

        # fallback → rxcui
        if not fda_resp and rxcui:
            try:
                resp = requests.get(
                    f"{OPENFDA_URL}/label.json",
                    params={"search": f'openfda.rxcui:"{rxcui}"', "limit": 1},
                    timeout=8
                )
                if resp.status_code == 200 and resp.json().get("results"):
                    fda_resp = resp
            except Exception:
                pass

        # ── Parse OpenFDA ────────────────────────────────
        if fda_resp and fda_resp.status_code == 200:
            fda_data = fda_resp.json()
            results  = fda_data.get("results", [])

            if results:
                r = results[0]
                openfda = r.get("openfda", {})

                result.update({
                    "brand_name":       safe_get(openfda, "brand_name"),
                    "generic_name":     safe_get(openfda, "generic_name"),
                    "manufacturer":     safe_get(openfda, "manufacturer_name"),
                    "route":            safe_get(openfda, "route"),
                    "dosage_form":      safe_get(openfda, "dosage_form"),
                    "substance_name":   safe_get(openfda, "substance_name"),
                    "product_type":     safe_get(openfda, "product_type"),

                    # Clinical
                    "indications":          safe_get(r, "indications_and_usage"),
                    "mechanism":            safe_get(r, "mechanism_of_action"),
                    "pharmacodynamics":     safe_get(r, "pharmacodynamics"),
                    "pharmacokinetics":     safe_get(r, "clinical_pharmacology"),
                    "contraindications":    safe_get(r, "contraindications"),
                    "dosage_administration":safe_get(r, "dosage_and_administration"),

                    # Safety
                    "warnings":             safe_get(r, "warnings"),
                    "warnings_boxed":       safe_get(r, "boxed_warning"),
                    "adverse_reactions":    safe_get(r, "adverse_reactions"),
                    "drug_interactions":    safe_get(r, "drug_interactions"),
                    "precautions":          safe_get(r, "precautions"),
                    "overdosage":           safe_get(r, "overdosage"),
                    "pregnancy":            safe_get(r, "pregnancy"),
                    "pediatric_use":        safe_get(r, "pediatric_use"),
                    "geriatric_use":        safe_get(r, "geriatric_use"),
                    "storage":              safe_get(r, "storage_and_handling"),
                })

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
                                desc = pair.get("description", "")
                                drugs = [
                                    c.get("minConceptItem", {}).get("name", "")
                                    for c in pair.get("interactionConcept", [])
                                ]

                                if desc:
                                    interactions.append({
                                        "drugs": drugs,
                                        "description": desc,
                                        "severity": pair.get("severity", "")
                                    })

                result["interactions"] = interactions[:20]

            except Exception:
                result["interactions"] = []

        # ── Adverse events ──────────────────────────────
        search_term = result.get("generic_name") or base_name

        if search_term:
            try:
                ae_resp = requests.get(
                    f"{OPENFDA_URL}/event.json",
                    params={
                        "search": f'patient.drug.medicinalproduct:"{search_term}"',
                        "count": "patient.reaction.reactionmeddrapt.exact",
                        "limit": 10
                    },
                    timeout=8
                )

                if ae_resp.status_code == 200:
                    ae_data = ae_resp.json()
                    result["top_adverse_events"] = ae_data.get("results", [])

            except Exception:
                result["top_adverse_events"] = []

        if not result.get("generic_name") and name:
            result["generic_name"] = base_name or name

        return jsonify(result), 200

    except Exception:
        return jsonify({"error": "Drug detail fetch failed"}), 502