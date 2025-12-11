from app import app, db, User

def create_admin():
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        if user is None:
            user = User(username='admin')
            user.set_password('admin')
            user.is_admin = True
            db.session.add(user)
            db.session.commit()
            print('Admin user created: admin')
        else:
            user.set_password('admin')
            user.is_admin = True
            db.session.add(user)
            db.session.commit()
            print('Admin user updated: admin')

if __name__ == '__main__':
    create_admin()
