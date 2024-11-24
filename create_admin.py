"""Create a default admin user."""
from app import create_app
from models import db, Admin
from werkzeug.security import generate_password_hash

def create_default_admin():
    """Create a default admin user if it doesn't exist."""
    app = create_app()
    
    with app.app_context():
        # Delete existing admin if exists
        Admin.query.filter_by(email='admin@example.com').delete()
        db.session.commit()
        
        # Create new admin
        admin = Admin(
            username='admin',
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            is_active=True,
            is_super_admin=True,
            password_hash=generate_password_hash('admin123')
        )
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created successfully!")
        print("Email: admin@example.com")
        print("Password: admin123")

if __name__ == '__main__':
    create_default_admin()
