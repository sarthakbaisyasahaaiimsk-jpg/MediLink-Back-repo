from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Case, User
from extensions import db
import os, uuid
from werkzeug.utils import secure_filename

patient_cases_bp = Blueprint("patient_cases", __name__)

# Get all patient cases with filtering
@patient_cases_bp.route("", methods=["GET"])
def get_cases():
    try:
        created_by = request.args.get('created_by')
        status = request.args.get('status')
        specialty = request.args.get('specialty')
        sort = request.args.get('sort', 'created_date')
        
        query = Case.query
        
        if created_by:
            query = query.filter_by(created_by=created_by)
        if status:
            query = query.filter_by(status=status)
        if specialty:
            query = query.filter(Case.specialty_tags.like(f'%{specialty}%'))
        
        # Handle sorting
        if sort.startswith('-'):
            query = query.order_by(getattr(Case, sort[1:]).desc())
        else:
            query = query.order_by(getattr(Case, sort).asc())
        
        cases = query.all()
        return jsonify([c.to_dict() for c in cases]), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Get single case
@patient_cases_bp.route("/<int:id>", methods=["GET"])
def get_case(id):
    try:
        case = Case.query.get(id)
        if not case:
            return jsonify(error="Case not found"), 404
        return jsonify(case.to_dict()), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Create case
def verify_user_is_doctor():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return None, jsonify(error='User not found'), 404
    if not user.is_verified:
        return None, jsonify(error='Doctor verification required for this action'), 403
    return user, None, None


@patient_cases_bp.route("", methods=["POST"])
@jwt_required()
def create_case():
    user, err_response, status = verify_user_is_doctor()
    if err_response:
        return err_response, status
    try:
        os.makedirs("uploads", exist_ok=True)
        
        data = request.form if request.form else request.json
        
        # Safe age conversion
        age = data.get("patient_age")
        patient_age = int(age) if age and str(age).isdigit() else None
        
        # Handle files if multipart
        file_paths = []
        if request.files:
            files = request.files.getlist("files")
            for f in files:
                if f:
                    safe_name = secure_filename(f.filename)
                    filename = f"{uuid.uuid4()}_{safe_name}"
                    path = os.path.join("uploads", filename)
                    f.save(path)
                    file_paths.append(path)
        
        # Handle specialty tags
        specialty_tags = data.get("specialty_tags")
        if isinstance(specialty_tags, list):
            specialty_tags = ",".join(specialty_tags)
        
        new_case = Case(
            title=data.get("title"),
            chief_complaint=data.get("chief_complaint"),
            description=data.get("description") or data.get("chief_complaint"),
            patient_age=patient_age,
            patient_gender=data.get("patient_gender"),
            history=data.get("history"),
            examination_findings=data.get("examination_findings"),
            investigations=data.get("investigations"),
            current_treatment=data.get("current_treatment"),
            question=data.get("question"),
            specialty_tags=specialty_tags,
            visibility=data.get("visibility", "public"),
            status=data.get("status", "open"),
            attachments=",".join(file_paths),
            created_by=data.get("created_by") or data.get("poster_name")
        )
        
        db.session.add(new_case)
        db.session.commit()
        
        return jsonify({
            "message": "Case created successfully",
            "id": new_case.id,
            "case": new_case.to_dict(),
            "files": file_paths
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Update case
@patient_cases_bp.route("/<int:id>", methods=["PUT"])
@jwt_required()
def update_case(id):
    user, err_response, status = verify_user_is_doctor()
    if err_response:
        return err_response, status
    try:
        case = Case.query.get(id)
        if not case:
            return jsonify(error="Case not found"), 404
        
        data = request.json
        
        if 'title' in data:
            case.title = data['title']
        if 'chief_complaint' in data:
            case.chief_complaint = data['chief_complaint']
        if 'description' in data:
            case.description = data['description']
        if 'patient_age' in data:
            case.patient_age = data['patient_age']
        if 'patient_gender' in data:
            case.patient_gender = data['patient_gender']
        if 'history' in data:
            case.history = data['history']
        if 'examination_findings' in data:
            case.examination_findings = data['examination_findings']
        if 'investigations' in data:
            case.investigations = data['investigations']
        if 'current_treatment' in data:
            case.current_treatment = data['current_treatment']
        if 'question' in data:
            case.question = data['question']
        if 'status' in data:
            case.status = data['status']
        if 'specialty_tags' in data:
            tags = data['specialty_tags']
            case.specialty_tags = ",".join(tags) if isinstance(tags, list) else tags
        if 'discussion_count' in data:
            case.discussion_count = data['discussion_count']
        
        db.session.commit()
        return jsonify(case.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Delete case
@patient_cases_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_case(id):
    user, err_response, status = verify_user_is_doctor()
    if err_response:
        return err_response, status
    try:
        case = Case.query.get(id)
        if not case:
            return jsonify(error="Case not found"), 404
        
        db.session.delete(case)
        db.session.commit()
        
        return jsonify(msg="Case deleted"), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500
