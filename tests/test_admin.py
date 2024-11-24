import pytest
from models import Admin, Employee, TaxRule, TaxCalculation
from flask import session
from models import db

@pytest.fixture
def admin_client(client, db):
    """Create and authenticate an admin user."""
    admin = Admin(
        email='admin@example.com',
        name='Admin User'
    )
    admin.set_password('Admin@123')
    db.session.add(admin)
    db.session.commit()
    
    client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'Admin@123'
    })
    return client

def test_admin_dashboard(client, auth_client, db):
    """Test admin dashboard access and functionality."""
    # Login as admin
    client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'admin_password'
    })
    
    response = client.get('/admin/dashboard')
    assert response.status_code == 200
    assert b'Admin Dashboard' in response.data
    assert b'Tax Rules' in response.data
    assert b'User Management' in response.data

def test_manage_tax_rules(client, db):
    """Test tax rule management."""
    # Login as admin
    client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'admin_password'
    })
    
    # Create new tax rule
    response = client.post('/admin/tax_rules', json={
        'min_income': 1000001,
        'max_income': 1500000,
        'tax_rate': 30,
        'description': 'New tax bracket',
        'is_active': True
    })
    assert response.status_code == 200
    
    # Verify rule was created
    rule = TaxRule.query.filter_by(min_income=1000001).first()
    assert rule is not None
    assert rule.tax_rate == 30
    
    # Update tax rule
    response = client.put(f'/admin/tax_rules/{rule.id}', json={
        'tax_rate': 25,
        'description': 'Updated tax bracket'
    })
    assert response.status_code == 200
    
    # Verify update
    rule = TaxRule.query.get(rule.id)
    assert rule.tax_rate == 25
    assert rule.description == 'Updated tax bracket'

def test_user_management(client, db):
    """Test user management functionality."""
    # Login as admin
    client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'admin_password'
    })
    
    # List users
    response = client.get('/admin/users')
    assert response.status_code == 200
    assert b'test@example.com' in response.data
    
    # Create new user
    response = client.post('/admin/users', json={
        'email': 'newuser@example.com',
        'name': 'New User',
        'password': 'password123'
    })
    assert response.status_code == 200
    
    # Verify user was created
    user = Employee.query.filter_by(email='newuser@example.com').first()
    assert user is not None
    
    # Deactivate user
    response = client.put(f'/admin/users/{user.id}', json={
        'is_active': False
    })
    assert response.status_code == 200
    
    # Verify user was deactivated
    user = Employee.query.get(user.id)
    assert not user.is_active

def test_admin_dashboard_access(client, admin_client):
    """Test admin dashboard access control."""
    # Test unauthenticated access
    response = client.get('/admin/dashboard')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']
    
    # Test authenticated admin access
    response = admin_client.get('/admin/dashboard')
    assert response.status_code == 200
    assert b'Admin Dashboard' in response.data

def test_tax_rule_management(admin_client, db):
    """Test tax rule CRUD operations."""
    # Test creating a new tax rule
    response = admin_client.post('/admin/tax-rules/add', data={
        'min_income': '0',
        'max_income': '250000',
        'tax_rate': '0',
        'description': 'No tax up to 2.5L'
    })
    assert response.status_code == 302
    
    rule = TaxRule.query.first()
    assert rule is not None
    assert rule.min_income == 0
    assert rule.max_income == 250000
    assert rule.tax_rate == 0
    
    # Test updating a tax rule
    response = admin_client.post(f'/admin/tax-rules/edit/{rule.id}', data={
        'min_income': '0',
        'max_income': '300000',  # Changed
        'tax_rate': '0',
        'description': 'No tax up to 3L'  # Changed
    })
    assert response.status_code == 302
    
    updated_rule = TaxRule.query.get(rule.id)
    assert updated_rule.max_income == 300000
    assert updated_rule.description == 'No tax up to 3L'
    
    # Test deleting a tax rule
    response = admin_client.post(f'/admin/tax-rules/delete/{rule.id}')
    assert response.status_code == 302
    
    deleted_rule = TaxRule.query.get(rule.id)
    assert deleted_rule is None

