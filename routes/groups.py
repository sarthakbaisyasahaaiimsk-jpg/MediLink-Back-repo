
from flask import Blueprint, request, jsonify
from extensions import db
from models import Group, GroupMember

group_bp = Blueprint("groups", __name__)

@group_bp.route("/create", methods=["POST"])
def create():
    g = Group(name=request.json["name"])
    db.session.add(g)
    db.session.commit()
    return jsonify(group_id=g.id)

@group_bp.route("/join", methods=["POST"])
def join():
    gm = GroupMember(group_id=request.json["group_id"], user_id=request.json["user_id"])
    db.session.add(gm)
    db.session.commit()
    return jsonify(msg="joined")
