from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Prescription

prescriptions_bp = Blueprint('prescriptions', __name__)


@prescriptions_bp.route('/prescriptions/search', methods=['GET'])
@jwt_required()
def search_prescription():
    query = request.args.get('disease', '').strip()

    if not query:
        return jsonify({'error': 'Disease name is required'}), 400

    result = Prescription.query.filter(
        Prescription.disease.ilike(f'%{query}%')
    ).first()

    if not result:
        return jsonify({'error': 'No guideline found for this disease'}), 404

    return jsonify(result.to_dict()), 200


@prescriptions_bp.route('/prescriptions/upload', methods=['POST'])
@jwt_required()
def upload_prescription():
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No JSON payload received'}), 400

    # SUPPORT BOTH:
    # 1. Single object
    # 2. Array of objects

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return jsonify({
            'error': 'Payload must be a JSON object or array'
        }), 400

    uploaded = []

    try:
        for item in data:

            # Validate required fields
            required_fields = [
                'disease',
                'medications',
                'contraindications',
                'patient_groups'
            ]

            for field in required_fields:
                if field not in item:
                    return jsonify({
                        'error': f'Missing field: {field}',
                        'payload': item
                    }), 400

            # Validate disease
            if not isinstance(item['disease'], str) or not item['disease'].strip():
                return jsonify({
                    'error': 'Disease must be a non-empty string'
                }), 400

            # Validate arrays
            if not isinstance(item['medications'], list):
                return jsonify({
                    'error': 'medications must be an array',
                    'disease': item['disease']
                }), 400

            if not isinstance(item['contraindications'], list):
                return jsonify({
                    'error': 'contraindications must be an array',
                    'disease': item['disease']
                }), 400

            if not isinstance(item['patient_groups'], list):
                return jsonify({
                    'error': 'patient_groups must be an array',
                    'disease': item['disease']
                }), 400

            # Check existing disease
            existing = Prescription.query.filter(
                Prescription.disease.ilike(item['disease'])
            ).first()

            rx = existing or Prescription()

            rx.disease = item['disease'].strip()
            rx.icd_code = item.get('icd_code', '')
            rx.source = item.get('source', '')
            rx.last_updated = item.get('last_updated', '')
            rx.medications = item['medications']
            rx.contraindications = item['contraindications']
            rx.patient_groups = item['patient_groups']

            if not existing:
                db.session.add(rx)

            uploaded.append(rx.disease)

        db.session.commit()

        return jsonify({
            'message': 'Upload successful',
            'uploaded': uploaded,
            'count': len(uploaded)
        }), 200

    except Exception as e:
        db.session.rollback()

        return jsonify({
            'error': 'Upload failed',
            'details': str(e)
        }), 500


@prescriptions_bp.route('/prescriptions/list', methods=['GET'])
@jwt_required()
def list_prescriptions():
    rxs = Prescription.query.order_by(Prescription.disease).all()

    return jsonify([
        {
            'id': r.id,
            'disease': r.disease,
            'icd_code': r.icd_code,
            'source': r.source,
            'last_updated': r.last_updated
        }
        for r in rxs
    ]), 200


@prescriptions_bp.route('/prescriptions/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_prescription(id):
    rx = Prescription.query.get_or_404(id)

    db.session.delete(rx)
    db.session.commit()

    return jsonify({'deleted': id}), 200