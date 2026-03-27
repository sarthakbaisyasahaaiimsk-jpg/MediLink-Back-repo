
from flask import Blueprint, request, jsonify
from extensions import db
from models import Workshop

workshop_bp = Blueprint("workshops", __name__)

@workshop_bp.route("/", methods=["POST"])
def add():
    w = Workshop(
        title=request.json["title"],
        link=request.json["link"],
        description=request.json.get("description", "")
    )
    db.session.add(w)
    db.session.commit()
    return jsonify(msg="workshop added")
