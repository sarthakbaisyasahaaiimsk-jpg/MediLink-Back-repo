from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import os
import uuid
from werkzeug.utils import secure_filename
from supabase import create_client

upload_bp = Blueprint("uploads", __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'xlsx', 'xls'}

def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@upload_bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_file():
    try:
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

        # Read file bytes
        file_bytes = file.read()
        content_type = file.content_type or 'application/octet-stream'

        # Upload to Supabase Storage
        supabase = get_supabase()
        res = supabase.storage.from_("uploads").upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": content_type}
        )

        # Get public URL
        public_url = supabase.storage.from_("uploads").get_public_url(filename)

        return jsonify({
            "message": "File uploaded successfully",
            "file_url": public_url,
            "filename": filename,
        }), 200

    except Exception as e:
        print("UPLOAD ERROR:", repr(e))
        return jsonify(error=str(e)), 500