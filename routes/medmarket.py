from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import os, uuid
import requests as http_requests
from werkzeug.utils import secure_filename
from extensions import db
from models import MedMarketListing, User

medmarket_bp = Blueprint("medmarket", __name__)


# ─── Supabase helper ──────────────────────────────────────────────────────────

def upload_to_supabase(file_bytes, filename, content_type):
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()
    upload_url = f"{supabase_url}/storage/v1/object/uploads/{filename}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    res = http_requests.post(upload_url, data=file_bytes, headers=headers)
    if res.status_code not in (200, 201):
        raise Exception(f"Supabase upload failed: {res.text}")
    return f"{supabase_url}/storage/v1/object/public/uploads/{filename}"


# ─── LISTINGS ─────────────────────────────────────────────────────────────────

@medmarket_bp.route("/listings", methods=["GET"])
@jwt_required()
def list_listings():
    """
    Return active listings.
    Optional query params:
      - category: filter by listing category
      - search: keyword match on title / description
    """
    category = request.args.get("category")
    search = request.args.get("search", "").strip()

    query = MedMarketListing.query.filter_by(is_active=True)

    if category:
        query = query.filter_by(category=category)

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                MedMarketListing.title.ilike(like),
                MedMarketListing.description.ilike(like),
            )
        )

    listings = query.order_by(
        MedMarketListing.is_featured.desc(),   # featured slots bubble to top
        MedMarketListing.created_at.desc(),
    ).all()

    return jsonify([l.to_dict() for l in listings]), 200


@medmarket_bp.route("/listings/mine", methods=["GET"])
@jwt_required()
def my_listings():
    """Return all listings created by the current user."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    listings = MedMarketListing.query.filter_by(posted_by=user.email).order_by(
        MedMarketListing.created_at.desc()
    ).all()
    return jsonify([l.to_dict() for l in listings]), 200


@medmarket_bp.route("/listings/<int:listing_id>", methods=["GET"])
@jwt_required()
def get_listing(listing_id):
    listing = MedMarketListing.query.get_or_404(listing_id)

    # Increment view counter
    listing.view_count = (listing.view_count or 0) + 1
    db.session.commit()

    return jsonify(listing.to_dict()), 200


@medmarket_bp.route("/listings", methods=["POST"])
@jwt_required()
def create_listing():
    """
    Create a new marketplace listing.
    Accepts multipart/form-data so images can be uploaded alongside metadata.
    Up to 5 images are stored in Supabase.
    """
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.form

        # Upload images (up to 5)
        image_urls = []
        for f in request.files.getlist("images")[:5]:
            if f and f.filename:
                safe_name = secure_filename(f.filename)
                filename = f"market_{uuid.uuid4()}_{safe_name}"
                url = upload_to_supabase(
                    f.read(), filename, f.content_type or "image/jpeg"
                )
                image_urls.append(url)

        price_raw = data.get("price")
        price = float(price_raw) if price_raw else None

        listing = MedMarketListing(
            title=data.get("title"),
            category=data.get("category"),  # equipment / pharma / service / education / other
            description=data.get("description"),
            price=price,
            currency=data.get("currency", "INR"),
            price_type=data.get("price_type", "fixed"),  # fixed / negotiable / contact / free
            condition=data.get("condition"),              # new / like-new / good / fair (equipment only)
            location=data.get("location"),
            contact_email=data.get("contact_email", user.email),
            contact_phone=data.get("contact_phone"),
            website_url=data.get("website_url"),
            images=",".join(image_urls),
            posted_by=user.email,
            is_active=True,
            is_featured=False,   # featured status set by admin only
            view_count=0,
        )

        db.session.add(listing)
        db.session.commit()

        return jsonify({
            "message": "Listing created successfully",
            "listing": listing.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        print("LISTING CREATE ERROR:", repr(e))
        return jsonify({"error": str(e)}), 500


@medmarket_bp.route("/listings/<int:listing_id>", methods=["PUT"])
@jwt_required()
def update_listing(listing_id):
    """Update a listing (owner only)."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        listing = MedMarketListing.query.get_or_404(listing_id)

        if listing.posted_by != user.email:
            return jsonify({"error": "Not authorised"}), 403

        data = request.get_json()
        for field in [
            "title", "category", "description", "price", "currency",
            "price_type", "condition", "location",
            "contact_email", "contact_phone", "website_url", "is_active",
        ]:
            if field in data:
                setattr(listing, field, data[field])

        db.session.commit()
        return jsonify({"message": "Listing updated", "listing": listing.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@medmarket_bp.route("/listings/<int:listing_id>", methods=["DELETE"])
@jwt_required()
def delete_listing(listing_id):
    """Soft-delete a listing (owner only)."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        listing = MedMarketListing.query.get_or_404(listing_id)

        if listing.posted_by != user.email:
            return jsonify({"error": "Not authorised"}), 403

        listing.is_active = False
        db.session.commit()
        return jsonify({"message": "Listing removed"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ─── ENQUIRIES (contact the seller) ──────────────────────────────────────────

@medmarket_bp.route("/listings/<int:listing_id>/enquire", methods=["POST"])
@jwt_required()
def enquire(listing_id):
    """
    Simple enquiry endpoint — records the message so the seller is notified.
    In production, wire this up to an email notification.
    """
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        listing = MedMarketListing.query.get_or_404(listing_id)

        data = request.get_json()
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Message cannot be empty"}), 400

        # Increment enquiry counter on the listing
        listing.enquiry_count = (listing.enquiry_count or 0) + 1
        db.session.commit()

        return jsonify({
            "message": "Enquiry recorded. The seller will contact you at your registered email.",
            "seller_email": listing.contact_email,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ─── CATEGORIES helper ────────────────────────────────────────────────────────

@medmarket_bp.route("/categories", methods=["GET"])
@jwt_required()
def categories():
    """Return the list of supported listing categories."""
    return jsonify([
        {"value": "equipment",  "label": "Medical Equipment"},
        {"value": "pharma",     "label": "Pharmaceuticals & Supplies"},
        {"value": "service",    "label": "Clinical Services"},
        {"value": "education",  "label": "Education & Training"},
        {"value": "software",   "label": "Healthcare Software"},
        {"value": "other",      "label": "Other"},
    ]), 200