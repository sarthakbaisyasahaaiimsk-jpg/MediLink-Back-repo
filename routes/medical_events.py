from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import MedicalEvent
from extensions import db
import json

medical_events_bp = Blueprint("medical_events", __name__)

# Get all medical events with filtering
@medical_events_bp.route("", methods=["GET"])
def get_events():
    try:
        event_type = request.args.get('event_type')
        specialty = request.args.get('specialty')
        is_online = request.args.get('is_online')
        sort = request.args.get('sort', 'date')
        
        query = MedicalEvent.query
        
        if event_type:
            query = query.filter_by(event_type=event_type)
        if specialty:
            query = query.filter(MedicalEvent.specialties.like(f'%{specialty}%'))
        if is_online:
            query = query.filter_by(is_online=is_online.lower() == 'true')
        
        # Handle sorting
        if sort.startswith('-'):
            query = query.order_by(getattr(MedicalEvent, sort[1:]).desc())
        else:
            query = query.order_by(getattr(MedicalEvent, sort).asc())
        
        events = query.all()
        return jsonify([e.to_dict() for e in events]), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Get single event
@medical_events_bp.route("/<int:id>", methods=["GET"])
def get_event(id):
    try:
        event = MedicalEvent.query.get(id)
        if not event:
            return jsonify(error="Event not found"), 404
        return jsonify(event.to_dict()), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

# Create event
@medical_events_bp.route("", methods=["POST"])
@jwt_required()
def create_event():
    try:
        data = request.json
        
        # Parse date strings to datetime if needed
        from datetime import datetime
        
        event = MedicalEvent(
            title=data.get('title'),
            description=data.get('description'),
            event_type=data.get('event_type'),
            specialties=json.dumps(data.get('specialties', [])),
            date=datetime.fromisoformat(data.get('date').replace('Z', '+00:00')) if data.get('date') else None,
            time=data.get('time'),
            end_date=datetime.fromisoformat(data.get('end_date').replace('Z', '+00:00')) if data.get('end_date') else None,
            location_city=data.get('location_city'),
            location_country=data.get('location_country'),
            venue=data.get('venue'),
            is_online=data.get('is_online', False),
            online_link=data.get('online_link'),
            registration_link=data.get('registration_link'),
            is_free=data.get('is_free', True),
            price=data.get('price'),
            organizer=data.get('organizer'),
            image_url=data.get('image_url'),
            attendees=json.dumps(data.get('attendees', [])),
            interested=json.dumps(data.get('interested', []))
        )
        
        db.session.add(event)
        db.session.commit()
        
        return jsonify(event.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Update event
@medical_events_bp.route("/<int:id>", methods=["PUT"])
@jwt_required()
def update_event(id):
    try:
        event = MedicalEvent.query.get(id)
        if not event:
            return jsonify(error="Event not found"), 404
        
        data = request.json
        from datetime import datetime
        
        if 'title' in data:
            event.title = data['title']
        if 'description' in data:
            event.description = data['description']
        if 'event_type' in data:
            event.event_type = data['event_type']
        if 'specialties' in data:
            event.specialties = json.dumps(data['specialties'])
        if 'date' in data and data['date']:
            event.date = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
        if 'time' in data:
            event.time = data['time']
        if 'end_date' in data and data['end_date']:
            event.end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
        if 'location_city' in data:
            event.location_city = data['location_city']
        if 'location_country' in data:
            event.location_country = data['location_country']
        if 'venue' in data:
            event.venue = data['venue']
        if 'is_online' in data:
            event.is_online = data['is_online']
        if 'online_link' in data:
            event.online_link = data['online_link']
        if 'registration_link' in data:
            event.registration_link = data['registration_link']
        if 'is_free' in data:
            event.is_free = data['is_free']
        if 'price' in data:
            event.price = data['price']
        if 'organizer' in data:
            event.organizer = data['organizer']
        if 'image_url' in data:
            event.image_url = data['image_url']
        if 'attendees' in data:
            event.attendees = json.dumps(data['attendees'])
        if 'interested' in data:
            event.interested = json.dumps(data['interested'])
        
        db.session.commit()
        return jsonify(event.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# Delete event
@medical_events_bp.route("/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_event(id):
    try:
        event = MedicalEvent.query.get(id)
        if not event:
            return jsonify(error="Event not found"), 404
        
        db.session.delete(event)
        db.session.commit()
        
        return jsonify(msg="Event deleted"), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500
