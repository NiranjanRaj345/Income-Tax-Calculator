import os
import tempfile
import pytest
from app import create_app
from database import db as _db
from models import Employee, Admin, TaxRule

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Create a temporary file to isolate the database for each test
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'WTF_CSRF_ENABLED': False,
    })

    # Create the database and load test data
    with app.app_context():
        _db.create_all()
        _create_test_data()

    yield app

    # Clean up
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()

@pytest.fixture
def db(app):
    """Create and configure a new database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()

@pytest.fixture
def auth_client(client):
    """A test client with authentication helpers."""
    class AuthActions:
        def __init__(self, client):
            self._client = client

        def login(self, email='test@example.com', password='password'):
            return self._client.post(
                '/auth/login',
                data={'email': email, 'password': password}
            )

        def logout(self):
            return self._client.get('/auth/logout')

    return AuthActions(client)

def _create_test_data():
    """Create initial test data."""
    # Create test employee
    employee = Employee(
        email='test@example.com',
        name='Test User'
    )
    employee.set_password('password')
    _db.session.add(employee)

    # Create test admin
    admin = Admin(
        email='admin@example.com',
        username='admin',
        is_super_admin=True
    )
    admin.set_password('admin_password')
    _db.session.add(admin)

    # Create test tax rules
    tax_rules = [
        TaxRule(
            min_income=0,
            max_income=250000,
            tax_rate=0,
            description="No tax up to ₹2.5 lakhs",
            is_active=True
        ),
        TaxRule(
            min_income=250001,
            max_income=500000,
            tax_rate=5,
            description="5% tax between ₹2.5 lakhs to ₹5 lakhs",
            is_active=True
        )
    ]
    _db.session.bulk_save_objects(tax_rules)
    
    _db.session.commit()
