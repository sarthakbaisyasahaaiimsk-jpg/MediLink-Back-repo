from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import ContactGroup, ContactGroupMember, User
from datetime import datetime, timezone

contacts_bp = Blueprint('contacts', __name__)


def serialize_group(group, include_members=True):
    data = {
        "id":           group.id,
        "name":         group.name,
        "color":        group.color,
        "created_at":   group.created_at.isoformat(),
        "member_count": len(group.members),
    }
    if include_members:
        data["members"] = [
            {
                "user_id":    m.user_id,
                "added_at":   m.added_at.isoformat(),
                "full_name":  m.user.full_name if m.user else "",
                "email":      m.user.email if m.user else "",
                "specialty":  getattr(m.user, 'specialty', ''),
                "avatar_url": getattr(m.user, 'avatar_url', ''),
            }
            for m in group.members
        ]
    return data


@contacts_bp.route("/groups", methods=["GET"])
@jwt_required()
def list_groups():
    owner_id = get_jwt_identity()
    groups   = ContactGroup.query.filter_by(owner_id=owner_id)\
                                 .order_by(ContactGroup.created_at)\
                                 .all()
    return jsonify([serialize_group(g) for g in groups]), 200


@contacts_bp.route("/groups", methods=["POST"])
@jwt_required()
def create_group():
    owner_id = get_jwt_identity()
    data     = request.get_json() or {}
    name     = (data.get("name") or "").strip()
    color    = data.get("color", "teal")

    if not name:
        return jsonify({"error": "Group name is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "Group name too long (max 100 chars)"}), 400

    exists = ContactGroup.query.filter_by(owner_id=owner_id, name=name).first()
    if exists:
        return jsonify({"error": "A group with this name already exists"}), 409

    group = ContactGroup(owner_id=owner_id, name=name, color=color)
    db.session.add(group)
    db.session.commit()
    return jsonify(serialize_group(group)), 201


@contacts_bp.route("/groups/<int:group_id>", methods=["PUT"])
@jwt_required()
def update_group(group_id):
    owner_id = get_jwt_identity()
    group    = ContactGroup.query.filter_by(id=group_id, owner_id=owner_id).first_or_404()
    data     = request.get_json() or {}

    if "name" in data:
        name = data["name"].strip()
        if not name:
            return jsonify({"error": "Name cannot be empty"}), 400
        conflict = ContactGroup.query.filter(
            ContactGroup.owner_id == owner_id,
            ContactGroup.name == name,
            ContactGroup.id != group_id
        ).first()
        if conflict:
            return jsonify({"error": "A group with this name already exists"}), 409
        group.name = name

    if "color" in data:
        group.color = data["color"]

    db.session.commit()
    return jsonify(serialize_group(group)), 200


@contacts_bp.route("/groups/<int:group_id>", methods=["DELETE"])
@jwt_required()
def delete_group(group_id):
    owner_id = get_jwt_identity()
    group    = ContactGroup.query.filter_by(id=group_id, owner_id=owner_id).first_or_404()
    db.session.delete(group)
    db.session.commit()
    return jsonify({"deleted": group_id}), 200


@contacts_bp.route("/groups/<int:group_id>/members", methods=["GET"])
@jwt_required()
def list_members(group_id):
    owner_id = get_jwt_identity()
    group    = ContactGroup.query.filter_by(id=group_id, owner_id=owner_id).first_or_404()
    return jsonify(serialize_group(group)["members"]), 200


@contacts_bp.route("/groups/<int:group_id>/members", methods=["POST"])
@jwt_required()
def add_member(group_id):
    owner_id = get_jwt_identity()
    group    = ContactGroup.query.filter_by(id=group_id, owner_id=owner_id).first_or_404()
    data     = request.get_json() or {}

    user_id = data.get("user_id")
    email   = data.get("email")

    # Resolve by email if user_id not provided
    if not user_id and email:
        target = User.query.filter_by(email=email).first()
        if not target:
            return jsonify({"error": "User not found"}), 404
        user_id = target.id
    elif user_id:
        target = User.query.get(user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404
    else:
        return jsonify({"error": "user_id or email is required"}), 400

    # Cannot add yourself
    if int(user_id) == int(owner_id):
        return jsonify({"error": "Cannot add yourself to a contact group"}), 400

    # Already a member?
    existing = ContactGroupMember.query.filter_by(
        group_id=group_id, user_id=user_id
    ).first()
    if existing:
        return jsonify({"error": "User is already in this group"}), 409

    member = ContactGroupMember(group_id=group_id, user_id=user_id)
    db.session.add(member)
    db.session.commit()

    return jsonify({
        "user_id":   target.id,
        "full_name": target.full_name,
        "email":     target.email,
        "added_at":  member.added_at.isoformat(),
    }), 201


@contacts_bp.route("/groups/<int:group_id>/members/<int:user_id>", methods=["DELETE"])
@jwt_required()
def remove_member(group_id, user_id):
    owner_id = get_jwt_identity()
    ContactGroup.query.filter_by(id=group_id, owner_id=owner_id).first_or_404()

    member = ContactGroupMember.query.filter_by(
        group_id=group_id, user_id=user_id
    ).first_or_404()

    db.session.delete(member)
    db.session.commit()
    return jsonify({"removed": user_id, "from_group": group_id}), 200


@contacts_bp.route("/all", methods=["GET"])
@jwt_required()
def all_contacts():
    owner_id = get_jwt_identity()
    groups   = ContactGroup.query.filter_by(owner_id=owner_id).all()

    contacts_map = {}
    for group in groups:
        for m in group.members:
            uid = m.user_id
            if uid not in contacts_map:
                contacts_map[uid] = {
                    "user_id":    m.user_id,
                    "full_name":  m.user.full_name if m.user else "",
                    "email":      m.user.email if m.user else "",
                    "specialty":  getattr(m.user, 'specialty', ''),
                    "avatar_url": getattr(m.user, 'avatar_url', ''),
                    "groups":     [],
                }
            contacts_map[uid]["groups"].append({
                "id":    group.id,
                "name":  group.name,
                "color": group.color,
            })

    return jsonify(list(contacts_map.values())), 200