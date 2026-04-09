import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

# ✅ Fix Render's postgres:// -> postgresql://
db_url = os.getenv("DATABASE_URL", "sqlite:///app.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-too")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)

    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ✅ Neon serverless fix — prevents SSL drop errors after inactivity
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_timeout": 20,
        "pool_size": 5,
        "max_overflow": 2,
        "connect_args": {"sslmode": "require"} if db_url.startswith("postgresql") else {}
    }

    UPLOAD_FOLDER = "uploads"

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")