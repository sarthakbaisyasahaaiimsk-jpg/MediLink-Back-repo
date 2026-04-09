from dotenv import load_dotenv
load_dotenv()

from flask import Flask, session, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from config import Config
from extensions import db, jwt
from authlib.integrations.flask_client import OAuth
from sqlalchemy import inspect, text
import os


def auto_add_missing_columns(app):
    from models import (
        User, Message, Conversation, Group, GroupMember,
        Case, Comment, DoctorProfile, MedicalEvent, Workshop
    )

    inspector = inspect(db.engine)

    model_list = [
        User,
        Message,
        Conversation,
        Group,
        GroupMember,
        Case,
        Comment,
        DoctorProfile,
        MedicalEvent,
        Workshop
    ]

    for model in model_list:
        table_name = getattr(model, '__tablename__', None) or model.__table__.name

        if table_name not in inspector.get_table_names():
            continue

        existing_columns = {col['name'] for col in inspector.get_columns(table_name)}

        for col in model.__table__.columns:
            if col.name in existing_columns:
                continue
            if col.primary_key:
                continue

            sql_type = col.type.compile(db.engine.dialect)
            query = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {sql_type}'

            # Fix for NOT NULL
            if not col.nullable:
                query += ' NOT NULL'

            if col.server_default is not None:
                default_val = str(col.server_default.arg)
                query += f' DEFAULT {default_val}'

            try:
                with app.app_context():
                    db.session.execute(text(query))
                    db.session.commit()
                    print(f"Added column {col.name} to {table_name}")
            except Exception as e:
                db.session.rollback()
                print(f"Could not add column {col.name} to {table_name}: {e}")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = False

    db.init_app(app)
    jwt.init_app(app)

    # OAuth
    oauth = OAuth(app)
    app.oauth = oauth
    oauth.register(
        'google',
        client_id=Config.GOOGLE_CLIENT_ID,
        client_secret=Config.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={'scope': 'openid email profile'},
    )

    # WebSocket
    socketio = SocketIO(
        app,
        cors_allowed_origins=["http://localhost:5173"],
        manage_session=True
    )

    # CORS
    CORS(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": ["http://localhost:5173"]}}
    )

    # ✅ FIX 1: Use absolute path for uploads folder
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # ✅ FIX 2: Serve uploaded files so they're accessible in the browser
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(UPLOAD_FOLDER, filename)

    # Blueprints
    from routes.auth import auth_bp
    from routes.case_comments import case_comments_bp
    from routes.cases import case_bp
    from routes.conversations import conversations_bp
    from routes.doctor_profiles import doctor_profile_bp
    from routes.groups import group_bp
    from routes.medical_events import medical_events_bp
    from routes.messages_api import messages_api_bp
    from routes.messages import message_bp
    from routes.patient_cases import patient_cases_bp
    from routes.uploads import upload_bp
    from routes.workshops import workshop_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(case_comments_bp, url_prefix="/api/case-comments")
    app.register_blueprint(case_bp, url_prefix="/api")
    app.register_blueprint(conversations_bp, url_prefix="/api/conversations")
    app.register_blueprint(doctor_profile_bp, url_prefix="/api/doctor-profiles")
    app.register_blueprint(group_bp, url_prefix="/api/groups")
    app.register_blueprint(medical_events_bp, url_prefix="/api/medical-events")
    app.register_blueprint(messages_api_bp, url_prefix="/api/messages")
    app.register_blueprint(message_bp, url_prefix="/api/messages-legacy")
    app.register_blueprint(patient_cases_bp, url_prefix="/api/patient-cases")
    app.register_blueprint(upload_bp, url_prefix="/api")
    app.register_blueprint(workshop_bp, url_prefix="/api/workshops")

    # Create tables + auto-migrate
    with app.app_context():
        import models
        db.create_all()
        auto_add_missing_columns(app)

    # WebSocket handlers
    from websocket_handlers import init_websocket
    init_websocket(socketio)

    return app, socketio


app, socketio = create_app()

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)