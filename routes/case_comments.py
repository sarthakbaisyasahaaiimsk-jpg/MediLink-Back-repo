from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Comment, User
from extensions import db
import json

case_comments_bp = Blueprint("case_comments", __name__)

# Get all comments with filtering
@case_comments_bp.route("", methods=["GET"])
def get_comments():
    try:
        case_id = request.args.get('case_id')
        commenter_id = request.args.get('commenter_id')
        sort = request.args.get('sort', 'created_date')
        
        query = Comment.query
        
        if case_id:
            query = query.filter_by(case_id=case_id)
        if commenter_id:
            query = query.filter_by(commenter_id=commenter_id)
        
        # Handle sorting
        if sort.startswith('-'):
            query = query.order_by(getattr(Comment, sort[1:]).desc())
        else:
            query = query.order_by(getattr(Comment, sort).asc())
        
        comments = query.all()
        return jsonify([c.to_dict() for c in comments]), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Get single comment
@case_comments_bp.route("/<int:id>", methods=["GET"])
def get_comment(id):
    try:
        comment = Comment.query.get(id)
        if not comment:
            return jsonify(error="Comment not found"), 404
        return jsonify(comment.to_dict()), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

def verify_user_is_doctor():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return None, jsonify(error='User not found'), 404
    if not user.is_verified:
        return None, jsonify(error='Doctor verification required for this action'), 403
    return user, None, None


# Create comment
@case_comments_bp.route("", methods=["POST"])
@jwt_required()
def create_comment():
    user, err_response, status = verify_user_is_doctor()
    if err_response:
        return err_response, status
    try:
        data = request.json
        
        comment = Comment(
            case_id=data.get('case_id'),
            user_id=data.get('user_id'),
            commenter_id=data.get('commenter_id'),
            commenter_name=data.get('commenter_name'),
            commenter_specialty=data.get('commenter_specialty'),
            commenter_qualifications=json.dumps(data.get('commenter_qualifications', [])),
            commenter_photo=data.get('commenter_photo'),
            content=data.get('content'),
            is_treatment_suggestion=data.get('is_treatment_suggestion', False),
            likes=data.get('likes', 0),
            dislikes=data.get('dislikes', 0),
            liked_by=json.dumps(data.get('liked_by', [])),
            disliked_by=json.dumps(data.get('disliked_by', [])),
            replies=json.dumps(data.get('replies', []))
        )
        
        db.session.add(comment)
        db.session.commit()
        
        return jsonify(comment.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Update comment
@case_comments_bp.route("/<int:id>", methods=["PUT"])
@jwt_required()
def update_comment(id):
    user, err_response, status = verify_user_is_doctor()
    if err_response:
        return err_response, status
    try:
        comment = Comment.query.get(id)
        if not comment:
            return jsonify(error="Comment not found"), 404
        
        data = request.json
        
        if 'content' in data:
            comment.content = data['content']
        if 'likes' in data:
            comment.likes = data['likes']
        if 'dislikes' in data:
            comment.dislikes = data['dislikes']
        if 'liked_by' in data:
            comment.liked_by = json.dumps(data['liked_by'])
        if 'disliked_by' in data:
            comment.disliked_by = json.dumps(data['disliked_by'])
        if 'replies' in data:
            comment.replies = json.dumps(data['replies'])
        if 'is_treatment_suggestion' in data:
            comment.is_treatment_suggestion = data['is_treatment_suggestion']
        
        db.session.commit()
        return jsonify(comment.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Delete comment
@case_comments_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_comment(id):
    user, err_response, status = verify_user_is_doctor()
    if err_response:
        return err_response, status
    try:
        comment = Comment.query.get(id)
        if not comment:
            return jsonify(error="Comment not found"), 404
        
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify(msg="Comment deleted"), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Add reply to comment
@case_comments_bp.route("/<int:id>/reply", methods=["POST"])
@jwt_required()
def add_reply(id):
    try:
        comment = Comment.query.get(id)
        if not comment:
            return jsonify(error="Comment not found"), 404
        
        data = request.json
        replies = json.loads(comment.replies) if comment.replies else []
        
        new_reply = {
            "id": str(len(replies) + 1),
            "user_id": data.get('user_id'),
            "user_name": data.get('user_name'),
            "user_photo": data.get('user_photo'),
            "content": data.get('content'),
            "created_at": data.get('created_at')
        }
        
        replies.append(new_reply)
        comment.replies = json.dumps(replies)
        
        db.session.commit()
        return jsonify(comment.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500
