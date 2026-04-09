from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import os, uuid
from werkzeug.utils import secure_filename
from extensions import db
from models import Case, User
from supabase import create_client

case_bp = Blueprint("cases", __name__)

def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

@case_bp.route("/cases", methods=["POST"])
@jwt_required()
def create_case():
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)

        data = request.form

        # ✅ Safe age conversion
        age = data.get("patient_age")
        patient_age = int(age) if age and age.isdigit() else None

        # ✅ Handle files — upload to Supabase
        files = request.files.getlist("files")
        file_urls = []

        supabase = get_supabase()

        for f in files:
            if f and f.filename:
                safe_name = secure_filename(f.filename)
                filename = f"{uuid.uuid4()}_{safe_name}"
                file_bytes = f.read()
                content_type = f.content_type or 'application/octet-stream'

                supabase.storage.from_("uploads").upload(
                    path=filename,
                    file=file_bytes,
                    file_options={"content-type": content_type}
                )

                public_url = supabase.storage.from_("uploads").get_public_url(filename)
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