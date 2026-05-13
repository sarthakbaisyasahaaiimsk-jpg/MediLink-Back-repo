from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import User, Follow, DoctorProfile
from sqlalchemy import func

follows_bp = Blueprint('follows', __name__)


# ── Toggle follow / unfollow ──────────────────────────────────────────────────
@follows_bp.route('/<int:target_user_id>', methods=['POST'])
@jwt_required()
def toggle_follow(target_user_id):
    current_user_id = get_jwt_identity()

    if current_user_id == target_user_id:
        return jsonify({'error': 'Cannot follow yourself'}), 400

    existing = Follow.query.filter_by(
        follower_id=current_user_id,
        following_id=target_user_id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        action = 'unfollowed'
    else:
        follow = Follow(follower_id=current_user_id, following_id=target_user_id)
        db.session.add(follow)
        db.session.commit()
        action = 'followed'

    follower_count = Follow.query.filter_by(following_id=target_user_id).count()
    return jsonify({
        'action':         action,
        'follower_count': follower_count,
        'is_following':   action == 'followed',
    }), 200


# ── List of user_ids current user follows ────────────────────────────────────
@follows_bp.route('/following', methods=['GET'])
@jwt_required()
def get_following():
    current_user_id = get_jwt_identity()
    rows = Follow.query.filter_by(follower_id=current_user_id).all()
    return jsonify({'following': [r.following_id for r in rows]}), 200


# ── Bulk stats for a list of user_ids (used by Network page) ─────────────────
@follows_bp.route('/bulk-stats', methods=['POST'])
@jwt_required()
def bulk_stats():
    current_user_id = get_jwt_identity()
    data     = request.get_json(silent=True) or {}
    user_ids = data.get('user_ids', [])

    if not user_ids:
        return jsonify({'stats': {}}), 200

    counts = db.session.query(
        Follow.following_id,
        func.count(Follow.follower_id).label('cnt')
    ).filter(Follow.following_id.in_(user_ids)).group_by(Follow.following_id).all()

    follower_map = {row.following_id: row.cnt for row in counts}

    following_rows = Follow.query.filter(
        Follow.follower_id == current_user_id,
        Follow.following_id.in_(user_ids)
    ).all()
    following_set = {r.following_id for r in following_rows}

    stats = {
        uid: {
            'follower_count': follower_map.get(uid, 0),
            'is_following':   uid in following_set,
        }
        for uid in user_ids
    }
    return jsonify({'stats': stats}), 200


# ── Public profile endpoint ───────────────────────────────────────────────────
@follows_bp.route('/profile/<int:target_user_id>', methods=['GET'])
@jwt_required()
def get_public_profile(target_user_id):
    current_user_id = get_jwt_identity()

    target_user = User.query.get(target_user_id)
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    # DoctorProfile linked via email (created_by) since user_id may be new
    profile = DoctorProfile.query.filter(
        (DoctorProfile.user_id == target_user_id) |
        (DoctorProfile.created_by == target_user.email)
    ).first()

    if not profile:
        return jsonify({'error': 'Profile not found'}), 404

    visibility = getattr(profile, 'profile_visibility', 'public') or 'public'
    if visibility != 'public' and current_user_id != target_user_id:
        return jsonify({'error': 'This profile is private'}), 403

    follower_count  = Follow.query.filter_by(following_id=target_user_id).count()
    following_count = Follow.query.filter_by(follower_id=target_user_id).count()
    is_following    = Follow.query.filter_by(
        follower_id=current_user_id,
        following_id=target_user_id
    ).first() is not None

    return jsonify({
        'user': {
            'id':        target_user.id,
            'email':     target_user.email,
            'full_name': target_user.full_name,
        },
        'profile':         profile.to_dict(),
        'follower_count':  follower_count,
        'following_count': following_count,
        'is_following':    is_following,
    }), 200