from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Conversation, Message, User
from extensions import db
import json

conversations_bp = Blueprint("conversations", __name__)

# Get all conversations for current user
@conversations_bp.route("", methods=["GET"])
@jwt_required()
def get_conversations():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        # Get conversations where user is a participant
        conversations = Conversation.query.all()
        user_conversations = []
        
        for conv in conversations:
            participants = json.loads(conv.participants) if conv.participants else []
            if user.email in participants:
                user_conversations.append(conv.to_dict())
        
        return jsonify(user_conversations), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Get single conversation
@conversations_bp.route("/<int:id>", methods=["GET"])
def get_conversation(id):
    try:
        conversation = Conversation.query.get(id)
        if not conversation:
            return jsonify(error="Conversation not found"), 404
        return jsonify(conversation.to_dict()), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Create conversation
@conversations_bp.route("", methods=["POST"])
@jwt_required()
def create_conversation():
    try:
        data = request.json
        
        participants = data.get('participants', [])
        participant_names = data.get('participant_names', [])
        participant_photos = data.get('participant_photos', [])
        
        conversation = Conversation(
            participants=json.dumps(participants),
            participant_names=json.dumps(participant_names),
            participant_photos=json.dumps(participant_photos),
            is_group=data.get('is_group', False),
            group_name=data.get('group_name'),
            unread_count=json.dumps({p: 0 for p in participants})
        )
        
        db.session.add(conversation)
        db.session.commit()
        
        return jsonify(conversation.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Update conversation
@conversations_bp.route("/<int:id>", methods=["PUT"])
@jwt_required()
def update_conversation(id):
    try:
        conversation = Conversation.query.get(id)
        if not conversation:
            return jsonify(error="Conversation not found"), 404
        
        data = request.json
        
        if 'last_message' in data:
            conversation.last_message = data['last_message']
        if 'last_message_time' in data:
            from datetime import datetime
            conversation.last_message_time = datetime.fromisoformat(data['last_message_time'].replace('Z', '+00:00'))
        if 'last_message_sender' in data:
            conversation.last_message_sender = data['last_message_sender']
        if 'unread_count' in data:
            conversation.unread_count = json.dumps(data['unread_count'])
        if 'participant_names' in data:
            conversation.participant_names = json.dumps(data['participant_names'])
        if 'participant_photos' in data:
            conversation.participant_photos = json.dumps(data['participant_photos'])
        
        db.session.commit()
        return jsonify(conversation.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Delete conversation
@conversations_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_conversation(id):
    try:
        conversation = Conversation.query.get(id)
        if not conversation:
            return jsonify(error="Conversation not found"), 404
        
        # Also delete all messages in this conversation
        Message.query.filter_by(conversation_id=id).delete()
        db.session.delete(conversation)
        db.session.commit()
        
        return jsonify(msg="Conversation deleted"), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500
