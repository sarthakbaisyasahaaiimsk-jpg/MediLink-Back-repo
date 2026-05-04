from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import requests

drugs_bp = Blueprint('drugs', __name__)

OPENFDA_URL = "https://api.fda.gov/drug"
RXNORM_URL  = "https://rxnav.nlm.nih.gov/REST"


def safe_get(data, *keys, default=""):
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        elif isinstance(data, list):
            data = data[0] if data else default
        else:
            return default
    return data or default


# ── Search drugs by name ─────────────────────────────────
@drugs_bp.route("/search", methods=["GET"])
@jwt_required()
def search_drugs():
    query = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 10))

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        # Step 1: Get RxNorm concept IDs for the drug name
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

                    if name.lower() not in seen and tty in ("IN", "BN", "SBD", "SCD", "MIN"):
                        seen.add(name.lower())
                        results.append({
                            "rxcui": rxcui,
                            "name":  name,
                            "type":  "Brand" if tty == "BN" else "Generic"
                        })

            results = results[:limit]

        return jsonify({"results": results, "query": query}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ── Get full drug detail ──────────────────────────────────
@drugs_bp.route("/detail", methods=["GET"])
@jwt_required()
def drug_detail():
    name  = request.args.get("name", "").strip()
    rxcui = request.args.get("rxcui", "").strip()

    if not name and not rxcui:
        return jsonify({"error": "name or rxcui is required"}), 400

    result = {}

    try:
        # ── OpenFDA: label info ──────────────────────────
        fda_resp = requests.get(
            f"{OPENFDA_URL}/label.json",
            params={"search": f'openfda.generic_name:"{name}"' if name else f'openfda.rxcui:"{rxcui}"', "limit": 1},
            timeout=8
        )

        if fda_resp.status_code == 200:
            fda_data = fda_resp.json()
            results  = fda_data.get("results", [])

            if results:
                r = results[0]
                openfda = r.get("openfda", {})

                result.update({
                    "brand_name":       safe_get(openfda, "brand_name", 0),
                    "generic_name":     safe_get(openfda, "generic_name", 0),
                    "manufacturer":     safe_get(openfda, "manufacturer_name", 0),
                    "route":            safe_get(openfda, "route", 0),
                    "dosage_form":      safe_get(openfda, "dosage_and_administration", 0),
                    "substance_name":   safe_get(openfda, "substance_name", 0),
                    "product_type":     safe_get(openfda, "product_type", 0),

                    # Clinical
                    "indications":          safe_get(r, "indications_and_usage", 0),
                    "mechanism":            safe_get(r, "mechanism_of_action", 0),
                    "pharmacodynamics":     safe_get(r, "pharmacodynamics", 0),
                    "pharmacokinetics":     safe_get(r, "clinical_pharmacology", 0),
                    "contraindications":    safe_get(r, "contraindications", 0),
                    "dosage_administration":safe_get(r, "dosage_and_administration", 0),

                    # Safety
                    "warnings":             safe_get(r, "warnings", 0),
                    "warnings_boxed":       safe_get(r, "boxed_warning", 0),
                    "adverse_reactions":    safe_get(r, "adverse_reactions", 0),
                    "drug_interactions":    safe_get(r, "drug_interactions", 0),
                    "precautions":          safe_get(r, "precautions", 0),
                    "overdosage":           safe_get(r, "overdosage", 0),
                    "pregnancy":            safe_get(r, "pregnancy", 0),
                    "pediatric_use":        safe_get(r, "pediatric_use", 0),
                    "geriatric_use":        safe_get(r, "geriatric_use", 0),
                    "storage":              safe_get(r, "storage_and_handling", 0),
                })

        # ── RxNorm: interactions (if rxcui provided) ─────
        if rxcui:
            interact_resp = requests.get(
                f"{RXNORM_URL}/interaction/interaction.json",
                params={"rxcui": rxcui},
                timeout=8
            )
            interactions = []
            if interact_resp.status_code == 200:
                i_data = interact_resp.json()
                for group in i_data.get("interactionTypeGroup", []):
                    for itype in group.get("interactionType", []):
                        for pair in itype.get("interactionPair", []):
                            desc = pair.get("description", "")
                            drugs = [c.get("minConceptItem", {}).get("name", "")
                                     for c in pair.get("interactionConcept", [])]
                            if desc:
                                interactions.append({
                                    "drugs":       drugs,
                                    "description": desc,
                                    "severity":    pair.get("severity", "")
                                })
            result["interactions"] = interactions[:20]

        # ── OpenFDA: adverse events count ────────────────
        search_term = name or result.get("generic_name", "")
        if search_term:
            ae_resp = requests.get(
                f"{OPENFDA_URL}/event.json",
                params={
                    "search":  f'patient.drug.medicinalproduct:"{search_term}"',
                    "count":   "patient.reaction.reactionmeddrapt.exact",
                    "limit":   10
                },
                timeout=8
            )
            if ae_resp.status_code == 200:
                ae_data = ae_resp.json()
                result["top_adverse_events"] = ae_data.get("results", [])

        if not result.get("generic_name") and not result.get("brand_name"):
            result["generic_name"] = name

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 502