from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import Message, User, Group, GroupMember

message_bp = Blueprint("messages", __name__)

# ✅ SEND MESSAGE
@message_bp.route("/send", methods=["POST"])
@jwt_required()
def send():
    data = request.json

    msg = Message(
        sender_id=get_jwt_identity(),
        receiver_id=data.get("receiver_id"),
        group_id=data.get("group_id"),
        content=data.get("content"),
    )

    db.session.add(msg)
    db.session.commit()

    return jsonify({
        "id": msg.id,
        "content": msg.content,
        "sender_id": msg.sender_id,
        "receiver_id": msg.receiver_id,
        "group_id": msg.group_id,
        "timestamp": msg.timestamp.isoformat()
    })


# ✅ GET CONVERSATIONS
@message_bp.route("/conversations", methods=["GET"])
@jwt_required()
def get_conversations():
    current_user_id = get_jwt_identity()

    # ✅ MUST be inside function
    group_ids = db.session.query(GroupMember.group_id).filter_by(user_id=current_user_id)

    messages = Message.query.filter(
        (Message.sender_id == current_user_id) |
        (Message.receiver_id == current_user_id) |
        (Message.group_id.in_(group_ids))
    ).order_by(Message.timestamp.desc()).all()

    conversations = {}

    for msg in messages:
        # 🔑 conversation key
        if msg.group_id:
            key = f"group_{msg.group_id}"
        else:
            other_user = msg.receiver_id if msg.sender_id == current_user_id else msg.sender_id
            key = f"user_{other_user}"

        if key not in conversations:
            conversations[key] = {
                "participants": [],
                "participant_names": [],
                "participant_photos": [],
                "last_message": msg.content,
                "last_message_time": msg.timestamp.isoformat(),
                "unread_count": {str(current_user_id): 0},
                "is_group": bool(msg.group_id),
                "group_name": None
            }

            # 👤 1-to-1
            if not msg.group_id:
                other_user = msg.receiver_id if msg.sender_id == current_user_id else msg.sender_id
                user = db.session.get(User, other_user)

                conversations[key]["participants"] = [current_user_id, other_user]
                conversations[key]["participant_names"] = [
                    "You",
                    user.username if user else "User"
                ]
                conversations[key]["participant_photos"] = [None, None]

            # 👥 group
            else:
                group = db.session.get(Group, msg.group_id)
                conversations[key]["group_name"] = group.name if group else "Group"

        else:
            conversations[key]["unread_count"].setdefault(str(current_user_id), 0)
            if msg.sender_id != current_user_id:
                conversations[key]["unread_count"][str(current_user_id)] += 1

    return jsonify(list(conversations.values()))