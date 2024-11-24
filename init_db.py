"""Initialize the database with default data."""
from app import create_app
from models import db
from database import init_db
import os

def main():
    """Initialize the database."""
    app = create_app()
    
    with app.app_context():
        # Ensure the data directory exists
        data_dir = app.config['DATA_DIR']
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, mode=0o777)
        
        # Initialize database
        db.create_all()
        
        # Initialize default data
        init_db()

if __name__ == '__main__':
    main()
