"""Database initialization and management module."""
from models import db, TaxRule, Admin
import os
import logging
import stat

logger = logging.getLogger(__name__)

def ensure_directory_exists(directory):
    """Ensure directory exists and has proper permissions."""
    try:
        if not os.path.exists(directory):
            os.makedirs(directory, mode=0o777)
            logger.info(f"Created directory: {directory}")
        os.chmod(directory, 0o777)
        logger.info(f"Set permissions for directory: {directory}")
        return True
    except Exception as e:
        logger.error(f"Error creating/setting permissions for directory {directory}: {str(e)}")
        return False

def init_db():
    """Initialize the database and create default data."""
    try:
        # Get the database directory from config
        from flask import current_app
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        
        # Ensure database directory exists with proper permissions
        if not ensure_directory_exists(db_dir):
            raise Exception("Failed to create/set permissions for database directory")
            
        # Create database file if it doesn't exist
        if not os.path.exists(db_path):
            with open(db_path, 'w') as f:
                pass
            os.chmod(db_path, 0o666)
            logger.info(f"Created database file: {db_path}")
        
        # Create all database tables
        logger.info("Creating database tables...")
        db.create_all()

        # Initialize tax rules if none exist
        init_tax_rules()
        
        # Initialize default admin if none exists
        init_admin()

        return True

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise

def init_tax_rules():
    """Initialize default tax rules if none exist."""
    try:
        logger.info("Initializing tax rules...")
        if TaxRule.query.count() == 0:
            default_rules = [
                TaxRule(
                    min_income=0,
                    max_income=250000,
                    tax_rate=0,
                    description="No tax up to ₹2.5L"
                ),
                TaxRule(
                    min_income=250001,
                    max_income=500000,
                    tax_rate=5,
                    description="5% tax from ₹2.5L to ₹5L"
                ),
                TaxRule(
                    min_income=500001,
                    max_income=1000000,
                    tax_rate=20,
                    description="20% tax from ₹5L to ₹10L"
                ),
                TaxRule(
                    min_income=1000001,
                    max_income=None,
                    tax_rate=30,
                    description="30% tax above ₹10L"
                )
            ]
            
            for rule in default_rules:
                db.session.add(rule)
            
            db.session.commit()
            logger.info("Successfully initialized tax rules")
    except Exception as e:
        logger.error(f"Error initializing tax rules: {str(e)}")
        db.session.rollback()
        raise

def init_admin():
    """Initialize default admin user if none exists."""
    try:
        logger.info("Checking for default admin...")
        if Admin.query.count() == 0:
            default_admin = Admin(
                username='admin',
                email='admin@example.com',
                name='System Administrator',
                is_super_admin=True
            )
            default_admin.set_password('admin123')
            db.session.add(default_admin)
            db.session.commit()
            logger.info("Successfully created default admin user")
    except Exception as e:
        logger.error(f"Error creating default admin: {str(e)}")
        db.session.rollback()
        raise
