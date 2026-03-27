from app import create_app
from extensions import db
from models import User

app, socketio = create_app()
with app.app_context():
    db.create_all()
    User.query.filter_by(username='test_user_db').delete()
    db.session.commit()

    u = User(username='test_user_db', email='test@example.com', password='secret')
    db.session.add(u)
    db.session.commit()

    u2 = User.query.filter_by(username='test_user_db').first()
    print('inserted', u2.id, u2.email)

    db.session.delete(u2)
    db.session.commit()
    print('cleanup done')
