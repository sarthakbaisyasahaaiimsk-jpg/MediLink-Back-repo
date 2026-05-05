from flask import Blueprint, request, jsonify
from extensions import db
from models import Forum, Thread, ThreadComment
from datetime import datetime

community_bp = Blueprint('community', __name__)

# =========================
# CREATE FORUM
# =========================
@community_bp.route('/forums', methods=['POST'])
def create_forum():
    data = request.json

    if not data.get("name"):
        return jsonify({"error": "Forum name required"}), 400

    forum = Forum(
        name=data.get("name"),
        description=data.get("description"),
        created_by=data.get("created_by"),
        created_date=datetime.utcnow()
    )

    db.session.add(forum)
    db.session.commit()

    return jsonify(forum.to_dict()), 201


# =========================
# GET ALL FORUMS
# =========================
@community_bp.route('/forums', methods=['GET'])
def get_forums():
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))

    forums = Forum.query\
        .order_by(Forum.created_date.desc())\
        .paginate(page=page, per_page=limit, error_out=False)

    return jsonify({
        "forums": [f.to_dict() for f in forums.items],
        "total": forums.total,
        "pages": forums.pages,
        "current_page": page
    })


# =========================
# CREATE THREAD
# =========================
@community_bp.route('/forums/<int:forum_id>/threads', methods=['POST'])
def create_thread(forum_id):
    data = request.json

    if not data.get("title") or not data.get("content"):
        return jsonify({"error": "Title and content required"}), 400

    thread = Thread(
        forum_id=forum_id,
        title=data.get("title"),
        content=data.get("content"),
        created_by=data.get("created_by"),
        created_date=datetime.utcnow()
    )

    db.session.add(thread)
    db.session.commit()

    return jsonify(thread.to_dict()), 201


# =========================
# GET THREADS (with pagination)
# =========================
@community_bp.route('/forums/<int:forum_id>/threads', methods=['GET'])
def get_threads(forum_id):
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))

    threads = Thread.query\
        .filter_by(forum_id=forum_id)\
        .order_by(Thread.created_date.desc())\
        .paginate(page=page, per_page=limit, error_out=False)

    return jsonify({
        "threads": [t.to_dict() for t in threads.items],
        "total": threads.total,
        "pages": threads.pages,
        "current_page": page
    })

# =========================
# GET SINGLE THREAD + COMMENTS
# =========================
@community_bp.route('/threads/<int:thread_id>', methods=['GET'])
def get_thread(thread_id):
    thread = Thread.query.get_or_404(thread_id)

    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))

    comments = ThreadComment.query\
        .filter_by(thread_id=thread_id)\
        .order_by(ThreadComment.created_date.asc())\
        .paginate(page=page, per_page=limit, error_out=False)

    return jsonify({
        "thread": thread.to_dict(),
        "comments": [c.to_dict() for c in comments.items],
        "total_comments": comments.total,
        "pages": comments.pages,
        "current_page": page
    })

# =========================
# ADD COMMENT
# =========================
@community_bp.route('/threads/<int:thread_id>/comments', methods=['POST'])
def add_thread_comment(thread_id):
    data = request.json

    if not data.get("content"):
        return jsonify({"error": "Content required"}), 400

    comment = ThreadComment(
        thread_id=thread_id,
        content=data.get("content"),
        created_by=data.get("created_by"),
        created_date=datetime.utcnow()
    )

    db.session.add(comment)
    db.session.commit()

    return jsonify(comment.to_dict()), 201