"""Main routes for the application."""
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, TaxCalculation
from utils import calculate_tax, generate_tax_report
import logging

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

@main_bp.route('/')
def index():
    """Home page route."""
    try:
        if current_user.is_authenticated:
            if hasattr(current_user, 'is_admin') and current_user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('employee.dashboard'))
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        return render_template('errors/500.html'), 500

@main_bp.route('/tax-calculator', methods=['GET', 'POST'])
@login_required
def tax_calculator():
    """Tax calculator route."""
    try:
        if request.method == 'POST':
            data = request.get_json()
            result = calculate_tax(data)
            return jsonify(result)
        return render_template('tax_calculator.html')
    except Exception as e:
        logger.error(f"Error in tax calculator: {str(e)}")
        return jsonify({'error': str(e)}), 500

@main_bp.route('/history')
@login_required
def history():
    """View tax calculation history."""
    try:
        calculations = TaxCalculation.query.filter_by(user_id=current_user.id).order_by(TaxCalculation.created_at.desc()).all()
        return render_template('history.html', calculations=calculations)
    except Exception as e:
        logger.error(f"Error retrieving history: {str(e)}")
        flash('Error retrieving calculation history.', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/report/<int:calculation_id>')
@login_required
def report(calculation_id):
    """Generate tax report for a specific calculation."""
    try:
        calculation = TaxCalculation.query.get_or_404(calculation_id)
        if calculation.user_id != current_user.id:
            return render_template('errors/403.html'), 403
            
        report_data = generate_tax_report(calculation)
        return jsonify(report_data)
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        return jsonify({'error': str(e)}), 500
