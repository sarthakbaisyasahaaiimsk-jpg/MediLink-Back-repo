from flask import Blueprint, request, jsonify
from extensions import db
from sqlalchemy import text

keys_bp = Blueprint('keys', __name__)


@keys_bp.route('/register', methods=['POST'])
def register_public_key():
    """Called by the frontend on every session start to upsert the doctor's public key."""
    data = request.get_json()
    user_id = data.get('user_id')
    public_key = data.get('public_key')

    if not user_id or not public_key:
        return jsonify({'error': 'Missing user_id or public_key'}), 400

    db.session.execute(text("""
        INSERT INTO public_keys (user_id, public_key, updated_at)
        VALUES (:user_id, :public_key, NOW())
        ON CONFLICT (user_id)
        DO UPDATE SET public_key = EXCLUDED.public_key, updated_at = NOW()
    """), {'user_id': user_id, 'public_key': public_key})
    db.session.commit()

    return jsonify({'status': 'ok'})


@keys_bp.route('/<path:user_id>', methods=['GET'])
def get_public_key(user_id):
    """Called by the frontend to fetch a recipient's public key before deriving the shared secret."""
    # <path:user_id> handles emails that contain @ and .
    row = db.session.execute(
        text("SELECT public_key FROM public_keys WHERE user_id = :user_id"),
        {'user_id': user_id}
    ).fetchone()

    if not row:
        return jsonify({'error': 'Key not found'}), 404

    return jsonify({'public_key': row[0]})