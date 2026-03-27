from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import DoctorProfile, User
from extensions import db
import json

doctor_profile_bp = Blueprint("doctor_profiles", __name__)

# Get all doctor profiles with filtering
@doctor_profile_bp.route("", methods=["GET"])
def get_profiles():
    try:
        created_by = request.args.get('created_by')
        specialty = request.args.get('specialty')
        sort = request.args.get('sort', 'id')
        
        query = DoctorProfile.query
        
        if created_by:
            query = query.filter_by(created_by=created_by)
        if specialty:
            query = query.filter_by(specialty=specialty)
        
        # Handle sorting
        if sort.startswith('-'):
            query = query.order_by(getattr(DoctorProfile, sort[1:]).desc())
        else:
            query = query.order_by(getattr(DoctorProfile, sort).asc())
        
        profiles = query.all()
        return jsonify([p.to_dict() for p in profiles]), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Get single profile
@doctor_profile_bp.route("/<int:id>", methods=["GET"])
def get_profile(id):
    try:
        profile = DoctorProfile.query.get(id)
        if not profile:
            return jsonify(error="Profile not found"), 404
        return jsonify(profile.to_dict()), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Create profile
@doctor_profile_bp.route("", methods=["POST"])
@jwt_required()
def create_profile():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.json
        
        profile = DoctorProfile(
            created_by=data.get('created_by', user.email),
            full_name=data.get('full_name'),
            profile_photo=data.get('profile_photo'),
            specialty=data.get('specialty'),
            sub_specialty=data.get('sub_specialty'),
            qualifications=json.dumps(data.get('qualifications', [])),
            registration_number=data.get('registration_number'),
            location_city=data.get('location_city'),
            location_country=data.get('location_country'),
            years_experience=data.get('years_experience'),
            institution_name=data.get('institution_name'),
            institution_type=data.get('institution_type'),
            bio=data.get('bio'),
            interests=json.dumps(data.get('interests', [])),
            response_count=0,
            helpful_votes_received=0
        )
        
        db.session.add(profile)
        db.session.commit()
        
        return jsonify(profile.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Update profile
@doctor_profile_bp.route("/<int:id>", methods=["PUT"])
@jwt_required()
def update_profile(id):
    try:
        profile = DoctorProfile.query.get(id)
        if not profile:
            return jsonify(error="Profile not found"), 404
        
        data = request.json
        
        if 'full_name' in data:
            profile.full_name = data['full_name']
        if 'profile_photo' in data:
            profile.profile_photo = data['profile_photo']
        if 'specialty' in data:
            profile.specialty = data['specialty']
        if 'sub_specialty' in data:
            profile.sub_specialty = data['sub_specialty']
        if 'qualifications' in data:
            profile.qualifications = json.dumps(data['qualifications'])
        if 'registration_number' in data:
            profile.registration_number = data['registration_number']
        if 'location_city' in data:
            profile.location_city = data['location_city']
        if 'location_country' in data:
            profile.location_country = data['location_country']
        if 'years_experience' in data:
            profile.years_experience = data['years_experience']
        if 'institution_name' in data:
            profile.institution_name = data['institution_name']
        if 'institution_type' in data:
            profile.institution_type = data['institution_type']
        if 'bio' in data:
            profile.bio = data['bio']
        if 'interests' in data:
            profile.interests = json.dumps(data['interests'])
        if 'response_count' in data:
            profile.response_count = data['response_count']
        if 'helpful_votes_received' in data:
            profile.helpful_votes_received = data['helpful_votes_received']
        
        db.session.commit()
        return jsonify(profile.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Delete profile
@doctor_profile_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_profile(id):
    try:
        profile = DoctorProfile.query.get(id)
        if not profile:
            return jsonify(error="Profile not found"), 404
        
        db.session.delete(profile)
        db.session.commit()
        
        return jsonify(msg="Profile deleted"), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500
