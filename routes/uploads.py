from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
import os
import uuid
import requests
from werkzeug.utils import secure_filename

upload_bp = Blueprint("uploads", __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'xlsx', 'xls', 'mp3', 'wav', 'ogg', 'webm'}

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

        safe_name = secure_filename(file.filename)
        filename = f"{uuid.uuid4()}_{safe_name}"

        file_bytes = file.read()
        content_type = file.content_type or 'application/octet-stream'

        supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

        # ✅ Upload directly via Supabase REST API — no Python client needed
        upload_url = f"{supabase_url}/storage/v1/object/uploads/{filename}"
        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": content_type,
            "x-upsert": "true"
        }

        res = requests.post(upload_url, data=file_bytes, headers=headers)

        if res.status_code not in (200, 201):
            print("SUPABASE UPLOAD FAILED:", res.status_code, res.text)
            return jsonify(error=f"Storage upload failed: {res.text}"), 500

        # ✅ Build public URL
        public_url = f"{supabase_url}/storage/v1/object/public/uploads/{filename}"

        return jsonify({
            "message": "File uploaded successfully",
            "file_url": public_url,
            "filename": filename,
        }), 200

    except Exception as e:
        print("UPLOAD ERROR:", repr(e))
        return jsonify(error=str(e)), 500