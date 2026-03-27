from flask import Blueprint, request, jsonify
import os, uuid
from werkzeug.utils import secure_filename
from extensions import db
from models import Case

case_bp = Blueprint("cases", __name__)

@case_bp.route("/cases", methods=["POST"])
def create_case():
    try:
        os.makedirs("uploads", exist_ok=True)

        data = request.form

        # ✅ Safe age conversion
        age = data.get("patient_age")
        patient_age = int(age) if age and age.isdigit() else None

        # ✅ Handle files
        files = request.files.getlist("files")
        file_paths = []

        for f in files:
            if f:
                safe_name = secure_filename(f.filename)
                filename = f"{uuid.uuid4()}_{safe_name}"
                path = os.path.join("uploads", filename)
                f.save(path)
                file_paths.append(path)

        new_case = Case(
            title=data.get("title"),
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
            attachments=",".join(file_paths),
            created_by=data.get("poster_name")
        )

        db.session.add(new_case)
        db.session.commit()

        return jsonify({
            "message": "Case created successfully",
            "files": file_paths
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500