from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import os, uuid
import requests as http_requests
from werkzeug.utils import secure_filename
from extensions import db
from models import JobPosting, JobApplication, User

recruitment_bp = Blueprint("recruitment", __name__)


# ─── Supabase helper (same pattern as cases.py) ───────────────────────────────

def upload_to_supabase(file_bytes, filename, content_type):
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()
    upload_url = f"{supabase_url}/storage/v1/object/uploads/{filename}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    res = http_requests.post(upload_url, data=file_bytes, headers=headers)
    if res.status_code not in (200, 201):
        raise Exception(f"Supabase upload failed: {res.text}")
    return f"{supabase_url}/storage/v1/object/public/uploads/{filename}"


# ─── JOB POSTINGS ─────────────────────────────────────────────────────────────

@recruitment_bp.route("/jobs", methods=["GET"])
@jwt_required()
def list_jobs():
    """Return all open job postings, newest first."""
    jobs = JobPosting.query.filter_by(is_active=True).order_by(
        JobPosting.created_at.desc()
    ).all()
    return jsonify([j.to_dict() for j in jobs]), 200


@recruitment_bp.route("/jobs/mine", methods=["GET"])
@jwt_required()
def my_job_postings():
    """Return all jobs posted by the current user."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    jobs = JobPosting.query.filter_by(posted_by=user.email).order_by(
        JobPosting.created_at.desc()
    ).all()
    return jsonify([j.to_dict() for j in jobs]), 200


@recruitment_bp.route("/jobs/<int:job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id):
    job = JobPosting.query.get_or_404(job_id)
    return jsonify(job.to_dict()), 200


@recruitment_bp.route("/jobs", methods=["POST"])
@jwt_required()
def create_job():
    """Create a new job posting."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json()

        job = JobPosting(
            title=data.get("title"),
            institution=data.get("institution"),
            location=data.get("location"),
            employment_type=data.get("employment_type"),   # full-time / part-time / locum / fellowship
            specialty=data.get("specialty"),
            description=data.get("description"),
            requirements=data.get("requirements"),
            salary_min=data.get("salary_min"),
            salary_max=data.get("salary_max"),
            salary_currency=data.get("salary_currency", "INR"),
            salary_period=data.get("salary_period", "monthly"),  # monthly / annual
            contact_email=data.get("contact_email", user.email),
            deadline=data.get("deadline"),                 # ISO date string or None
            posted_by=user.email,
            is_active=True,
        )

        db.session.add(job)
        db.session.commit()

        return jsonify({"message": "Job posted successfully", "job": job.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        print("JOB CREATE ERROR:", repr(e))
        return jsonify({"error": str(e)}), 500


@recruitment_bp.route("/jobs/<int:job_id>", methods=["PUT"])
@jwt_required()
def update_job(job_id):
    """Update a job posting (owner only)."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        job = JobPosting.query.get_or_404(job_id)

        if job.posted_by != user.email:
            return jsonify({"error": "Not authorised"}), 403

        data = request.get_json()
        for field in [
            "title", "institution", "location", "employment_type",
            "specialty", "description", "requirements",
            "salary_min", "salary_max", "salary_currency", "salary_period",
            "contact_email", "deadline", "is_active",
        ]:
            if field in data:
                setattr(job, field, data[field])

        db.session.commit()
        return jsonify({"message": "Job updated", "job": job.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@recruitment_bp.route("/jobs/<int:job_id>", methods=["DELETE"])
@jwt_required()
def delete_job(job_id):
    """Soft-delete (deactivate) a job posting (owner only)."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        job = JobPosting.query.get_or_404(job_id)

        if job.posted_by != user.email:
            return jsonify({"error": "Not authorised"}), 403

        job.is_active = False
        db.session.commit()
        return jsonify({"message": "Job removed"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ─── JOB APPLICATIONS ─────────────────────────────────────────────────────────

@recruitment_bp.route("/jobs/<int:job_id>/apply", methods=["POST"])
@jwt_required()
def apply_for_job(job_id):
    """
    Apply for a job.  Accepts multipart/form-data so the applicant can
    upload a CV / cover-letter PDF alongside the text fields.
    """
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        job = JobPosting.query.get_or_404(job_id)

        # Prevent duplicate applications
        existing = JobApplication.query.filter_by(
            job_id=job_id, applicant_email=user.email
        ).first()
        if existing:
            return jsonify({"error": "You have already applied for this job"}), 409

        # Prevent the poster from applying to their own job
        if job.posted_by == user.email:
            return jsonify({"error": "You cannot apply to your own job posting"}), 400

        data = request.form

        # Optional CV upload
        cv_url = None
        cv_file = request.files.get("cv")
        if cv_file and cv_file.filename:
            safe_name = secure_filename(cv_file.filename)
            filename = f"cv_{uuid.uuid4()}_{safe_name}"
            cv_url = upload_to_supabase(
                cv_file.read(), filename, cv_file.content_type or "application/pdf"
            )

        application = JobApplication(
            job_id=job_id,
            applicant_email=user.email,
            applicant_name=data.get("applicant_name") or user.full_name,
            cover_letter=data.get("cover_letter"),
            cv_url=cv_url,
            status="pending",          # pending / shortlisted / rejected
        )

        db.session.add(application)
        db.session.commit()

        return jsonify({
            "message": "Application submitted successfully",
            "application": application.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        print("APPLY ERROR:", repr(e))
        return jsonify({"error": str(e)}), 500


@recruitment_bp.route("/jobs/<int:job_id>/applications", methods=["GET"])
@jwt_required()
def job_applications(job_id):
    """
    Return all applications for a specific job.
    Only the job poster can view applications.
    """
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        job = JobPosting.query.get_or_404(job_id)

        if job.posted_by != user.email:
            return jsonify({"error": "Not authorised"}), 403

        apps = JobApplication.query.filter_by(job_id=job_id).order_by(
            JobApplication.created_at.desc()
        ).all()
        return jsonify([a.to_dict() for a in apps]), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@recruitment_bp.route("/applications/<int:app_id>/status", methods=["PUT"])
@jwt_required()
def update_application_status(app_id):
    """Let the job poster update an application status (shortlisted / rejected / pending)."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        application = JobApplication.query.get_or_404(app_id)
        job = JobPosting.query.get(application.job_id)

        if job.posted_by != user.email:
            return jsonify({"error": "Not authorised"}), 403

        data = request.get_json()
        new_status = data.get("status")
        if new_status not in ("pending", "shortlisted", "rejected"):
            return jsonify({"error": "Invalid status"}), 400

        application.status = new_status
        db.session.commit()
        return jsonify({"message": "Status updated", "application": application.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@recruitment_bp.route("/applications/mine", methods=["GET"])
@jwt_required()
def my_applications():
    """Return all applications submitted by the current user."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    apps = JobApplication.query.filter_by(applicant_email=user.email).order_by(
        JobApplication.created_at.desc()
    ).all()
    return jsonify([a.to_dict() for a in apps]), 200