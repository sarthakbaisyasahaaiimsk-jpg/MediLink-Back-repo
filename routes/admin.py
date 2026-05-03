from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User, Case, Comment, MedicalEvent, Conversation, Message, DoctorProfile, SavedReference
from extensions import db
from functools import wraps

admin_bp = Blueprint("admin", __name__)

def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user or not user.is_admin:
            return jsonify(error="Admin access required"), 403
        return fn(*args, **kwargs)
    return wrapper

# ── ANALYTICS ──────────────────────────────────────
@admin_bp.route("/analytics", methods=["GET"])
@admin_required
def get_analytics():
    return jsonify({
        "total_users":        User.query.count(),
        "verified_users":     User.query.filter_by(is_verified=True).count(),
        "pending_users":      User.query.filter_by(verification_state="pending").count(),
        "total_cases":        Case.query.count(),
        "open_cases":         Case.query.filter_by(status="open").count(),
        "total_events":       MedicalEvent.query.count(),
        "total_conversations":Conversation.query.count(),
        "total_messages":     Message.query.count(),
        "total_references":   SavedReference.query.count(),
        "total_profiles":     DoctorProfile.query.count(),
    })

# ── USERS ───────────────────────────────────────────
@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    users = User.query.order_by(User.id.desc()).all()
    return jsonify([u.to_dict() for u in users])

@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify(msg="User deleted")

@admin_bp.route("/users/<int:user_id>/verify", methods=["PATCH"])
@admin_required
def verify_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = True
    user.verification_state = "verified"
    db.session.commit()
    return jsonify(msg="User verified", user=user.to_dict())

@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["PATCH"])
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    return jsonify(msg="Admin status updated", is_admin=user.is_admin)

# ── CASES ───────────────────────────────────────────
@admin_bp.route("/cases", methods=["GET"])
@admin_required
def list_cases():
    cases = Case.query.order_by(Case.created_date.desc()).all()
    return jsonify([c.to_dict() for c in cases])

@admin_bp.route("/cases/<int:case_id>", methods=["DELETE"])
@admin_required
def delete_case(case_id):
    case = Case.query.get_or_404(case_id)
    db.session.delete(case)
    db.session.commit()
    return jsonify(msg="Case deleted")

@admin_bp.route("/cases/<int:case_id>/status", methods=["PATCH"])
@admin_required
def update_case_status(case_id):
    case = Case.query.get_or_404(case_id)
    case.status = request.json.get("status", case.status)
    db.session.commit()
    return jsonify(msg="Status updated", case=case.to_dict())

# ── EVENTS ──────────────────────────────────────────
@admin_bp.route("/events", methods=["GET"])
@admin_required
def list_events():
    events = MedicalEvent.query.order_by(MedicalEvent.created_date.desc()).all()
    return jsonify([e.to_dict() for e in events])

@admin_bp.route("/events/<int:event_id>", methods=["DELETE"])
@admin_required
def delete_event(event_id):
    event = MedicalEvent.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    return jsonify(msg="Event deleted")

# ── CHATS ───────────────────────────────────────────
@admin_bp.route("/conversations", methods=["GET"])
@admin_required
def list_conversations():
    convs = Conversation.query.order_by(Conversation.last_message_time.desc()).all()
    return jsonify([c.to_dict() for c in convs])

@admin_bp.route("/conversations/<int:conv_id>", methods=["DELETE"])
@admin_required
def delete_conversation(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    Message.query.filter_by(conversation_id=conv_id).delete()
    db.session.delete(conv)
    db.session.commit()
    return jsonify(msg="Conversation deleted")

# ── NETWORKING (Doctor Profiles) ─────────────────────
@admin_bp.route("/profiles", methods=["GET"])
@admin_required
def list_profiles():
    profiles = DoctorProfile.query.order_by(DoctorProfile.created_date.desc()).all()