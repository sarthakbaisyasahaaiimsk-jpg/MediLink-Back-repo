from dotenv import load_dotenv
load_dotenv()

from flask import Flask, app, session
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
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True

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
        cors_allowed_origins=["http://localhost:5173", "https://medilink-front-repo.onrender.com"],
        manage_session=True
    )

    # CORS
    CORS(
    app,
    resources={r"/api/*": {
        "origins": [
            "http://localhost:5173",
            "https://medilink-front-repo.onrender.com"
        ]
    }},
    supports_credentials=True
   )

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
    from routes.references import references_bp
    from routes.zotero import zotero_bp
    from routes.admin import admin_bp
    from routes.drugs import drugs_bp
    from routes.forum_community import community_bp


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
    app.register_blueprint(references_bp, url_prefix="/api/references")
    app.register_blueprint(zotero_bp, url_prefix="/api/zotero")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(drugs_bp, url_prefix="/api/drugs")
    app.register_blueprint(community_bp, url_prefix='/api/community')


    # Keep-alive health check (also wakes Neon DB)
    @app.route("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as e:
            db_status = f"error: {e}"
        return {"status": "ok", "db": db_status}, 200

    # Create tables + auto-migrate
    with app.app_context():
        import models
        from models import SavedReference
        db.create_all()
        auto_add_missing_columns(app)

    # WebSocket handlers
    from websocket_handlers import init_websocket
    init_websocket(socketio)

    return app, socketio


from keep_alive import start_keep_alive

app, socketio = create_app()
start_keep_alive()

# if __name__ == "__main__":
#     socketio.run(app, debug=True, host="0.0.0.0", port=5000)