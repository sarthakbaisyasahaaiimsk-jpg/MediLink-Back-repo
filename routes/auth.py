from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import User, OtpCode
from extensions import db
from flask import url_for, redirect, session, current_app
from authlib.integrations.flask_client import OAuth
from config import Config
import os
import random
import string


auth_bp = Blueprint("auth", __name__)


def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.json

    if not data.get("email") or not data.get("password") or not data.get("phone"):
        return jsonify(error="email, password and phone are required"), 400

    if User.query.filter_by(email=data.get("email")).first():
        return jsonify(error="Email already registered"), 400
    if User.query.filter_by(phone=data.get("phone")).first():
        return jsonify(error="Phone already registered"), 400

    admin_code = data.get("admin_code")
    is_admin = False
    if admin_code and admin_code == os.environ.get('ADMIN_SECRET', 'admin-secret'):
        is_admin = True

    import uuid

if not user:
    base_username = email.split('@')[0]
    unique_username = f"{base_username}_{uuid.uuid4().hex[:6]}"

    user = User(
        username=unique_username,
        email=email,
        phone=None,
        password=None,
        full_name=user_info.get('name', 'Google User'),
        verification_state='verified',
        is_verified=True,
        email_verified=True,
        phone_verified=False,
        google_id=google_id,
        is_admin=False
    )
    db.session.add(user)
    db.session.commit()
    db.session.add(user)
    db.session.commit()

    # ✅ identity must be a string for Flask-JWT-Extended v4+
    token = create_access_token(identity=str(user.id))
    return jsonify(
        msg="registered",
        token=token,
        user=user.to_dict()
    ), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(email=data.get("email")).first()

    if not user:
        return jsonify(error="invalid credentials"), 401

    # ✅ User signed up via Google — has no password
    if not user.password:
        return jsonify(error="This account uses Google login. Please sign in with Google."), 401

    if check_password_hash(user.password, data.get("password")):
        # ✅ identity must be a string for Flask-JWT-Extended v4+
        token = create_access_token(identity=str(user.id))
        return jsonify(
            access_token=token,
            token=token,
            user=user.to_dict()
        ), 200

    return jsonify(error="invalid credentials"), 401


@auth_bp.route('/send-otp', methods=['POST'])
def send_otp():
    data = request.json or {}
    email = data.get('email')
    phone = data.get('phone')
    if not email or not phone:
        return jsonify(error='email and phone are required'), 400

    user = User.query.filter_by(email=email, phone=phone).first()
    if not user:
        return jsonify(error='User not found'), 404

    code = generate_otp()
    otp = OtpCode(user_email=email, user_phone=phone, code=code)
    db.session.add(otp)
    db.session.commit()

    print(f"DEBUG OTP for {email}/{phone}: {code}")

    return jsonify(message='OTP sent'), 200


@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json or {}
    email = data.get('email')
    phone = data.get('phone')
    otp_code = data.get('otp')
    if not email or not phone or not otp_code:
        return jsonify(error='email, phone and otp are required'), 400

    record = OtpCode.query.filter_by(user_email=email, user_phone=phone, code=otp_code).order_by(OtpCode.id.desc()).first()
    if not record:
        return jsonify(error='invalid otp'), 400

    user = User.query.filter_by(email=email, phone=phone).first()
    if not user:
        return jsonify(error='User not found'), 404

    user.email_verified = True
    user.phone_verified = True
    if user.is_verified:
        user.verification_state = 'verified'
    db.session.commit()

    return jsonify(message='OTP verified', user=user.to_dict()), 200


@auth_bp.route('/verify-doctor', methods=['POST'])
@jwt_required()
def verify_doctor():
    data = request.json or {}
    user_id = int(get_jwt_identity())  # ✅ convert back to int for DB lookup
    user = User.query.get(user_id)
    if not user:
        return jsonify(error='User not found'), 404

    full_name = data.get('full_name') or user.full_name
    registration_number = data.get('nmc_or_smc_number') or data.get('registration_number')
    degree = data.get('degree')

    if not registration_number:
        return jsonify(error='nmc_or_smc_number is required'), 400

    user.full_name = full_name
    user.nmc_number = registration_number
    user.degree = degree

    registry_ok = False
    if registration_number.startswith('NMC-'):
        registry_ok = True
    elif registration_number.startswith('SMC-'):
        registry_ok = True

    if registry_ok:
        user.is_verified = True
        user.verification_state = 'verified'
    else:
        user.is_verified = False
        user.verification_state = 'unverified'

    if user.email_verified and user.phone_verified and user.is_verified:
        user.verification_state = 'verified'

    db.session.commit()

    return jsonify(is_verified=user.is_verified, verification_state=user.verification_state, user=user.to_dict()), 200


@auth_bp.route('/admin/users', methods=['GET'])
@jwt_required()
def get_all_users():
    admin_user = User.query.get(int(get_jwt_identity()))  # ✅ convert to int
    if not admin_user or not admin_user.is_admin:
        return jsonify(error='admin access required'), 403

    users = User.query.all()
    return jsonify(users=[u.to_dict() for u in users]), 200


@auth_bp.route('/admin/verify-user', methods=['POST'])
@jwt_required()
def admin_verify_user():
    admin_user = User.query.get(int(get_jwt_identity()))  # ✅ convert to int
    if not admin_user or not admin_user.is_admin:
        return jsonify(error='admin access required'), 403

    data = request.json or {}
    user_id = data.get('user_id')
    new_state = data.get('verification_state', 'verified')
    user = User.query.get(user_id)
    if not user:
        return jsonify(error='user not found'), 404

    user.verification_state = new_state
    user.is_verified = new_state == 'verified'
    db.session.commit()
    return jsonify(user=user.to_dict()), 200


@auth_bp.route('/ocr-degree', methods=['POST'])
@jwt_required()
def ocr_degree():
    return jsonify(text='Simulated OCR degree text'), 200


@auth_bp.route("/google/login")
def google_login():
    google = current_app.oauth.google
    redirect_uri = url_for("auth.google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route("/google/callback")
def google_callback():
    google = current_app.oauth.google
    token = google.authorize_access_token()
    resp = google.get("https://openidconnect.googleapis.com/v1/userinfo", token=token)
    user_info = resp.json()

    google_id = user_info['sub']
    email = user_info['email']

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User(
         username=email.split('@')[0],
          email=email,
          phone=None,                 # ✅ IMPORTANT FIX
         password=None,              # ✅ IMPORTANT FIX
         full_name=user_info.get('name', 'Google User'),
         verification_state='verified',
         is_verified=True,
         email_verified=True,
         phone_verified=False,
         google_id=google_id,
         is_admin=False
     )
        db.session.add(user)
        db.session.commit()

    # ✅ identity must be a string for Flask-JWT-Extended v4+
    access_token = create_access_token(identity=str(user.id))

    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    frontend_redirect = f"{frontend_url}/auth/callback?token={access_token}"
    return redirect(frontend_redirect)


# ✅ @jwt_required() so token is actually validated
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    try:
        user_id = int(get_jwt_identity())  # ✅ convert back to int for DB lookup
        user = User.query.get(user_id)

        if not user:
            return jsonify(error="User not found"), 404

        return jsonify(user.to_dict()), 200
    except Exception as e:
        return jsonify(error="Authentication failed", message=str(e)), 401