import pytest
from decimal import Decimal
from models import TaxCalculation, TaxRule

def test_tax_calculation(client, auth_client, db):
    """Test tax calculation functionality."""
    # Login first
    auth_client.login()
    
    # Test calculation with no tax bracket
    response = client.post('/calculate_tax', json={
        'annual_income': 200000,
        'deductions': {
            'section_80c': 50000,
            'health_insurance': 25000
        }
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['tax_amount'] == 0
    
    # Test calculation with 5% tax bracket
    response = client.post('/calculate_tax', json={
        'annual_income': 400000,
        'deductions': {
            'section_80c': 50000,
            'health_insurance': 25000
        }
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['tax_amount'] > 0
    
    # Verify calculation is saved
    calc = TaxCalculation.query.filter_by(user_id=1).first()
    assert calc is not None
    assert calc.income_data['annual_income'] == 400000

def test_tax_saving_tips(client, auth_client):
    """Test tax saving recommendations."""
    auth_client.login()
    
    response = client.get('/tax_saving_tips')
    assert response.status_code == 200
    assert b'Section 80C' in response.data
    assert b'Health Insurance' in response.data

def test_tax_history(client, auth_client, db):
    """Test tax calculation history."""
    auth_client.login()
    
    # Create some test calculations
    for income in [300000, 500000]:
        client.post('/calculate_tax', json={
            'annual_income': income,
            'deductions': {
                'section_80c': 50000
            }
        })
    
    # Check history
    response = client.get('/tax_history')
    assert response.status_code == 200
    assert b'300,000' in response.data
    assert b'500,000' in response.data

def test_tax_report_generation(client, auth_client, db):
    """Test tax report generation."""
    auth_client.login()
    
    # Create a calculation first
    client.post('/calculate_tax', json={
        'annual_income': 600000,
        'deductions': {
            'section_80c': 150000
        }
    })
    
    calc = TaxCalculation.query.first()
    
    # Generate report
    response = client.get(f'/generate_report/{calc.id}')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/pdf'

def test_invalid_inputs(client, auth_client):
    """Test input validation."""
    auth_client.login()
    
    # Test negative income
    response = client.post('/calculate_tax', json={
        'annual_income': -50000,
        'deductions': {}
    })
    assert response.status_code == 400
    
    # Test excessive deductions
    response = client.post('/calculate_tax', json={
        'annual_income': 500000,
        'deductions': {
            'section_80c': 500000  # More than allowed limit
        }
    })
    assert response.status_code == 400

def test_tax_rule_changes(client, auth_client, db):
    """Test tax calculation with different tax rules."""
    # Login as admin to modify tax rules
    client.post('/auth/login', data={
        'email': 'admin@example.com',
        'password': 'admin_password'
    })
    
    # Add a new tax rule
    client.post('/admin/tax_rules', json={
        'min_income': 500001,
        'max_income': 1000000,
        'tax_rate': 20,
        'description': 'New tax bracket'
    })
    
    # Login as regular user
    auth_client.login()
    
    # Test calculation with new tax bracket
    response = client.post('/calculate_tax', json={
        'annual_income': 750000,
        'deductions': {}
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['tax_amount'] > 0  # Should use new 20% bracket

import pytest
from flask import session
from models import db, Employee, TaxRule, TaxCalculation
from decimal import Decimal

@pytest.fixture
def tax_rules(db):
    """Create test tax rules."""
    rules = [
        TaxRule(min_income=0, max_income=250000, tax_rate=0, description="No tax up to 2.5L"),
        TaxRule(min_income=250001, max_income=500000, tax_rate=5, description="5% from 2.5L to 5L"),
        TaxRule(min_income=500001, max_income=1000000, tax_rate=20, description="20% from 5L to 10L"),
        TaxRule(min_income=1000001, max_income=None, tax_rate=30, description="30% above 10L")
    ]
    for rule in rules:
        db.session.add(rule)
    db.session.commit()
    return rules

@pytest.fixture
def auth_employee(client, db):
    """Create and authenticate a test employee."""
    employee = Employee(
        email='test@example.com',
        first_name='Test',
        last_name='User',
        phone='1234567890'
    )
    employee.set_password('Test@123')
    db.session.add(employee)
    db.session.commit()
    
    client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'Test@123'
    })
    return employee

def test_tax_calculation_no_tax(client, auth_employee, tax_rules):
    """Test tax calculation for income below tax threshold."""
    response = client.post('/employee/calculate-tax', data={
        'gross_income': '200000',
        'deductions': '50000'
    })
    assert response.status_code == 200
    
    calculation = TaxCalculation.query.first()
    assert calculation is not None
    assert calculation.gross_income == 200000
    assert calculation.deductions == 50000
    assert calculation.taxable_income == 150000
    assert calculation.tax_amount == 0

def test_tax_calculation_first_slab(client, auth_employee, tax_rules):
    """Test tax calculation for first tax slab."""
    response = client.post('/employee/calculate-tax', data={
        'gross_income': '400000',
        'deductions': '50000'
    })
    assert response.status_code == 200
    
    calculation = TaxCalculation.query.first()
    assert calculation is not None
    assert calculation.gross_income == 400000
    assert calculation.taxable_income == 350000
    # Tax should be 5% of (350000 - 250000) = 5% of 100000 = 5000
    assert calculation.tax_amount == 5000

def test_tax_calculation_multiple_slabs(client, auth_employee, tax_rules):
    """Test tax calculation across multiple slabs."""
    response = client.post('/employee/calculate-tax', data={
        'gross_income': '1500000',
        'deductions': '100000'
    })
    assert response.status_code == 200
    
    calculation = TaxCalculation.query.first()
    assert calculation is not None
    assert calculation.gross_income == 1500000
    assert calculation.taxable_income == 1400000
    
    # Tax calculation:
    # 0-2.5L: 0
    # 2.5L-5L: 12500 (5% of 2.5L)
    # 5L-10L: 100000 (20% of 5L)
    # 10L-14L: 120000 (30% of 4L)
    # Total: 232500
    assert calculation.tax_amount == 232500

def test_tax_calculation_validation(client, auth_employee, tax_rules):
    """Test input validation for tax calculation."""
    # Test negative income
    response = client.post('/employee/calculate-tax', data={
        'gross_income': '-100000',
        'deductions': '50000'
    })
    assert response.status_code == 302
    assert b'Invalid income or deductions values' in response.data
    
    # Test deductions greater than income
    response = client.post('/employee/calculate-tax', data={
        'gross_income': '100000',
        'deductions': '150000'
    })
    assert response.status_code == 302
    assert b'Invalid income or deductions values' in response.data
    
    # Test non-numeric values
    response = client.post('/employee/calculate-tax', data={
        'gross_income': 'abc',
        'deductions': '50000'
    })
    assert response.status_code == 302
    assert b'Please enter valid numeric values' in response.data

def test_tax_calculation_history(client, auth_employee, tax_rules):
    """Test tax calculation history."""
    # Make multiple calculations
    calculations = [
        {'gross_income': '300000', 'deductions': '50000'},
        {'gross_income': '600000', 'deductions': '100000'},
        {'gross_income': '1200000', 'deductions': '150000'}
    ]
    
    for calc in calculations:
        client.post('/employee/calculate-tax', data=calc)
    
    # Check history
    response = client.get('/employee/calculations')
    assert response.status_code == 200
    
    # Verify all calculations are shown
    history = TaxCalculation.query.all()
    assert len(history) == 3
    
    # Check calculations are ordered by date (newest first)
    assert history[0].gross_income == 1200000
    assert history[1].gross_income == 600000
    assert history[2].gross_income == 300000

def test_tax_calculation_export(client, auth_employee, tax_rules):
    """Test tax calculation export functionality."""
    # Make some calculations
    calculations = [
        {'gross_income': '300000', 'deductions': '50000'},
        {'gross_income': '600000', 'deductions': '100000'}
    ]
    
    for calc in calculations:
        client.post('/employee/calculate-tax', data=calc)
    
    # Test CSV export
    response = client.get('/employee/export-calculations')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/csv'
    assert b'gross_income,deductions,taxable_income,tax_amount' in response.data
