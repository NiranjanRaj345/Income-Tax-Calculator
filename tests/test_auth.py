import pytest
from flask import session, g
from models import Employee, Admin

def test_register(client, db):
    """Test registration."""
    # Test successful registration
    response = client.post('/auth/register', data={
        'email': 'new@example.com',
        'name': 'New User',
        'password': 'newpassword123',
        'confirm_password': 'newpassword123'
    })
    assert response.status_code == 302  # Redirect after successful registration
    
    # Check if user was created
    user = Employee.query.filter_by(email='new@example.com').first()
    assert user is not None
    assert user.name == 'New User'
    
    # Test duplicate email
    response = client.post('/auth/register', data={
        'email': 'new@example.com',
        'name': 'Another User',
        'password': 'password123',
        'confirm_password': 'password123'
    })
    assert b'Email already registered' in response.data

def test_login(client, auth_client):
    """Test login."""
    # Test successful login
    response = auth_client.login()
    assert response.status_code == 302  # Redirect after successful login
    
    with client:
        client.get('/')  # Get a page to trigger session handling
        assert session['user_id'] is not None
        assert session['user_type'] == 'employee'

def test_logout(client, auth_client):
    """Test logout."""
    auth_client.login()
    
    with client:
        auth_client.logout()
        assert 'user_id' not in session

def test_admin_login(client):
    """Test admin login."""
    response = client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'admin_password'
    })
    assert response.status_code == 302
    
    with client:
        client.get('/')
        assert session['user_type'] == 'admin'

def test_password_validation(client):
    """Test password validation rules."""
    # Test password too short
    response = client.post('/auth/register', data={
        'email': 'test@example.com',
        'name': 'Test User',
        'password': '12345',
        'confirm_password': '12345'
    })
    assert b'Password must be at least 6 characters long' in response.data
    
    # Test password mismatch
    response = client.post('/auth/register', data={
        'email': 'test@example.com',
        'name': 'Test User',
        'password': 'password123',
        'confirm_password': 'password456'
    })
    assert b'Passwords must match' in response.data

def test_login_required(client):
    """Test login_required decorator."""
    # Try accessing protected page
    response = client.get('/tax_calculator')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']

def test_admin_required(client, auth_client):
    """Test admin_required decorator."""
    # Login as regular user
    auth_client.login()
    
    # Try accessing admin page
    response = client.get('/admin/dashboard')
    assert response.status_code == 302  # Redirect to login
    
    # Login as admin
    client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'admin_password'
    })
    
    # Try accessing admin page again
    response = client.get('/admin/dashboard')
    assert response.status_code == 200  # Success

def test_password_reset_request(client, db):
    """Test password reset request functionality."""
    # Create a test user
    employee = Employee(
        email='test@example.com',
        first_name='Test',
        last_name='User',
        phone='1234567890'
    )
    employee.set_password('Test@123')
    db.session.add(employee)
    db.session.commit()
    
    # Test reset request for existing user
    response = client.post('/auth/reset-password', data={
        'email': 'test@example.com'
    })
    assert response.status_code == 302
    assert b'If an account exists with that email' in response.data
    
    # Test reset request for non-existent user
    response = client.post('/auth/reset-password', data={
        'email': 'nonexistent@example.com'
    })
    assert response.status_code == 302
    assert b'If an account exists with that email' in response.data

def test_password_reset_token(client, db):
    """Test password reset token functionality."""
    with client:
        # Request password reset
        client.post('/auth/reset-password', data={
            'email': 'test@example.com'
        })
        
        # Check if token was stored in session
        assert 'reset_token' in session
        assert 'reset_email' in session
        assert 'reset_expiry' in session
        
        token = session['reset_token']
        
        # Test invalid token
        response = client.get('/auth/reset-password/invalid-token')
        assert response.status_code == 302
        assert b'Invalid or expired reset link' in response.data
        
        # Test valid token
        response = client.get(f'/auth/reset-password/{token}')
        assert response.status_code == 200
        
        # Test password reset with valid token
        response = client.post(f'/auth/reset-password/{token}', data={
            'password': 'NewTest@123',
            'confirm_password': 'NewTest@123'
        })
        assert response.status_code == 302
        
        # Verify new password works
        response = client.post('/auth/login', data={
            'email': 'test@example.com',
            'password': 'NewTest@123'
        })
        assert response.status_code == 302
        assert session['user_type'] == 'employee'

def test_password_complexity(client):
    """Test password complexity requirements."""
    test_cases = [
        ('12345', 'Password must be at least 6 characters long'),
        ('123456', None)  # Should pass
    ]
    
    for password, expected_error in test_cases:
        response = client.post('/auth/register', data={
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '1234567890',
            'password': password,
            'confirm_password': password
        })
        
        if expected_error:
            assert expected_error.encode() in response.data
        else:
            assert response.status_code == 302  # Successful registration redirects

def test_session_management(client, auth_client):
    """Test session management."""
    with client:
        # Test login sets correct session data
        response = auth_client.login()
        assert response.status_code == 302
        assert 'user_id' in session
        assert 'user_type' in session
        assert 'last_seen' in session
        
        # Test session data is cleared on logout
        auth_client.logout()
        assert 'user_id' not in session
        assert 'user_type' not in session
        assert 'last_seen' not in session

def test_csrf_protection(client):
    """Test CSRF protection."""
    # Try to submit form without CSRF token
    response = client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'Test@123'
    })
    assert response.status_code == 400  # Bad Request due to missing CSRF token
