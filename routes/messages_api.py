from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Message, User
from extensions import db
from datetime import datetime
import json

def verify_user_is_doctor():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return None, jsonify(error='User not found'), 404
    if not user.is_verified:
        return None, jsonify(error='Doctor verification required for this action'), 403
    return user, None, None

messages_api_bp = Blueprint("messages_api", __name__)

# Get messages with filtering
@messages_api_bp.route("", methods=["GET"])
@jwt_required()
def get_messages():
    try:
        conversation_id = request.args.get('conversation_id')
        sender_id = request.args.get('sender_id')
        sort = request.args.get('sort', 'created_date')
        
        query = Message.query
        
        if conversation_id:
            query = query.filter_by(conversation_id=conversation_id)
        if sender_id:
            query = query.filter_by(sender_id=sender_id)
        
        # Handle sorting
        if sort.startswith('-'):
            query = query.order_by(getattr(Message, sort[1:]).desc())
        else:
            query = query.order_by(getattr(Message, sort).asc())
        
        messages = query.all()
        return jsonify([m.to_dict() for m in messages]), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Get single message
@messages_api_bp.route("/<int:id>", methods=["GET"])
def get_message(id):
    try:
        message = Message.query.get(id)
        if not message:
            return jsonify(error="Message not found"), 404
        return jsonify(message.to_dict()), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Create/Send message
@messages_api_bp.route("", methods=["POST"])
@jwt_required()
def create_message():
    user, err_response, status = verify_user_is_doctor()
    if err_response:
        return err_response, status
    try:
        data = request.json
        
        message = Message(
            conversation_id=data.get('conversation_id'),
            sender_id=data.get('sender_id'),
            sender_name=data.get('sender_name'),
            sender_photo=data.get('sender_photo'),
            receiver_id=data.get('receiver_id'),
            group_id=data.get('group_id'),
            content=data.get('content'),
            message_type=data.get('message_type', 'text'),
            file_url=data.get('file_url'),
            is_read=data.get('is_read', False),
            read_by=json.dumps(data.get('read_by', []))
        )
        
        db.session.add(message)
        db.session.commit()
        
        return jsonify(message.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Update message
@messages_api_bp.route("/<int:id>", methods=["PUT"])
@jwt_required()
def update_message(id):
    try:
        message = Message.query.get(id)
        if not message:
            return jsonify(error="Message not found"), 404
        
        data = request.json
        
        if 'content' in data:
            message.content = data['content']
        if 'is_read' in data:
            message.is_read = data['is_read']
        if 'read_by' in data:
            message.read_by = json.dumps(data['read_by'])
        if 'message_type' in data:
            message.message_type = data['message_type']
        if 'file_url' in data:
            message.file_url = data['file_url']
        
        db.session.commit()
        return jsonify(message.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Delete message
@messages_api_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_message(id):
    try:
        message = Message.query.get(id)
        if not message:
            return jsonify(error="Message not found"), 404
        
        db.session.delete(message)
        db.session.commit()
        
        return jsonify(msg="Message deleted"), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500


# ===== NEW ENDPOINTS FOR ADVANCED FEATURES =====

# Add or remove emoji reaction to message
@messages_api_bp.route("/<int:id>/reactions", methods=["POST"])
@jwt_required()
def add_reaction(id):
    """Add emoji reaction to message"""
    try:
        message = Message.query.get(id)
        if not message:
            return jsonify(error="Message not found"), 404
        
        user_email = get_jwt_identity()
        data = request.json
        emoji = data.get('emoji')
        action = data.get('action', 'add')  # add or remove
        
        if not emoji:
            return jsonify(error="Emoji required"), 400
        
        reactions = json.loads(message.reactions) if message.reactions else {}
        
        if action == 'add':
            if emoji not in reactions:
                reactions[emoji] = []
            if user_email not in reactions[emoji]:
                reactions[emoji].append(user_email)
        elif action == 'remove':
            if emoji in reactions and user_email in reactions[emoji]:
                reactions[emoji].remove(user_email)
                if not reactions[emoji]:
                    del reactions[emoji]
        
        message.reactions = json.dumps(reactions)
        db.session.commit()
        
        return jsonify(message.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500


# Pin/Unpin message
@messages_api_bp.route("/<int:id>/pin", methods=["POST"])
@jwt_required()
def pin_message(id):
    """Pin or unpin a message"""
    try:
        message = Message.query.get(id)
        if not message:
            return jsonify(error="Message not found"), 404
        
        user_email = get_jwt_identity()
        action = request.json.get('action', 'pin')  # pin or unpin
        
        if action == 'pin':
            message.is_pinned = True
            message.pinned_by = user_email
            message.pinned_date = datetime.utcnow()
        elif action == 'unpin':
            message.is_pinned = False
            message.pinned_by = None
            message.pinned_date = None
        
        db.session.commit()
        return jsonify(message.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500


# Archive/Unarchive message
@messages_api_bp.route("/<int:id>/archive", methods=["POST"])
@jwt_required()
def archive_message(id):
    """Archive or unarchive a message (read-only)"""
    try:
        message = Message.query.get(id)
        if not message:
            return jsonify(error="Message not found"), 404
        
        user_email = get_jwt_identity()
        action = request.json.get('action', 'archive')  # archive or restore
        
        if action == 'archive':
            message.is_archived = True
            message.archived_by = user_email
            message.archived_date = datetime.utcnow()
        elif action == 'restore':
            message.is_archived = False
            message.archived_by = None
            message.archived_date = None
        
        db.session.commit()
        return jsonify(message.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500


# Search messages
@messages_api_bp.route("/search", methods=["GET"])
@jwt_required()
def search_messages():
    """Search messages by content, supports pagination"""
    try:
        conversation_id = request.args.get('conversation_id')
        query = request.args.get('q', '')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        search_query = Message.query
        
        if conversation_id:
            search_query = search_query.filter_by(conversation_id=conversation_id)
        
        # Search in content (case-insensitive)
        if query:
            search_query = search_query.filter(
                Message.content.ilike(f"%{query}%")
            )
        
        # Exclude archived messages
        search_query = search_query.filter_by(is_archived=False)
        
        # Get total count and paginated results
        total = search_query.count()
        messages = search_query.order_by(Message.created_date.desc()).limit(limit).offset(offset).all()
        
        return jsonify({
            'total': total,
            'limit': limit,
            'offset': offset,
            'messages': [m.to_dict() for m in messages]
        }), 200
    except Exception as e:
        return jsonify(error=str(e)), 500


# Get pinned messages in conversation
@messages_api_bp.route("/pinned", methods=["GET"])
@jwt_required()
def get_pinned_messages():
    """Get all pinned messages in a conversation"""
    try:
        conversation_id = request.args.get('conversation_id')
        
        if not conversation_id:
            return jsonify(error="conversation_id required"), 400
        
        messages = Message.query.filter_by(
            conversation_id=conversation_id,
            is_pinned=True
        ).order_by(Message.pinned_date.desc()).all()
        
        return jsonify([m.to_dict() for m in messages]), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
