from flask import Blueprint, request, jsonify, url_for, redirect, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import User, OtpCode
from extensions import db
import os
import random
import string
import uuid

auth_bp = Blueprint("auth", __name__)


# =========================
# OTP GENERATOR
# =========================
def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))


# =========================
# REGISTER (EMAIL/PASSWORD)
# =========================
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.json or {}

    if not data.get("email") or not data.get("password") or not data.get("phone"):
        return jsonify(error="email, password and phone are required"), 400

    if User.query.filter_by(email=data.get("email")).first():
        return jsonify(error="Email already registered"), 400

    if User.query.filter_by(phone=data.get("phone")).first():
        return jsonify(error="Phone already registered"), 400

    user = User(
        username=data.get("username"),
        email=data.get("email"),
        phone=data.get("phone"),
        full_name=data.get("full_name"),
        password=generate_password_hash(data.get("password")),
        verification_state="pending",
        is_verified=False,
        email_verified=False,
        phone_verified=False,
        is_admin=False
    )

    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))

    return jsonify(
        msg="registered",
        token=token,
        user=user.to_dict()
    ), 201


# =========================
# LOGIN (EMAIL/PASSWORD)
# =========================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json or {}

    user = User.query.filter_by(email=data.get("email")).first()

    if not user:
        return jsonify(error="invalid credentials"), 401

    if not user.password:
        return jsonify(error="Use Google login for this account"), 401

    if check_password_hash(user.password, data.get("password")):
        token = create_access_token(identity=str(user.id))
        return jsonify(
            access_token=token,
            token=token,
            user=user.to_dict()
        ), 200

    return jsonify(error="invalid credentials"), 401


# =========================
# GOOGLE LOGIN START
# =========================
@auth_bp.route("/google/login")
def google_login():
    google = current_app.oauth.google
    redirect_uri = url_for("auth.google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


# =========================
# GOOGLE CALLBACK (FIXED)
# =========================
@auth_bp.route("/google/callback")
def google_callback():
    google = current_app.oauth.google

    token = google.authorize_access_token()
    resp = google.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        token=token
    )
    user_info = resp.json()

    google_id = user_info["sub"]
    email = user_info["email"]

    # 1. Check google_id first
    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        # 2. Check email existing user
        user = User.query.filter_by(email=email).first()

        if user:
            # attach google to existing account
            user.google_id = google_id
            user.email_verified = True
            user.is_verified = True
        else:
            # create new user safely
            base_username = email.split("@")[0]
            unique_username = f"{base_username}_{uuid.uuid4().hex[:6]}"

            user = User(
                username=unique_username,
                email=email,
                phone=None,
                password=None,
                full_name=user_info.get("name", "Google User"),
                verification_state="verified",
                is_verified=True,
                email_verified=True,
                phone_verified=False,
                google_id=google_id,
                is_admin=False
            )
            db.session.add(user)

    db.session.commit()

    access_token = create_access_token(identity=str(user.id))

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return redirect(f"{frontend_url}/auth/callback?token={access_token}")


# =========================
# CURRENT USER
# =========================
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if not user:
        return jsonify(error="User not found"), 404

    return jsonify(user.to_dict()), 200


# =========================
# OTP (UNCHANGED SAFE)
# =========================
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

    otp = OtpCode(
        user_email=email,
        user_phone=phone,
        code=code
    )

    db.session.add(otp)
    db.session.commit()

    print(f"DEBUG OTP: {email} -> {code}")

    return jsonify(message='OTP sent'), 200


@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json or {}
    email = data.get('email')
    phone = data.get('phone')
    otp_code = data.get('otp')

    record = OtpCode.query.filter_by(
        user_email=email,
        user_phone=phone,
        code=otp_code
    ).order_by(OtpCode.id.desc()).first()

    if not record:
        return jsonify(error='invalid otp'), 400

    user = User.query.filter_by(email=email, phone=phone).first()

    if not user:
        return jsonify(error='User not found'), 404

    user.email_verified = True
    user.phone_verified = True

    db.session.commit()

    return jsonify(message='OTP verified', user=user.to_dict()), 200