def test_tax_rule_validation(admin_client):
    """Test tax rule validation."""
    # Test overlapping tax brackets
    admin_client.post('/admin/tax-rules/add', data={
        'min_income': '0',
        'max_income': '250000',
        'tax_rate': '0',
        'description': 'First bracket'
    })
    
    response = admin_client.post('/admin/tax-rules/add', data={
        'min_income': '200000',  # Overlaps with previous bracket
        'max_income': '500000',
        'tax_rate': '5',
        'description': 'Second bracket'
    })
    assert response.status_code == 302
    assert b'Tax brackets cannot overlap' in response.data
    
    # Test invalid tax rate
    response = admin_client.post('/admin/tax-rules/add', data={
        'min_income': '500001',
        'max_income': '1000000',
        'tax_rate': '101',  # Invalid rate > 100
        'description': 'Invalid rate'
    })
    assert response.status_code == 302
    assert b'Tax rate must be between 0 and 100' in response.data

def test_employee_management(admin_client, db):
    """Test employee management functionality."""
    # Create test employees
    employees = [
        {'email': 'emp1@example.com', 'first_name': 'Emp1', 'last_name': 'Test', 'phone': '1234567890'},
        {'email': 'emp2@example.com', 'first_name': 'Emp2', 'last_name': 'Test', 'phone': '0987654321'}
    ]
    
    for emp_data in employees:
        employee = Employee(**emp_data)
        employee.set_password('Test@123')
        db.session.add(employee)
    db.session.commit()
    
    # Test employee list view
    response = admin_client.get('/admin/employees')
    assert response.status_code == 200
    assert b'emp1@example.com' in response.data
    assert b'emp2@example.com' in response.data
    
    # Test employee detail view
    employee = Employee.query.filter_by(email='emp1@example.com').first()
    response = admin_client.get(f'/admin/employees/{employee.id}')
    assert response.status_code == 200
    assert b'Emp1' in response.data
    assert b'1234567890' in response.data
    
    # Test employee deletion
    response = admin_client.post(f'/admin/employees/delete/{employee.id}')
    assert response.status_code == 302
    
    deleted_employee = Employee.query.get(employee.id)
    assert deleted_employee is None

def test_admin_reports(admin_client, db):
    """Test admin reporting functionality."""
    # Test tax calculation report
    response = admin_client.get('/admin/reports/tax-calculations')
    assert response.status_code == 200
    assert b'Tax Calculation Report' in response.data
    
    # Test employee statistics
    response = admin_client.get('/admin/reports/employee-stats')
    assert response.status_code == 200
    assert b'Employee Statistics' in response.data
    
    # Test data export
    response = admin_client.get('/admin/reports/export')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/csv'
    assert b'employee_id,calculation_date,gross_income,tax_amount' in response.data

def test_admin_reports(client, auth_client, db):
    """Test admin reporting functionality."""
    # Create some test data
    auth_client.login()
    for income in [300000, 500000, 750000]:
        client.post('/calculate_tax', json={
            'annual_income': income,
            'deductions': {'section_80c': 50000}
        })
    
    # Login as admin
    client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'admin_password'
    })
    
    # Test aggregate reports
    response = client.get('/admin/reports/aggregate')
    assert response.status_code == 200
    data = response.get_json()
    assert 'total_users' in data
    assert 'total_calculations' in data
    assert data['total_calculations'] == 3
    
    # Test detailed reports
    response = client.get('/admin/reports/detailed')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/pdf'

def test_audit_logging(client, db):
    """Test audit logging for admin actions."""
    # Login as admin
    client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'admin_password'
    })
    
    # Perform some actions
    client.post('/admin/tax_rules', json={
        'min_income': 2000001,
        'max_income': 2500000,
        'tax_rate': 35,
        'description': 'New tax bracket'
    })
    
    # Check audit logs
    response = client.get('/admin/audit_logs')
    assert response.status_code == 200
    assert b'Created tax rule' in response.data
    
def test_admin_security(client, auth_client):
    """Test admin security restrictions."""
    # Try accessing admin page without login
    response = client.get('/admin/dashboard')
    assert response.status_code == 302  # Redirect to login
    
    # Try accessing as regular user
    auth_client.login()
    response = client.get('/admin/dashboard')
    assert response.status_code == 403  # Forbidden
    
    # Try creating tax rule as regular user
    response = client.post('/admin/tax_rules', json={
        'min_income': 100000,
        'tax_rate': 10
    })
    assert response.status_code == 403
