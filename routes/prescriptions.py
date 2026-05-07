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
    for field in ['disease', 'medications', 'contraindications', 'patient_groups']:
        if field not in data:
            return jsonify({'error': f'Missing field: {field}'}), 400

    existing = Prescription.query.filter(
        Prescription.disease.ilike(data['disease'])
    ).first()

    rx = existing or Prescription()
    rx.disease = data['disease']
    rx.icd_code = data.get('icd_code', '')
    rx.source = data.get('source', '')
    rx.last_updated = data.get('last_updated', '')
    rx.medications = data['medications']
    rx.contraindications = data['contraindications']
    rx.patient_groups = data['patient_groups']

    if not existing:
        db.session.add(rx)

    db.session.commit()
    return jsonify({'disease': rx.disease}), 200


@prescriptions_bp.route('/prescriptions/list', methods=['GET'])
@jwt_required()
def list_prescriptions():
    rxs = Prescription.query.order_by(Prescription.disease).all()
    return jsonify([{
        'id': r.id,
        'disease': r.disease,
        'icd_code': r.icd_code,
        'source': r.source,
        'last_updated': r.last_updated
    } for r in rxs]), 200


@prescriptions_bp.route('/prescriptions/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_prescription(id):
    rx = Prescription.query.get_or_404(id)
    db.session.delete(rx)
    db.session.commit()
    return jsonify({'deleted': id}), 200