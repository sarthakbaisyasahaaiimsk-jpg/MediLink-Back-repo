from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import os, uuid
import requests as http_requests
from werkzeug.utils import secure_filename
from extensions import db
from models import Case, User

case_bp = Blueprint("cases", __name__)

def upload_to_supabase(file_bytes, filename, content_type):
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

    upload_url = f"{supabase_url}/storage/v1/object/uploads/{filename}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": content_type,
        "x-upsert": "true"
    }

    res = http_requests.post(upload_url, data=file_bytes, headers=headers)

    if res.status_code not in (200, 201):
        raise Exception(f"Supabase upload failed: {res.text}")

    return f"{supabase_url}/storage/v1/object/public/uploads/{filename}"

@case_bp.route("/cases", methods=["POST"])
@jwt_required()
def create_case():
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)

        data = request.form

        age = data.get("patient_age")
        patient_age = int(age) if age and age.isdigit() else None

        # ✅ Handle files — upload to Supabase via REST API
        files = request.files.getlist("files")
        file_urls = []

        for f in files:
            if f and f.filename:
                safe_name = secure_filename(f.filename)
                filename = f"{uuid.uuid4()}_{safe_name}"
                file_bytes = f.read()
                content_type = f.content_type or 'application/octet-stream'
                public_url = upload_to_supabase(file_bytes, filename, content_type)
                file_urls.append(public_url)

        new_case = Case(
            title=data.get("title"),
            chief_complaint=data.get("chief_complaint"),
            description=data.get("chief_complaint"),
            patient_age=patient_age,
            patient_gender=data.get("patient_gender"),
            history=data.get("history"),
            examination_findings=data.get("examination_findings"),
            investigations=data.get("investigations"),
            current_treatment=data.get("current_treatment"),
            question=data.get("question"),
            specialty_tags=data.get("specialty_tags"),
            visibility=data.get("visibility"),
            attachments=",".join(file_urls),
            created_by=user.email if user else data.get("poster_name")
        )

        db.session.add(new_case)
        db.session.commit()

        return jsonify({
            "message": "Case created successfully",
            "files": file_urls
        }), 201

    except Exception as e:
        print("CASE CREATE ERROR:", repr(e))
        return jsonify({"error": str(e)}), 500