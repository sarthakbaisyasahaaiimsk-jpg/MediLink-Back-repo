# App.py
from flask import Flask, session
from flask_cors import CORS
from flask_socketio import SocketIO
from config import Config
from extensions import db, jwt
from authlib.integrations.flask_client import OAuth
from sqlalchemy import inspect, text
import os
import secrets

def auto_add_missing_columns(app):
    from models import User

    inspector = inspect(db.engine)
    model_list = [User]

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
                query += ' NULL'
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

    # ✅ Make SECRET_KEY constant (must not change between restarts)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    # ✅ Session cookie settings for OAuth redirect to localhost
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'   # Allows redirect back from Google
    app.config['SESSION_COOKIE_SECURE'] = False    # True if using HTTPS, False for localhost

    db.init_app(app)
    jwt.init_app(app)

    # Initialize OAuth
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
    socketio = SocketIO(app, cors_allowed_origins=["http://localhost:5173"], manage_session=True)

    # Enable CORS with credentials so session works
    CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": ["http://localhost:5173"]}})

    os.makedirs("uploads", exist_ok=True)

    # Import and register blueprints
    from routes.auth import auth_bp
    # ... other blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    # ... other blueprints registration

    # Create tables and auto-add columns
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