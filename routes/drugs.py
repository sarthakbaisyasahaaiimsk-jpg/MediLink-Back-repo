from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

drugs_bp = Blueprint('drugs', __name__)

OPENFDA_URL  = "https://api.fda.gov/drug"
RXNORM_URL   = "https://rxnav.nlm.nih.gov/REST"
DAILYMED_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
CHEMBL_URL   = "https://www.ebi.ac.uk/chembl/api/data"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    if not text:
        return ""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def name_matches(query, candidate):
    if not query or not candidate:
        return False
    q = normalize(query)
    c = normalize(candidate)
    if q == c or q in c or c.startswith(q):
        return True
    q_tokens = re.sub(r'[^a-z0-9\s]', '', query.lower()).split()
    if q_tokens and normalize(q_tokens[0]) in c:
        return True
    return False


def best_fda_result(results, query):
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


def first_nonempty(*values):
    for v in values:
        if v and v != "" and v != [] and v != {}:
            return v
    return ""


def clean_html(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', ' ', str(text)).strip()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEXT SUMMARISER — converts long FDA paragraphs into
# clean bullet-ready sentences BEFORE sending to frontend.
# This means less data over the wire + faster frontend render.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Section headers that appear inline in FDA text — used as
# split points so each topic becomes its own bullet.
_INLINE_HEADERS = re.compile(
    r'\b('
    r'Limitations of Use|Dosage and Administration|'
    r'Usage|Indications|Contraindications|Warnings|'
    r'Precautions|Adverse Reactions|Drug Interactions|'
    r'Overdosage|Pregnancy|Lactation|Pediatric Use|'
    r'Geriatric Use|Storage|Mechanism of Action|'
    r'Pharmacokinetics|Clinical Pharmacology|'
    r'Pharmacodynamics|Description'
    r')\s*[:\-]?\s*',
    re.IGNORECASE
)

# Patterns that are noise — section numbers, legal boilerplate, etc.
_NOISE = re.compile(
    r'^(\d+\s+[A-Z\s&]+)$|'           # "1 INDICATIONS AND USAGE"
    r'^\(\s*\d+\s*\)$|'               # "(1)"
    r'^[A-Z\s]{10,}$|'                # ALL CAPS headers
    r'prescribing information|'
    r'full prescribing|'
    r'see (also )?section',
    re.IGNORECASE
)


def summarise_field(text, max_bullets=8):
    """
    Converts raw FDA label text into a list of clean bullet strings.
    - Splits on inline section headers and sentence boundaries
    - Deduplicates and removes noise
    - Caps at max_bullets to keep payload small
    Returns a list of strings (not a paragraph).
    """
    if not text:
        return []

    if isinstance(text, list):
        text = " ".join(str(t) for t in text)

    # 1. Flatten: replace newlines + multiple spaces with single space
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()

    # 2. Split on inline section headers first (they act as natural bullet breaks)
    parts = _INLINE_HEADERS.split(text)

    # 3. For each part, split into sentences
    sentences = []
    for part in parts:
        part = part.strip()
        if not part or len(part) < 15:
            continue
        # Split on sentence boundaries — period/exclamation followed by capital
        split = re.split(r'(?<=[.!?])\s+(?=[A-Z(])', part)
        for s in split:
            s = s.strip().rstrip('.')
            if len(s) < 20:
                continue
            # Strip leading list markers
            s = re.sub(r'^[\u2022\-\*\u00b7]\s*', '', s)
            s = re.sub(r'^\d+[\.\)]\s*', '', s)
            sentences.append(s)

    # 4. Remove noise lines
    sentences = [s for s in sentences if not _NOISE.search(s)]

    # 5. Deduplicate (by first 60 chars, case-insensitive)
    seen = set()
    unique = []
    for s in sentences:
        key = s.lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    # 6. Cap length — return top N most informative bullets
    # Prefer longer sentences (more info) over very short ones
    unique.sort(key=lambda s: -len(s))
    top = unique[:max_bullets]
    # Re-sort in original document order (approximate: by first char position)
    # by rebuilding in insertion order from unique list
    order = {s: i for i, s in enumerate(unique)}
    top_ordered = sorted(top, key=lambda s: order.get(s, 999))

    return top_ordered


def summarise_drug_fields(drug_dict):
    """
    Walk all text fields and convert them from raw paragraphs to bullet lists.
    Non-text fields (lists, booleans, numbers) are left untouched.
    """
    TEXT_FIELDS = {
        "indications", "dosage_administration", "contraindications",
        "warnings", "warnings_boxed", "adverse_reactions",
        "drug_interactions", "precautions", "overdosage",
        "pregnancy", "pediatric_use", "geriatric_use", "storage",
        "pharmacokinetics", "pharmacodynamics", "mechanism",
    }
    # Bullet caps per section — safety sections get more bullets
    CAPS = {
        "warnings_boxed":    5,
        "contraindications": 6,
        "adverse_reactions": 10,
        "drug_interactions": 8,
        "warnings":          8,
        "indications":       6,
    }
    for field in TEXT_FIELDS:
        val = drug_dict.get(field)
        if val and isinstance(val, (str, list)):
            cap = CAPS.get(field, 7)
            drug_dict[field] = summarise_field(val, max_bullets=cap)

    return drug_dict


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SOURCE 1 — OpenFDA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_openfda(name, rxcui):
    fda_result = None

    if rxcui:
        try:
            resp = requests.get(
                f"{OPENFDA_URL}/label.json",
                params={"search": f'openfda.rxcui:"{rxcui}"', "limit": 5},
                timeout=6
            )
            if resp.status_code == 200:
                fda_result = best_fda_result(resp.json().get("results", []), name or rxcui)
        except Exception:
            pass

    if not fda_result and name:
        for field in ("openfda.generic_name", "openfda.substance_name", "openfda.brand_name"):
            try:
                resp = requests.get(
                    f"{OPENFDA_URL}/label.json",
                    params={"search": f'{field}:"{name.strip()}"', "limit": 5},
                    timeout=6
                )
                if resp.status_code == 200:
                    candidate = best_fda_result(resp.json().get("results", []), name)
                    if candidate:
                        fda_result = candidate
                        break
            except Exception:
                continue

    if not fda_result and name:
        first_word = name.strip().split()[0]
        if len(first_word) >= 4:
            try:
                resp = requests.get(
                    f"{OPENFDA_URL}/label.json",
                    params={"search": f'openfda.generic_name:"{first_word}"', "limit": 5},
                    timeout=6
                )
                if resp.status_code == 200:
                    candidate = best_fda_result(resp.json().get("results", []), first_word)
                    if candidate:
                        fda_result = candidate
            except Exception:
                pass

    if not fda_result:
        return {}

    r       = fda_result
    openfda = r.get("openfda", {})

    return {
        "brand_name":            safe_get(openfda, "brand_name"),
        "generic_name":          safe_get(openfda, "generic_name"),
        "manufacturer":          safe_get(openfda, "manufacturer_name"),
        "route":                 safe_get(openfda, "route"),
        "dosage_form":           safe_get(openfda, "dosage_form"),
        "substance_name":        safe_get(openfda, "substance_name"),
        "product_type":          safe_get(openfda, "product_type"),
        "indications":           safe_get(r, "indications_and_usage"),
        "mechanism":             safe_get(r, "mechanism_of_action"),
        "pharmacodynamics":      safe_get(r, "pharmacodynamics"),
        "pharmacokinetics":      safe_get(r, "clinical_pharmacology"),
        "contraindications":     safe_get(r, "contraindications"),
        "dosage_administration": safe_get(r, "dosage_and_administration"),
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
        "_source":               "OpenFDA",
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SOURCE 2 — DailyMed
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_dailymed(name):
    if not name:
        return {}

    setid = None
    try:
        resp = requests.get(
            f"{DAILYMED_URL}/spls.json",
            params={"drug_name": name.strip(), "pagesize": 5},
            timeout=6
        )
        if resp.status_code == 200:
            data  = resp.json()
            items = data.get("data", [])
            for item in items:
                label_name = item.get("title", "")
                if name_matches(name, label_name):
                    setid = item.get("setid")
                    break
            if not setid and items:
                setid = items[0].get("setid")
    except Exception:
        return {}

    if not setid:
        return {}

    try:
        resp = requests.get(
            f"{DAILYMED_URL}/spls/{setid}.json",
            timeout=8
        )
        if resp.status_code != 200:
            return {}
        spl = resp.json()
    except Exception:
        return {}

    SECTION_CODES = {
        "34067-9":  "indications",
        "34068-7":  "dosage_administration",
        "34070-3":  "contraindications",
        "34071-1":  "warnings",
        "34084-4":  "adverse_reactions",
        "34073-7":  "drug_interactions",
        "42232-9":  "precautions",
        "34088-5":  "overdosage",
        "42228-7":  "pregnancy",
        "34080-2":  "pediatric_use",
        "34081-0":  "geriatric_use",
        "44425-7":  "storage",
        "34089-3":  "description",
        "43678-2":  "dosage_form",
        "34090-1":  "pharmacokinetics",
        "43679-0":  "mechanism",
    }

    parsed = {"_source": "DailyMed", "_setid": setid}

    sections = spl.get("data", {}).get("sections", []) or []
    for section in sections:
        code = section.get("code", "")
        text = clean_html(section.get("text", ""))
        key  = SECTION_CODES.get(code)
        if key and text:
            parsed[key] = text

    product = spl.get("data", {}).get("products", [{}])[0] if spl.get("data", {}).get("products") else {}
    if product:
        parsed["brand_name"]    = parsed.get("brand_name")    or product.get("brand_name", "")
        parsed["generic_name"]  = parsed.get("generic_name")  or product.get("generic_name", "")
        parsed["manufacturer"]  = parsed.get("manufacturer")  or product.get("labeler_name", "")
        parsed["dosage_form"]   = parsed.get("dosage_form")   or product.get("dosage_form", "")
        parsed["route"]         = parsed.get("route")         or product.get("route", "")

    return parsed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SOURCE 3 — ChEMBL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_chembl(name):
    if not name:
        return {}

    chembl_id = None
    molecule  = {}
    try:
        resp = requests.get(
            f"{CHEMBL_URL}/molecule.json",
            params={"pref_name__iexact": name.strip(), "format": "json", "limit": 5},
            timeout=6
        )
        if resp.status_code == 200:
            molecules = resp.json().get("molecules", [])
            for m in molecules:
                if normalize(m.get("pref_name", "")) == normalize(name):
                    chembl_id = m.get("molecule_chembl_id")
                    molecule  = m
                    break
            if not chembl_id and molecules:
                chembl_id = molecules[0].get("molecule_chembl_id")
                molecule  = molecules[0]
    except Exception:
        return {}

    if not chembl_id:
        try:
            resp = requests.get(
                f"{CHEMBL_URL}/molecule.json",
                params={"molecule_synonyms__synonym__iexact": name.strip(), "format": "json", "limit": 3},
                timeout=6
            )
            if resp.status_code == 200:
                molecules = resp.json().get("molecules", [])
                if molecules:
                    chembl_id = molecules[0].get("molecule_chembl_id")
                    molecule  = molecules[0]
        except Exception:
            pass

    if not chembl_id:
        return {}

    parsed = {"_source": "ChEMBL", "_chembl_id": chembl_id}

    props  = molecule.get("molecule_properties") or {}
    struct = molecule.get("molecule_structures") or {}
    hiers  = molecule.get("atc_classifications") or []

    parsed.update({
        "molecular_formula":   molecule.get("molecule_type", ""),
        "max_phase":           molecule.get("max_phase", ""),
        "atc_classifications": [h.get("level5", "") for h in hiers if h.get("level5")],
        "molecular_weight":    props.get("full_mwt", ""),
        "smiles":              struct.get("canonical_smiles", ""),
        "black_box_warning":   molecule.get("black_box_warning", False),
        "prodrug":             molecule.get("prodrug", False),
        "oral":                molecule.get("oral", False),
        "parenteral":          molecule.get("parenteral", False),
        "topical":             molecule.get("topical", False),
    })

    try:
        resp = requests.get(
            f"{CHEMBL_URL}/mechanism.json",
            params={"molecule_chembl_id": chembl_id, "format": "json", "limit": 20},
            timeout=6
        )
        if resp.status_code == 200:
            mechanisms = resp.json().get("mechanisms", [])
            moa_list, targets = [], []
            for m in mechanisms:
                moa_text = m.get("mechanism_of_action", "")
                target   = m.get("target_name", "")
                if moa_text:
                    moa_list.append(moa_text)
                if target:
                    targets.append({
                        "target":     target,
                        "action":     m.get("action_type", ""),
                        "chembl_tid": m.get("target_chembl_id", ""),
                    })
            if moa_list:
                parsed["mechanism_chembl"] = "; ".join(set(moa_list))
            if targets:
                parsed["drug_targets"] = targets
    except Exception:
        pass

    try:
        resp = requests.get(
            f"{CHEMBL_URL}/drug_indication.json",
            params={"molecule_chembl_id": chembl_id, "format": "json", "limit": 20},
            timeout=6
        )
        if resp.status_code == 200:
            parsed["chembl_indications"] = [
                {"condition": ind.get("mesh_heading", ""), "max_phase": ind.get("max_phase_for_ind", "")}
                for ind in resp.json().get("drug_indications", [])
                if ind.get("mesh_heading")
            ]
    except Exception:
        pass

    try:
        resp = requests.get(
            f"{CHEMBL_URL}/molecule/{chembl_id}.json",
            params={"format": "json"},
            timeout=6
        )
        if resp.status_code == 200:
            detail = resp.json()
            parsed["indication_class"]      = detail.get("indication_class", "")
            parsed["usan_stem"]             = detail.get("usan_stem", "")
            parsed["usan_stem_definition"]  = detail.get("usan_stem_definition", "")
            parsed["therapeutic_flag"]      = detail.get("therapeutic_flag", False)
    except Exception:
        pass

    return parsed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MERGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def merge_sources(fda, dailymed, chembl):
    merged = {}

    merged["generic_name"]   = first_nonempty(fda.get("generic_name"),  dailymed.get("generic_name"))
    merged["brand_name"]     = first_nonempty(fda.get("brand_name"),    dailymed.get("brand_name"))
    merged["manufacturer"]   = first_nonempty(fda.get("manufacturer"),  dailymed.get("manufacturer"))
    merged["route"]          = first_nonempty(fda.get("route"),         dailymed.get("route"))
    merged["dosage_form"]    = first_nonempty(fda.get("dosage_form"),   dailymed.get("dosage_form"))
    merged["substance_name"] = fda.get("substance_name", "")
    merged["product_type"]   = fda.get("product_type", "")

    clinical_fields = [
        "indications", "dosage_administration", "contraindications",
        "warnings", "warnings_boxed", "adverse_reactions",
        "drug_interactions", "precautions", "overdosage",
        "pregnancy", "pediatric_use", "geriatric_use",
        "storage", "pharmacokinetics", "pharmacodynamics",
    ]
    for field in clinical_fields:
        merged[field] = first_nonempty(fda.get(field), dailymed.get(field))

    merged["mechanism"] = first_nonempty(
        chembl.get("mechanism_chembl"),
        fda.get("mechanism"),
        dailymed.get("mechanism"),
    )

    merged["drug_targets"]         = chembl.get("drug_targets", [])
    merged["chembl_indications"]   = chembl.get("chembl_indications", [])
    merged["atc_classifications"]  = chembl.get("atc_classifications", [])
    merged["indication_class"]     = chembl.get("indication_class", "")
    merged["molecular_weight"]     = chembl.get("molecular_weight", "")
    merged["molecular_formula"]    = chembl.get("molecular_formula", "")
    merged["smiles"]               = chembl.get("smiles", "")
    merged["max_phase"]            = chembl.get("max_phase", "")
    merged["black_box_warning"]    = chembl.get("black_box_warning", False)
    merged["prodrug"]              = chembl.get("prodrug", False)
    merged["oral"]                 = chembl.get("oral", False)
    merged["parenteral"]           = chembl.get("parenteral", False)
    merged["topical"]              = chembl.get("topical", False)
    merged["usan_stem"]            = chembl.get("usan_stem", "")
    merged["usan_stem_definition"] = chembl.get("usan_stem_definition", "")
    merged["therapeutic_flag"]     = chembl.get("therapeutic_flag", False)

    sources_used = []
    if fda:      sources_used.append("OpenFDA")
    if dailymed: sources_used.append("DailyMed")
    if chembl:   sources_used.append("ChEMBL")
    merged["_sources"]    = sources_used
    merged["_chembl_id"]  = chembl.get("_chembl_id", "")
    merged["_setid"]      = dailymed.get("_setid", "")

    return merged


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
            timeout=6
        )

        results = []

        if rxnorm_resp.status_code == 200:
            rx_data        = rxnorm_resp.json()
            drug_group     = rx_data.get("drugGroup", {})
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
        return jsonify({"error": "RxNorm search failed", "detail": str(e)}), 502


@drugs_bp.route("/detail", methods=["GET"])
@jwt_required()
def drug_detail():
    name  = request.args.get("name", "").strip()
    rxcui = request.args.get("rxcui", "").strip()

    if not name and not rxcui:
        return jsonify({"error": "name or rxcui is required"}), 400

    # ── PARALLEL fetch — all 3 sources at the same time ──
    # Previously sequential (up to ~24s). Now parallel (~8s max).
    fda_data      = {}
    dailymed_data = {}
    chembl_data   = {}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fetch_openfda, name, rxcui):  "fda",
            executor.submit(fetch_dailymed, name):        "dailymed",
            executor.submit(fetch_chembl, name):          "chembl",
        }
        for future in as_completed(futures, timeout=12):
            key = futures[future]
            try:
                result = future.result()
                if key == "fda":
                    fda_data = result
                elif key == "dailymed":
                    dailymed_data = result
                elif key == "chembl":
                    chembl_data = result
            except Exception:
                pass  # source failed — others still populate

    # If OpenFDA returned a generic_name, retry DailyMed/ChEMBL with it
    # (only if the original name call returned nothing)
    fda_generic = fda_data.get("generic_name", "")
    if fda_generic and not dailymed_data:
        dailymed_data = fetch_dailymed(fda_generic)
    if fda_generic and not chembl_data:
        chembl_data = fetch_chembl(fda_generic)

    # ── Merge ─────────────────────────────────────────────
    result = merge_sources(fda_data, dailymed_data, chembl_data)

    if not result.get("generic_name"):
        result["generic_name"] = name

    if not fda_data and not dailymed_data and not chembl_data:
        result["no_data"] = True

    # ── Summarise all text fields into bullet arrays ──────
    # Converts "1 INDICATIONS AND USAGE Amoxicillin and Clavulanate..."
    # into ["Indicated for lower respiratory tract infections",
    #       "Active against beta-lactamase-producing organisms", ...]
    result = summarise_drug_fields(result)

    # ── RxNorm interactions (parallel-safe, runs after merge) ──
    if rxcui:
        try:
            resp = requests.get(
                f"{RXNORM_URL}/interaction/interaction.json",
                params={"rxcui": rxcui},
                timeout=6
            )
            interactions = []
            if resp.status_code == 200:
                groups = resp.json().get("interactionTypeGroup") or []
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
            result["rxnorm_interactions"] = interactions[:20]
        except Exception:
            result["rxnorm_interactions"] = []

    # ── Adverse events (FAERS) ────────────────────────────
    ae_term = result.get("generic_name") or name
    if ae_term:
        try:
            resp = requests.get(
                f"{OPENFDA_URL}/event.json",
                params={
                    "search": f'patient.drug.medicinalproduct:"{ae_term}"',
                    "count":  "patient.reaction.reactionmeddrapt.exact",
                    "limit":  15
                },
                timeout=6
            )
            if resp.status_code == 200:
                result["top_adverse_events"] = resp.json().get("results", [])
            else:
                result["top_adverse_events"] = []
        except Exception:
            result["top_adverse_events"] = []

    return jsonify(result), 200


@drugs_bp.route("/targets", methods=["GET"])
@jwt_required()
def drug_targets():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    chembl = fetch_chembl(name)
    if not chembl:
        return jsonify({"error": "No ChEMBL data found", "name": name}), 404

    return jsonify({
        "name":                name,
        "chembl_id":           chembl.get("_chembl_id"),
        "mechanism":           chembl.get("mechanism_chembl"),
        "drug_targets":        chembl.get("drug_targets", []),
        "indications":         chembl.get("chembl_indications", []),
        "atc_classifications": chembl.get("atc_classifications", []),
        "indication_class":    chembl.get("indication_class"),
        "usan_stem":           chembl.get("usan_stem"),
        "usan_stem_definition":chembl.get("usan_stem_definition"),
        "molecular_weight":    chembl.get("molecular_weight"),
        "max_phase":           chembl.get("max_phase"),
        "black_box_warning":   chembl.get("black_box_warning"),
        "oral":                chembl.get("oral"),
        "parenteral":          chembl.get("parenteral"),
    }), 200