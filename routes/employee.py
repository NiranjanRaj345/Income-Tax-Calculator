"""Employee routes module."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import db, Employee, TaxCalculation
from flask_wtf import FlaskForm
from wtforms import FloatField, RadioField
from wtforms.validators import DataRequired, NumberRange
import logging
from extensions import limiter
import csv
from io import StringIO
import pandas as pd
import sys
import json
import traceback
from datetime import datetime
from functools import wraps
import sqlite3

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG level for detailed logging

# Add a file handler if it doesn't exist
if not logger.handlers:
    fh = logging.FileHandler('tax_calculator.log')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

employee_bp = Blueprint('employee', __name__)

def employee_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not isinstance(current_user, Employee):
            flash('Access denied. Employee privileges required.', 'error')
            return redirect(url_for('auth.login'))
        if not current_user.is_active:
            flash('Your account is currently inactive. Please contact an administrator.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

class TaxCalculationForm(FlaskForm):
    """Form for tax calculation."""
    monthly_income = FloatField('Monthly Income', validators=[DataRequired(), NumberRange(min=0)])
    bonus = FloatField('Annual Bonus', validators=[NumberRange(min=0)], default=0)
    investment_80c = FloatField('80C Investment', validators=[NumberRange(min=0)], default=0)
    medical_insurance = FloatField('Medical Insurance Premium', validators=[NumberRange(min=0)], default=0)
    home_loan_interest = FloatField('Home Loan Interest', validators=[NumberRange(min=0)], default=0)
    education_loan_interest = FloatField('Education Loan Interest', validators=[NumberRange(min=0)], default=0)
    tax_regime = RadioField('Tax Regime', choices=[('old', 'Old Regime'), ('new', 'New Regime')], default='old')

class ProfileForm(FlaskForm):
    """Empty form class for CSRF protection"""
    pass

def clean_currency_input(value):
    """Clean currency input by removing non-numeric characters."""
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    # Remove currency symbols, commas and spaces
    cleaned = str(value).replace('₹', '').replace(',', '').replace(' ', '').strip()
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

@employee_bp.route('/dashboard')
@login_required
@employee_required
def dashboard():
    """Employee dashboard showing recent calculations and profile info."""
    try:
        # Get database path from config
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        logger.info(f"Dashboard accessing database at: {db_path}")
        
        recent_calculations = []
        stats = {
            'total_calculations': 0,
            'latest_tax_amount': 0,
            'current_regime': None
        }
        regime_distribution = {
            'labels': [],
            'data': []
        }
        
        # Use direct SQLite connection
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row  # This allows accessing columns by name
            cursor = conn.cursor()
            
            # Get recent calculations for the employee
            cursor.execute("""
                SELECT * FROM tax_calculation 
                WHERE employee_id = ? 
                ORDER BY calculation_date DESC 
                LIMIT 5
            """, (current_user.id,))
            
            rows = cursor.fetchall()
            for row in rows:
                calculation = {
                    'id': row['id'],
                    'gross_income': row['gross_income'],
                    'deductions': row['deductions'],
                    'taxable_income': row['taxable_income'],
                    'tax_amount': row['tax_amount'],
                    'tax_regime': row['tax_regime'],
                    'calculation_date': datetime.strptime(row['calculation_date'], '%Y-%m-%d %H:%M:%S'),
                    'calculation_details': json.loads(row['calculation_details']) if row['calculation_details'] else {}
                }
                recent_calculations.append(calculation)
                
                # Update latest tax amount from the most recent calculation
                if len(recent_calculations) == 1:
                    stats['latest_tax_amount'] = calculation['tax_amount']
                    stats['current_regime'] = calculation['tax_regime']
            
            # Get total calculations
            cursor.execute("""
                SELECT COUNT(*) as total FROM tax_calculation 
                WHERE employee_id = ?
            """, (current_user.id,))
            stats['total_calculations'] = cursor.fetchone()['total']
            
            # Get regime distribution
            cursor.execute("""
                SELECT tax_regime, COUNT(*) as count 
                FROM tax_calculation 
                WHERE employee_id = ? 
                GROUP BY tax_regime
            """, (current_user.id,))
            
            regime_rows = cursor.fetchall()
            if regime_rows:
                regime_distribution['labels'] = [row['tax_regime'].title() for row in regime_rows]
                regime_distribution['data'] = [row['count'] for row in regime_rows]
        
        logger.info(f"Retrieved {len(recent_calculations)} recent calculations")
        
        return render_template('employee/dashboard.html',
                             employee=current_user,
                             recent_calculations=recent_calculations,
                             stats=stats,
                             regime_distribution=regime_distribution)
    except Exception as e:
        logger.error(f"Error in employee dashboard: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while loading the dashboard.', 'error')
        return render_template('errors/500.html'), 500

@employee_bp.route('/profile')
@login_required
@employee_required
def profile():
    """View and edit employee profile."""
    try:
        form = ProfileForm()
        return render_template('employee/profile.html', employee=current_user, form=form)
    except Exception as e:
        logger.error(f"Error in employee profile: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while loading your profile.', 'error')
        return render_template('errors/500.html'), 500

@employee_bp.route('/profile/update', methods=['POST'])
@login_required
@employee_required
def update_profile():
    """Update employee profile information."""
    try:
        form = ProfileForm()
        if not form.validate_on_submit():
            flash('Invalid form submission.', 'error')
            return redirect(url_for('employee.profile'))
            
        data = request.form
        current_user.first_name = data.get('first_name', current_user.first_name)
        current_user.last_name = data.get('last_name', current_user.last_name)
        current_user.phone = data.get('phone', current_user.phone)
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('employee.profile'))
    except Exception as e:
        logger.error(f"Error updating profile: {str(e)}\n{traceback.format_exc()}")
        db.session.rollback()
        flash('An error occurred while updating your profile.', 'error')
        return redirect(url_for('employee.profile'))

@employee_bp.route('/calculate-tax', methods=['GET', 'POST'])
@login_required
@employee_required
def calculate_tax():
    """Calculate tax for the employee."""
    try:
        form = TaxCalculationForm()
        calculation_result = None
        
        if request.method == 'GET':
            return render_template('employee/calculate_tax.html', form=form)
        
        # Handle tax regime and set deduction fields to 0 for new regime
        tax_regime = request.form.get('tax_regime', 'old')
        if tax_regime == 'new':
            form.investment_80c.data = 0
            form.medical_insurance.data = 0
            form.home_loan_interest.data = 0
            form.education_loan_interest.data = 0
        
        # Clean form data before validation
        if request.method == 'POST':
            form.monthly_income.data = clean_currency_input(form.monthly_income.data)
            form.bonus.data = clean_currency_input(form.bonus.data)
            if tax_regime == 'old':
                form.investment_80c.data = clean_currency_input(form.investment_80c.data)
                form.medical_insurance.data = clean_currency_input(form.medical_insurance.data)
                form.home_loan_interest.data = clean_currency_input(form.home_loan_interest.data)
                form.education_loan_interest.data = clean_currency_input(form.education_loan_interest.data)
        
        if not form.validate_on_submit():
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{getattr(form, field).label.text}: {error}', 'error')
            return render_template('employee/calculate_tax.html', form=form)
        
        # Get form data and validate
        try:
            monthly_income = float(form.monthly_income.data)
            bonus = float(form.bonus.data or 0)
            investment_80c = float(form.investment_80c.data or 0)
            medical_insurance = float(form.medical_insurance.data or 0)
            home_loan_interest = float(form.home_loan_interest.data or 0)
            education_loan_interest = float(form.education_loan_interest.data or 0)
            tax_regime = form.tax_regime.data
        except ValueError as e:
            flash('Please enter valid numeric values for all fields.', 'error')
            return render_template('employee/calculate_tax.html', form=form)
        
        # Calculate annual values
        annual_income = (monthly_income * 12) + bonus
        standard_deduction = 50000 if tax_regime == 'old' else 0
        
        # Calculate deductions (only for old regime)
        total_deductions = 0
        if tax_regime == 'old':
            total_deductions = (
                standard_deduction +
                min(investment_80c, 150000) +  # Cap at limits
                min(medical_insurance, 25000) +
                min(home_loan_interest, 200000) +
                education_loan_interest
            )
        
        # Calculate taxable income
        taxable_income = max(0, annual_income - total_deductions)
        
        # Calculate tax based on regime
        tax_amount = 0
        tax_breakdown = []
        
        if tax_regime == 'old':
            # Old regime tax calculation
            if taxable_income <= 250000:
                tax_breakdown.append({
                    'bracket': '₹0 - ₹2,50,000',
                    'rate': 0,
                    'income_in_bracket': taxable_income,
                    'tax_amount': 0
                })
            else:
                remaining_income = taxable_income
                
                # First slab (0 - 250,000)
                first_slab = min(250000, remaining_income)
                tax_breakdown.append({
                    'bracket': '₹0 - ₹2,50,000',
                    'rate': 0,
                    'income_in_bracket': first_slab,
                    'tax_amount': 0
                })
                remaining_income -= first_slab
                
                # Second slab (250,001 - 500,000)
                if remaining_income > 0:
                    second_slab = min(250000, remaining_income)
                    tax_in_bracket = second_slab * 0.05
                    tax_amount += tax_in_bracket
                    tax_breakdown.append({
                        'bracket': '₹2,50,001 - ₹5,00,000',
                        'rate': 5,
                        'income_in_bracket': second_slab,
                        'tax_amount': tax_in_bracket
                    })
                    remaining_income -= second_slab
                
                # Third slab (500,001 - 1,000,000)
                if remaining_income > 0:
                    third_slab = min(500000, remaining_income)
                    tax_in_bracket = third_slab * 0.20
                    tax_amount += tax_in_bracket
                    tax_breakdown.append({
                        'bracket': '₹5,00,001 - ₹10,00,000',
                        'rate': 20,
                        'income_in_bracket': third_slab,
                        'tax_amount': tax_in_bracket
                    })
                    remaining_income -= third_slab
                
                # Fourth slab (Above 1,000,000)
                if remaining_income > 0:
                    tax_in_bracket = remaining_income * 0.30
                    tax_amount += tax_in_bracket
                    tax_breakdown.append({
                        'bracket': 'Above ₹10,00,000',
                        'rate': 30,
                        'income_in_bracket': remaining_income,
                        'tax_amount': tax_in_bracket
                    })
        else:
            # New regime tax calculation
            if taxable_income <= 300000:
                tax_breakdown.append({
                    'bracket': '₹0 - ₹3,00,000',
                    'rate': 0,
                    'income_in_bracket': taxable_income,
                    'tax_amount': 0
                })
            else:
                remaining_income = taxable_income
                
                # First slab (0 - 300,000)
                first_slab = min(300000, remaining_income)
                tax_breakdown.append({
                    'bracket': '₹0 - ₹3,00,000',
                    'rate': 0,
                    'income_in_bracket': first_slab,
                    'tax_amount': 0
                })
                remaining_income -= first_slab
                
                # Second slab (300,001 - 600,000)
                if remaining_income > 0:
                    second_slab = min(300000, remaining_income)
                    tax_in_bracket = second_slab * 0.05
                    tax_amount += tax_in_bracket
                    tax_breakdown.append({
                        'bracket': '₹3,00,001 - ₹6,00,000',
                        'rate': 5,
                        'income_in_bracket': second_slab,
                        'tax_amount': tax_in_bracket
                    })
                    remaining_income -= second_slab
                
                # Third slab (600,001 - 900,000)
                if remaining_income > 0:
                    third_slab = min(300000, remaining_income)
                    tax_in_bracket = third_slab * 0.10
                    tax_amount += tax_in_bracket
                    tax_breakdown.append({
                        'bracket': '₹6,00,001 - ₹9,00,000',
                        'rate': 10,
                        'income_in_bracket': third_slab,
                        'tax_amount': tax_in_bracket
                    })
                    remaining_income -= third_slab
                
                # Fourth slab (900,001 - 1,200,000)
                if remaining_income > 0:
                    fourth_slab = min(300000, remaining_income)
                    tax_in_bracket = fourth_slab * 0.15
                    tax_amount += tax_in_bracket
                    tax_breakdown.append({
                        'bracket': '₹9,00,001 - ₹12,00,000',
                        'rate': 15,
                        'income_in_bracket': fourth_slab,
                        'tax_amount': tax_in_bracket
                    })
                    remaining_income -= fourth_slab
                
                # Fifth slab (1,200,001 - 1,500,000)
                if remaining_income > 0:
                    fifth_slab = min(300000, remaining_income)
                    tax_in_bracket = fifth_slab * 0.20
                    tax_amount += tax_in_bracket
                    tax_breakdown.append({
                        'bracket': '₹12,00,001 - ₹15,00,000',
                        'rate': 20,
                        'income_in_bracket': fifth_slab,
                        'tax_amount': tax_in_bracket
                    })
                    remaining_income -= fifth_slab
                
                # Sixth slab (Above 1,500,000)
                if remaining_income > 0:
                    tax_in_bracket = remaining_income * 0.30
                    tax_amount += tax_in_bracket
                    tax_breakdown.append({
                        'bracket': 'Above ₹15,00,000',
                        'rate': 30,
                        'income_in_bracket': remaining_income,
                        'tax_amount': tax_in_bracket
                    })
        
        # Calculate surcharge and cess
        surcharge = 0
        if taxable_income > 10000000:  # Above 1 crore
            surcharge = tax_amount * 0.15
        elif taxable_income > 5000000:  # Above 50 lakhs
            surcharge = tax_amount * 0.10

        # Add health and education cess (4%)
        cess = (tax_amount + surcharge) * 0.04
        
        # Total tax liability
        total_tax = tax_amount + surcharge + cess
        
        # Create calculation result
        calculation_result = {
            'annual_income': annual_income,
            'total_deductions': total_deductions,
            'taxable_income': taxable_income,
            'tax_amount': tax_amount,
            'surcharge': surcharge,
            'cess': cess,
            'total_tax': total_tax,
            'tax_breakdown': tax_breakdown,
            'regime': 'Old' if tax_regime == 'old' else 'New'
        }
        
        # Save calculation to database
        try:
            logger.info("Attempting to save tax calculation...")
            
            # Get database path from config
            db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            logger.info(f"Database path: {db_path}")
            
            # Convert calculation details to JSON string
            calculation_details = json.dumps({
                'monthly_income': monthly_income,
                'bonus': bonus,
                'investment_80c': investment_80c,
                'medical_insurance': medical_insurance,
                'home_loan_interest': home_loan_interest,
                'education_loan_interest': education_loan_interest,
                'tax_breakdown': tax_breakdown,
                'surcharge': surcharge,
                'cess': cess,
                'base_tax': tax_amount
            })
            
            # Use direct SQLite connection
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Create table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tax_calculation (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_id INTEGER NOT NULL,
                        gross_income FLOAT NOT NULL,
                        deductions FLOAT NOT NULL,
                        taxable_income FLOAT NOT NULL,
                        tax_amount FLOAT NOT NULL,
                        tax_regime VARCHAR(10) NOT NULL,
                        calculation_details TEXT,
                        calculation_date DATETIME,
                        FOREIGN KEY(employee_id) REFERENCES employee(id)
                    )
                """)
                
                # Insert the calculation
                cursor.execute("""
                    INSERT INTO tax_calculation (
                        employee_id, gross_income, deductions, taxable_income,
                        tax_amount, tax_regime, calculation_details, calculation_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    current_user.id,
                    float(annual_income),
                    float(total_deductions),
                    float(taxable_income),
                    float(total_tax),
                    str(tax_regime),
                    calculation_details,
                    datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                ))
                
                conn.commit()
                logger.info("Tax calculation saved successfully")
                flash('Tax calculation completed and saved successfully!', 'success')
                
        except Exception as e:
            error_msg = f"Error saving tax calculation: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            flash('Your tax calculation was completed but could not be saved.', 'warning')
        
        return render_template('employee/calculate_tax.html', 
                             form=form, 
                             calculation_result=calculation_result)
                             
    except Exception as e:
        logger.error(f"Error in tax calculation: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred during tax calculation. Please try again.', 'error')
        return render_template('employee/calculate_tax.html', form=form)

@employee_bp.route('/calculation-history')
@login_required
@employee_required
def calculation_history():
    """View tax calculation history."""
    try:
        calculations = TaxCalculation.query\
            .filter_by(employee_id=current_user.id)\
            .order_by(TaxCalculation.calculation_date.desc())\
            .all()
        return render_template('employee/calculations.html', calculations=calculations)
    except Exception as e:
        logger.error(f"Error in calculation history: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while loading calculation history.', 'error')
        return render_template('errors/500.html'), 500

@employee_bp.route('/export-calculations')
@login_required
@employee_required
@limiter.limit("10 per hour")  # Rate limit: 10 exports per hour
def export_calculations():
    """Export tax calculations to CSV."""
    try:
        calculations = TaxCalculation.query\
            .filter_by(employee_id=current_user.id)\
            .order_by(TaxCalculation.calculation_date.desc())\
            .all()
            
        if not calculations:
            flash('No calculations to export.', 'warning')
            return redirect(url_for('employee.calculation_history'))
            
        # Create CSV data
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Gross Income', 'Deductions', 'Taxable Income', 'Tax Amount'])
        
        for calc in calculations:
            writer.writerow([
                calc.calculation_date.strftime('%Y-%m-%d %H:%M'),
                f"₹{calc.gross_income:,.2f}",
                f"₹{calc.deductions:,.2f}",
                f"₹{calc.taxable_income:,.2f}",
                f"₹{calc.tax_amount:,.2f}"
            ])
            
        # Create response
        output.seek(0)
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'tax_calculations_{datetime.now().strftime("%Y%m%d")}.csv'
        )
            
    except Exception as e:
        logger.error(f"Error exporting calculations: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while exporting calculations.', 'error')
        return redirect(url_for('employee.calculation_history'))
