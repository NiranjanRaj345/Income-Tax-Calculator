"""Admin routes for the application."""
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for, session, send_file, Response
from flask_login import login_required, current_user
from models import db, TaxRule, TaxCalculation, Employee, AuditLog, Admin
from routes.auth import admin_required
import logging
import traceback
from sqlalchemy import func, text, extract, or_
from datetime import datetime, timedelta
import json
from extensions import limiter
import csv
from io import StringIO, BytesIO
import pdfkit
import sqlite3

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)

@admin_bp.before_request
def check_session_timeout():
    """Check if admin session has timed out."""
    try:
        if current_user.is_authenticated and hasattr(current_user, 'is_admin'):
            if 'last_seen' not in session:
                session['last_seen'] = datetime.utcnow().isoformat()
            else:
                try:
                    last_seen = datetime.fromisoformat(session.get('last_seen'))
                    if datetime.utcnow() - last_seen > timedelta(minutes=30):
                        session.clear()
                        flash('Your session has expired. Please login again.', 'warning')
                        return redirect(url_for('auth.login'))
                    session['last_seen'] = datetime.utcnow().isoformat()
                except (ValueError, TypeError) as e:
                    logger.error(f"Session timestamp error: {str(e)}")
                    session['last_seen'] = datetime.utcnow().isoformat()
    except Exception as e:
        logger.error(f"Session check error: {str(e)}\n{traceback.format_exc()}")
        session.clear()
        return redirect(url_for('auth.login'))

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard showing key statistics."""
    try:
        stats = {}
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        logger.info(f"Admin dashboard accessing database at: {db_path}")
        
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get basic statistics
            try:
                cursor.execute("SELECT COUNT(*) as count FROM employee")
                stats['total_employees'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM tax_calculation")
                stats['total_calculations'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM employee WHERE is_active = 1")
                stats['active_employees'] = cursor.fetchone()['count']
            except Exception as e:
                logger.error(f"Error getting basic statistics: {str(e)}")
                stats['total_employees'] = 0
                stats['total_calculations'] = 0
                stats['active_employees'] = 0
            
            # Get recent calculations
            try:
                cursor.execute("""
                    SELECT 
                        tc.*,
                        e.first_name,
                        e.last_name
                    FROM tax_calculation tc
                    JOIN employee e ON tc.employee_id = e.id
                    ORDER BY tc.calculation_date DESC
                    LIMIT 5
                """)
                
                rows = cursor.fetchall()
                formatted_calculations = []
                for row in rows:
                    formatted_calculations.append({
                        'employee_name': f"{row['first_name']} {row['last_name']}",
                        'annual_income': row['gross_income'],
                        'total_tax': row['tax_amount'],
                        'tax_regime': row['tax_regime'],
                        'date': datetime.strptime(row['calculation_date'], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
                    })
            except Exception as e:
                logger.error(f"Error getting recent calculations: {str(e)}")
                formatted_calculations = []
            
            # Get tax regime distribution
            try:
                cursor.execute("""
                    SELECT 
                        tax_regime,
                        COUNT(*) as count
                    FROM tax_calculation
                    GROUP BY tax_regime
                """)
                
                rows = cursor.fetchall()
                regime_distribution = {
                    'labels': [],
                    'data': []
                }
                for row in rows:
                    regime_distribution['labels'].append(row['tax_regime'].title() + ' Regime')
                    regime_distribution['data'].append(row['count'])
            except Exception as e:
                logger.error(f"Error getting tax regime distribution: {str(e)}")
                regime_distribution = {'labels': [], 'data': []}
            
            # Get monthly calculation trends
            try:
                cursor.execute("""
                    SELECT 
                        strftime('%Y-%m', calculation_date) as month,
                        COUNT(*) as count
                    FROM tax_calculation
                    WHERE calculation_date >= date('now', '-12 months')
                    GROUP BY strftime('%Y-%m', calculation_date)
                    ORDER BY month DESC
                """)
                
                rows = cursor.fetchall()
                monthly_trends = {
                    'labels': [],
                    'data': []
                }
                for row in rows:
                    monthly_trends['labels'].append(row['month'])
                    monthly_trends['data'].append(row['count'])
            except Exception as e:
                logger.error(f"Error getting monthly trends: {str(e)}")
                monthly_trends = {'labels': [], 'data': []}
        
        return render_template('admin/dashboard.html',
                             stats=stats,
                             recent_calculations=formatted_calculations,
                             regime_distribution=regime_distribution,
                             monthly_trends=monthly_trends)
    except Exception as e:
        logger.error(f"Error in admin dashboard: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while loading the dashboard.', 'error')
        return render_template('errors/500.html'), 500

@admin_bp.route('/tax-rules', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
@admin_required
def tax_rules():
    """Manage tax rules."""
    try:
        if request.method == 'GET':
            rules = TaxRule.query.order_by(TaxRule.min_income).all()
            return render_template('admin/tax_rules.html', rules=rules)
            
        elif request.method == 'POST':
            data = request.get_json()
            
            # Validate input
            required_fields = ['min_income', 'tax_rate', 'description']
            if not all(field in data for field in required_fields):
                return jsonify({'error': 'Missing required fields'}), 400
            
            # Validate numeric values
            try:
                min_income = float(data['min_income'])
                max_income = float(data.get('max_income', 0)) or None
                tax_rate = float(data['tax_rate'])
                
                if min_income < 0 or (max_income and max_income < min_income) or tax_rate < 0 or tax_rate > 100:
                    return jsonify({'error': 'Invalid numeric values'}), 400
            except ValueError:
                return jsonify({'error': 'Invalid numeric values'}), 400
            
            # Create new tax rule
            rule = TaxRule(
                min_income=min_income,
                max_income=max_income,
                tax_rate=tax_rate,
                description=data['description']
            )
            
            db.session.add(rule)
            
            # Add audit log
            audit = AuditLog(
                admin_id=current_user.id,
                action='create_tax_rule',
                details={
                    'min_income': min_income,
                    'max_income': max_income,
                    'tax_rate': tax_rate,
                    'description': data['description']
                }
            )
            db.session.add(audit)
            
            try:
                db.session.commit()
                return jsonify({'message': 'Tax rule created successfully', 'rule': rule.to_dict()}), 201
            except Exception as e:
                db.session.rollback()
                logger.error(f"Database error creating tax rule: {str(e)}")
                return jsonify({'error': 'Database error'}), 500
                
        elif request.method in ['PUT', 'DELETE']:
            rule_id = request.args.get('id')
            if not rule_id:
                return jsonify({'error': 'Rule ID required'}), 400
                
            rule = TaxRule.query.get_or_404(rule_id)
            
            if request.method == 'PUT':
                data = request.get_json()
                
                # Validate numeric values
                try:
                    min_income = float(data.get('min_income', rule.min_income))
                    max_income = float(data.get('max_income', rule.max_income or 0)) or None
                    tax_rate = float(data.get('tax_rate', rule.tax_rate))
                    
                    if min_income < 0 or (max_income and max_income < min_income) or tax_rate < 0 or tax_rate > 100:
                        return jsonify({'error': 'Invalid numeric values'}), 400
                except ValueError:
                    return jsonify({'error': 'Invalid numeric values'}), 400
                
                # Update rule
                rule.min_income = min_income
                rule.max_income = max_income
                rule.tax_rate = tax_rate
                rule.description = data.get('description', rule.description)
                
                # Add audit log
                audit = AuditLog(
                    admin_id=current_user.id,
                    action='update_tax_rule',
                    details={
                        'rule_id': rule_id,
                        'changes': data
                    }
                )
                db.session.add(audit)
                
            else:  # DELETE
                rule.is_active = False
                
                # Add audit log
                audit = AuditLog(
                    admin_id=current_user.id,
                    action='delete_tax_rule',
                    details={'rule_id': rule_id}
                )
                db.session.add(audit)
            
            try:
                db.session.commit()
                return jsonify({'message': f'Tax rule {"updated" if request.method == "PUT" else "deleted"} successfully'}), 200
            except Exception as e:
                db.session.rollback()
                logger.error(f"Database error modifying tax rule: {str(e)}")
                return jsonify({'error': 'Database error'}), 500
                
    except Exception as e:
        logger.error(f"Error in tax_rules route: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500

@admin_bp.route('/tax-rule/<int:rule_id>', methods=['GET'])
@login_required
@admin_required
def get_tax_rule(rule_id):
    """Get a specific tax rule."""
    try:
        rule = TaxRule.query.get_or_404(rule_id)
        return jsonify(rule.to_dict())
    except Exception as e:
        logger.error(f"Error getting tax rule: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500

@admin_bp.route('/tax-rule/<int:rule_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_tax_rule(rule_id):
    """Toggle a tax rule's active status."""
    try:
        rule = TaxRule.query.get_or_404(rule_id)
        rule.is_active = not rule.is_active
        
        # Add audit log
        audit = AuditLog(
            admin_id=current_user.id,
            action='toggle_tax_rule',
            details={
                'rule_id': rule_id,
                'new_status': rule.is_active
            }
        )
        db.session.add(audit)
        
        try:
            db.session.commit()
            return jsonify({
                'message': f'Tax rule {"activated" if rule.is_active else "deactivated"} successfully',
                'is_active': rule.is_active
            }), 200
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error toggling tax rule: {str(e)}")
            return jsonify({'error': 'Database error'}), 500
            
    except Exception as e:
        logger.error(f"Error toggling tax rule: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500

@admin_bp.route('/tax-rule/<int:rule_id>', methods=['PUT'])
@login_required
@admin_required
def update_tax_rule(rule_id):
    """Update a specific tax rule."""
    try:
        rule = TaxRule.query.get_or_404(rule_id)
        data = request.get_json()
        
        # Validate numeric values
        try:
            min_income = float(data.get('min_income', rule.min_income))
            max_income = float(data.get('max_income', rule.max_income or 0)) or None
            tax_rate = float(data.get('tax_rate', rule.tax_rate))
            
            if min_income < 0 or (max_income and max_income < min_income) or tax_rate < 0 or tax_rate > 100:
                return jsonify({'error': 'Invalid numeric values'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid numeric values'}), 400
        
        # Update rule
        rule.min_income = min_income
        rule.max_income = max_income
        rule.tax_rate = tax_rate
        rule.description = data.get('description', rule.description)
        
        # Add audit log
        audit = AuditLog(
            admin_id=current_user.id,
            action='update_tax_rule',
            details={
                'rule_id': rule_id,
                'changes': data
            }
        )
        db.session.add(audit)
        
        try:
            db.session.commit()
            return jsonify({
                'message': 'Tax rule updated successfully',
                'rule': rule.to_dict()
            }), 200
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error updating tax rule: {str(e)}")
            return jsonify({'error': 'Database error'}), 500
            
    except Exception as e:
        logger.error(f"Error updating tax rule: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Internal server error'}), 500

@admin_bp.route('/employees')
@login_required
@admin_required
def employees():
    """View and manage employees."""
    try:
        employees_list = db.session.query(Employee)\
            .order_by(Employee.created_at.desc())\
            .all()
        return render_template('admin/employees.html', employees=employees_list)
    except Exception as e:
        logger.error(f"Error in employees view: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while loading employees.', 'error')
        return render_template('errors/500.html'), 500

@admin_bp.route('/employees/<int:employee_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_employee_status(employee_id):
    """Toggle employee active status."""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        # Don't allow deactivating the current admin
        if employee.id == current_user.id:
            return jsonify({
                'success': False,
                'message': 'You cannot deactivate your own account.'
            }), 400
        
        # Toggle status
        employee.is_active = not employee.is_active
        db.session.commit()
        
        # Log the action
        action = 'activated' if employee.is_active else 'deactivated'
        AuditLog.log_action(
            actor_id=current_user.id,
            action=f"Employee {action}",
            details=f"Employee ID: {employee.id}, Email: {employee.email}"
        )
        
        flash(f'Employee {employee.email} has been {action}.', 'success')
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error toggling employee status: {str(e)}\n{traceback.format_exc()}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'An error occurred while updating employee status.'
        }), 500

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    """Generate and view reports."""
    try:
        # Get date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        # Get daily calculations with additional statistics
        daily_calculations = db.session.query(
            extract('year', TaxCalculation.calculation_date).label('year'),
            extract('month', TaxCalculation.calculation_date).label('month'),
            extract('day', TaxCalculation.calculation_date).label('day'),
            func.count(TaxCalculation.id).label('count'),
            func.avg(TaxCalculation.tax_amount).label('avg_tax'),
            func.sum(TaxCalculation.tax_amount).label('total_tax'),
            func.avg(TaxCalculation.gross_income).label('avg_income')
        ).filter(
            TaxCalculation.calculation_date.between(start_date, end_date)
        ).group_by(
            extract('year', TaxCalculation.calculation_date),
            extract('month', TaxCalculation.calculation_date),
            extract('day', TaxCalculation.calculation_date)
        ).order_by(
            extract('year', TaxCalculation.calculation_date),
            extract('month', TaxCalculation.calculation_date),
            extract('day', TaxCalculation.calculation_date)
        ).all()

        # Format the results
        formatted_calculations = []
        total_calculations = 0
        total_tax_collected = 0
        
        for calc in daily_calculations:
            date_obj = datetime(int(calc.year), int(calc.month), int(calc.day))
            total_calculations += calc.count
            total_tax_collected += calc.total_tax or 0
            
            formatted_calculations.append({
                'date': date_obj,
                'count': calc.count,
                'avg_tax': round(calc.avg_tax or 0, 2),
                'total_tax': round(calc.total_tax or 0, 2),
                'avg_income': round(calc.avg_income or 0, 2)
            })
        
        # Calculate summary statistics
        summary_stats = {
            'total_calculations': total_calculations,
            'total_tax_collected': round(total_tax_collected, 2),
            'avg_daily_calculations': round(total_calculations / len(formatted_calculations) if formatted_calculations else 0, 2),
            'avg_tax_per_calculation': round(total_tax_collected / total_calculations if total_calculations else 0, 2)
        }
        
        return render_template(
            'admin/reports.html',
            daily_calculations=formatted_calculations,
            summary_stats=summary_stats,
            start_date=start_date,
            end_date=end_date
        )
    except Exception as e:
        logger.error(f"Error in reports view: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while generating reports.', 'error')
        return render_template('errors/500.html'), 500

@admin_bp.route('/export-report/<format>')
@login_required
@admin_required
def export_report(format):
    """Export report in the specified format."""
    try:
        # Get date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        # Get daily calculations with additional statistics
        daily_calculations = db.session.query(
            extract('year', TaxCalculation.calculation_date).label('year'),
            extract('month', TaxCalculation.calculation_date).label('month'),
            extract('day', TaxCalculation.calculation_date).label('day'),
            func.count(TaxCalculation.id).label('count'),
            func.avg(TaxCalculation.tax_amount).label('avg_tax'),
            func.sum(TaxCalculation.tax_amount).label('total_tax'),
            func.avg(TaxCalculation.gross_income).label('avg_income')
        ).filter(
            TaxCalculation.calculation_date.between(start_date, end_date)
        ).group_by(
            extract('year', TaxCalculation.calculation_date),
            extract('month', TaxCalculation.calculation_date),
            extract('day', TaxCalculation.calculation_date)
        ).order_by(
            extract('year', TaxCalculation.calculation_date),
            extract('month', TaxCalculation.calculation_date),
            extract('day', TaxCalculation.calculation_date)
        ).all()

        # Format the results
        formatted_calculations = []
        total_calculations = 0
        total_tax_collected = 0
        
        for calc in daily_calculations:
            date_obj = datetime(int(calc.year), int(calc.month), int(calc.day))
            total_calculations += calc.count
            total_tax_collected += calc.total_tax or 0
            
            formatted_calculations.append({
                'date': date_obj,
                'count': calc.count,
                'avg_tax': round(calc.avg_tax or 0, 2),
                'total_tax': round(calc.total_tax or 0, 2),
                'avg_income': round(calc.avg_income or 0, 2)
            })
        
        # Calculate summary statistics
        summary_stats = {
            'total_calculations': total_calculations,
            'total_tax_collected': round(total_tax_collected, 2),
            'avg_daily_calculations': round(total_calculations / len(formatted_calculations) if formatted_calculations else 0, 2),
            'avg_tax_per_calculation': round(total_tax_collected / total_calculations if total_calculations else 0, 2)
        }

        if format == 'csv':
            # Create CSV file
            output = StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow(['Date', 'Number of Calculations', 'Average Tax', 'Total Tax', 'Average Income'])
            
            # Write data
            for calc in formatted_calculations:
                writer.writerow([
                    calc['date'].strftime('%Y-%m-%d'),
                    calc['count'],
                    calc['avg_tax'],
                    calc['total_tax'],
                    calc['avg_income']
                ])
            
            # Prepare response
            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment;filename=tax_report_{end_date.strftime("%Y%m%d")}.csv'}
            )
            
        elif format == 'pdf':
            # Render PDF template
            html = render_template(
                'admin/reports_pdf.html',
                daily_calculations=formatted_calculations,
                summary_stats=summary_stats,
                start_date=start_date,
                end_date=end_date,
                now=datetime.utcnow()
            )
            
            # Convert to PDF
            pdf = pdfkit.from_string(html, False)
            
            # Return PDF file
            return Response(
                pdf,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment;filename=tax_report_{end_date.strftime("%Y%m%d")}.pdf'}
            )
        
        else:
            flash('Invalid export format specified.', 'error')
            return redirect(url_for('admin.reports'))
            
    except Exception as e:
        logger.error(f"Error in export_report: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while generating the export.', 'error')
        return redirect(url_for('admin.reports'))

@admin_bp.route('/calculation-history')
@login_required
@admin_required
def calculation_history():
    """View detailed calculation history with filters."""
    try:
        # Get filter parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        min_amount = request.args.get('min_amount', type=float)
        max_amount = request.args.get('max_amount', type=float)
        search_name = request.args.get('search_name', '')
        
        # Base query
        query = db.session.query(
            TaxCalculation, Employee
        ).join(
            Employee, TaxCalculation.employee_id == Employee.id
        )
        
        # Apply filters
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(TaxCalculation.calculation_date >= start_date_obj)
            except ValueError:
                flash('Invalid start date format', 'error')
                
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date_obj = end_date_obj + timedelta(days=1)
                query = query.filter(TaxCalculation.calculation_date < end_date_obj)
            except ValueError:
                flash('Invalid end date format', 'error')
                
        if min_amount is not None:
            query = query.filter(TaxCalculation.tax_amount >= min_amount)
            
        if max_amount is not None:
            query = query.filter(TaxCalculation.tax_amount <= max_amount)
            
        if search_name:
            search_term = f"%{search_name}%"
            query = query.filter(
                or_(
                    Employee.first_name.ilike(search_term),
                    Employee.last_name.ilike(search_term)
                )
            )
            
        # Order by date descending
        query = query.order_by(TaxCalculation.calculation_date.desc())
        
        # Execute query
        history_data = query.all()
        
        # Format data for template
        calculations = []
        for calc, emp in history_data:
            calculations.append({
                'id': calc.id,
                'name': f"{emp.first_name} {emp.last_name}",
                'date': calc.calculation_date,
                'time': calc.calculation_date.strftime('%H:%M:%S'),
                'gross_income': calc.gross_income,
                'tax_amount': calc.tax_amount,
                'net_income': calc.gross_income - calc.tax_amount
            })
        
        return render_template(
            'admin/history.html',
            calculations=calculations,
            filters={
                'start_date': start_date,
                'end_date': end_date,
                'min_amount': min_amount,
                'max_amount': max_amount,
                'search_name': search_name
            }
        )
        
    except Exception as e:
        logger.error(f"Error in calculation history view: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while retrieving history.', 'error')
        return render_template('errors/500.html'), 500

@admin_bp.route('/export-calculation-history/<format>')
@login_required
@admin_required
def export_calculation_history(format):
    """Export history in the specified format."""
    try:
        # Get filter parameters (same as history route)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        min_amount = request.args.get('min_amount', type=float)
        max_amount = request.args.get('max_amount', type=float)
        search_name = request.args.get('search_name', '')
        
        # Base query
        query = db.session.query(
            TaxCalculation, Employee
        ).join(
            Employee, TaxCalculation.employee_id == Employee.id
        )
        
        # Apply filters
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(TaxCalculation.calculation_date >= start_date_obj)
            except ValueError:
                flash('Invalid start date format', 'error')
                
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date_obj = end_date_obj + timedelta(days=1)
                query = query.filter(TaxCalculation.calculation_date < end_date_obj)
            except ValueError:
                flash('Invalid end date format', 'error')
                
        if min_amount is not None:
            query = query.filter(TaxCalculation.tax_amount >= min_amount)
            
        if max_amount is not None:
            query = query.filter(TaxCalculation.tax_amount <= max_amount)
            
        if search_name:
            search_term = f"%{search_name}%"
            query = query.filter(
                or_(
                    Employee.first_name.ilike(search_term),
                    Employee.last_name.ilike(search_term)
                )
            )
            
        # Order by date descending
        query = query.order_by(TaxCalculation.calculation_date.desc())
        
        # Execute query
        history_data = query.all()
        
        # Format data
        calculations = []
        for calc, emp in history_data:
            calculations.append({
                'name': f"{emp.first_name} {emp.last_name}",
                'date': calc.calculation_date.strftime('%Y-%m-%d'),
                'time': calc.calculation_date.strftime('%H:%M:%S'),
                'gross_income': calc.gross_income,
                'tax_amount': calc.tax_amount,
                'net_income': calc.gross_income - calc.tax_amount
            })

        if format == 'csv':
            # Create CSV
            output = StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow(['Name', 'Date', 'Time', 'Gross Income', 'Tax Amount', 'Net Income'])
            
            # Write data
            for calc in calculations:
                writer.writerow([
                    calc['name'],
                    calc['date'],
                    calc['time'],
                    calc['gross_income'],
                    calc['tax_amount'],
                    calc['net_income']
                ])
            
            # Prepare response
            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment;filename=tax_history_{datetime.utcnow().strftime("%Y%m%d")}.csv'}
            )
            
        elif format == 'pdf':
            # Render PDF template
            html = render_template(
                'admin/history_pdf.html',
                calculations=calculations,
                start_date=start_date,
                end_date=end_date,
                generated_at=datetime.utcnow()
            )
            
            # Convert to PDF
            pdf = pdfkit.from_string(html, False)
            
            # Return PDF file
            return Response(
                pdf,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment;filename=tax_history_{datetime.utcnow().strftime("%Y%m%d")}.pdf'}
            )
        
        else:
            flash('Invalid export format specified.', 'error')
            return redirect(url_for('admin.calculation_history'))
            
    except Exception as e:
        logger.error(f"Error in export_calculation_history: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred while generating the export.', 'error')
        return redirect(url_for('admin.calculation_history'))
