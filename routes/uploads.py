from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import os
import uuid
from werkzeug.utils import secure_filename

upload_bp = Blueprint("uploads", __name__)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@upload_bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_file():
    try:
        # Create uploads directory if it doesn't exist
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify(error="No file provided"), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify(error="No file selected"), 400
        
        if not allowed_file(file.filename):
            return jsonify(error="File type not allowed"), 400
        
        # Generate unique filename
        safe_name = secure_filename(file.filename)
        filename = f"{uuid.uuid4()}_{safe_name}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save file
        file.save(filepath)
        
        # Return file info
        return jsonify({
            "message": "File uploaded successfully",
            "file_url": f"/uploads/{filename}",
            "filename": filename,
            "filepath": filepath
        }), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
