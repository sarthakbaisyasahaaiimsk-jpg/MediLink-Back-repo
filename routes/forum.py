from flask import Blueprint, request, jsonify
from datetime import datetime
from extensions import db
from models import Case, Comment
import json

forum_bp = Blueprint('forum', __name__)

# ================================
# GET ALL CASES (with pagination + optional filters)
# ================================
@forum_bp.route('/cases', methods=['GET'])
def get_cases():
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    search = request.args.get('search', '')
    specialty = request.args.get('specialty', '')
    status = request.args.get('status', '')

    query = Case.query

    # 🔍 Search by title or complaint
    if search:
        query = query.filter(
            Case.title.ilike(f"%{search}%") |
            Case.chief_complaint.ilike(f"%{search}%")
        )

    # 🏷️ Filter by specialty
    if specialty:
        query = query.filter(Case.specialty_tags.ilike(f"%{specialty}%"))

    # 📌 Filter by status
    if status:
        query = query.filter_by(status=status)

    cases = query.order_by(Case.created_date.desc()) \
        .paginate(page=page, per_page=limit)

    return jsonify({
        "cases": [c.to_dict() for c in cases.items],
        "total": cases.total,
        "page": page,
        "pages": cases.pages
    })


# ================================
# CREATE NEW CASE
# ================================
@forum_bp.route('/cases', methods=['POST'])
def create_case():
    data = request.json

    try:
        new_case = Case(
            title=data.get('title'),
            chief_complaint=data.get('chief_complaint'),
            description=data.get('description'),
            patient_age=data.get('patient_age'),
            patient_gender=data.get('patient_gender'),
            history=data.get('history'),
            examination_findings=data.get('examination_findings'),
            investigations=data.get('investigations'),
            current_treatment=data.get('current_treatment'),
            question=data.get('question'),
            specialty_tags=",".join(data.get('specialty_tags', [])),
            created_by=data.get('created_by'),
            created_date=datetime.utcnow()
        )

        db.session.add(new_case)
        db.session.commit()

        return jsonify(new_case.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ================================
# GET SINGLE CASE
# ================================
@forum_bp.route('/cases/<int:case_id>', methods=['GET'])
def get_case(case_id):
    case = Case.query.get_or_404(case_id)

    # Fetch comments
    comments = Comment.query.filter_by(case_id=case_id) \
        .order_by(Comment.created_date.asc()).all()

    return jsonify({
        "case": case.to_dict(),
        "comments": [c.to_dict() for c in comments]
    })


# ================================
# ADD COMMENT TO CASE
# ================================
@forum_bp.route('/cases/<int:case_id>/comments', methods=['POST'])
def add_comment(case_id):
    data = request.json

    try:
        comment = Comment(
            case_id=case_id,
            commenter_id=data.get('email'),
            commenter_name=data.get('name'),
            commenter_specialty=data.get('specialty'),
            content=data.get('content'),
            created_date=datetime.utcnow(),
            liked_by=json.dumps([]),
            disliked_by=json.dumps([]),
            replies=json.dumps([])
        )

        db.session.add(comment)

        # update discussion count
        case = Case.query.get(case_id)
        if case:
            case.discussion_count += 1

        db.session.commit()

        return jsonify(comment.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ================================
# LIKE COMMENT
# ================================
@forum_bp.route('/comments/<int:comment_id>/like', methods=['POST'])
def like_comment(comment_id):
    data = request.json
    user_email = data.get("email")

    comment = Comment.query.get_or_404(comment_id)

    liked_by = json.loads(comment.liked_by or "[]")

    if user_email not in liked_by:
        liked_by.append(user_email)
        comment.likes += 1

    comment.liked_by = json.dumps(liked_by)

    db.session.commit()

    return jsonify({"message": "Liked", "likes": comment.likes})


# ================================
# DISLIKE COMMENT
# ================================
@forum_bp.route('/comments/<int:comment_id>/dislike', methods=['POST'])
def dislike_comment(comment_id):
    data = request.json
    user_email = data.get("email")

    comment = Comment.query.get_or_404(comment_id)

    disliked_by = json.loads(comment.disliked_by or "[]")

    if user_email not in disliked_by:
        disliked_by.append(user_email)
        comment.dislikes += 1

    comment.disliked_by = json.dumps(disliked_by)

    db.session.commit()

    return jsonify({"message": "Disliked", "dislikes": comment.dislikes})


# ================================
# DELETE CASE (optional - admin)
# ================================
@forum_bp.route('/cases/<int:case_id>', methods=['DELETE'])
def delete_case(case_id):
    case = Case.query.get_or_404(case_id)

    db.session.delete(case)
    db.session.commit()

    return jsonify({"message": "Case deleted"})


# ================================
# DELETE COMMENT
# ================================
@forum_bp.route('/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)

    db.session.delete(comment)
    db.session.commit()

    return jsonify({"message": "Comment deleted"})