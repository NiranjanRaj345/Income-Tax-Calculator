"""Main application module."""
from flask import Flask, render_template, redirect, url_for, jsonify, request, flash, send_file
from flask_login import LoginManager, current_user, login_required
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from models import db, Admin, Employee, TaxRule, TaxCalculation
from routes.main import main_bp
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.employee import employee_bp
from config import Config
import logging
import os
from werkzeug.middleware.proxy_fix import ProxyFix
import datetime
from io import BytesIO
from extensions import mail, limiter
import sqlite3

# Initialize extensions
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()

def ensure_directory_exists(directory):
    """Ensure directory exists and has proper permissions."""
    if not os.path.exists(directory):
        os.makedirs(directory, mode=0o777)
    os.chmod(directory, 0o777)
    return True

def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    
    # Configure logging
    logging.basicConfig(
        level=app.config['LOG_LEVEL'],
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Ensure required directories exist
    try:
        # Create instance directory
        ensure_directory_exists(app.instance_path)
        logger.info(f"Instance path: {app.instance_path}")
        
        # Create data directory if it doesn't exist
        ensure_directory_exists(app.config['DATA_DIR'])
        logger.info(f"Data directory: {app.config['DATA_DIR']}")
        
        # Create session directory if using filesystem sessions
        if app.config.get('SESSION_TYPE') == 'filesystem':
            ensure_directory_exists(app.config['SESSION_FILE_DIR'])
            logger.info(f"Session directory: {app.config['SESSION_FILE_DIR']}")
            
    except Exception as e:
        logger.error(f"Error creating directories: {str(e)}")
        raise
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    
    # Configure login manager
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID."""
        try:
            if not user_id:
                return None
                
            # Parse the user type and ID
            if '-' not in user_id:
                return None
                
            user_type, id_str = user_id.split('-')
            try:
                user_id = int(id_str)
            except ValueError:
                return None
            
            if user_type == 'admin':
                return Admin.query.get(user_id)
            elif user_type == 'employee':
                return Employee.query.get(user_id)
            return None
        except Exception as e:
            logger.error(f"Error loading user: {str(e)}")
            return None
    
    # Add template context processor
    @app.context_processor
    def utility_processor():
        from datetime import datetime
        return {
            'current_year': datetime.now().year
        }
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(employee_bp, url_prefix='/employee')
    
    # Register error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template('errors/429.html', 
                             message="Rate limit exceeded. Please try again later."), 429
    
    # Create database tables
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
            
            # Create admin user if none exists
            if not Admin.query.first():
                admin = Admin(
                    username='admin',
                    email='admin@example.com'
                )
                admin.set_password('admin')  # Change this in production!
                db.session.add(admin)
                db.session.commit()
                logger.info("Default admin user created")
                
            # Create default tax rules if none exist
            if not TaxRule.query.first():
                default_rules = [
                    TaxRule(min_income=0, max_income=250000, tax_rate=0, description="No tax"),
                    TaxRule(min_income=250000, max_income=500000, tax_rate=5, description="5% tax bracket"),
                    TaxRule(min_income=500000, max_income=750000, tax_rate=10, description="10% tax bracket"),
                    TaxRule(min_income=750000, max_income=1000000, tax_rate=15, description="15% tax bracket"),
                    TaxRule(min_income=1000000, max_income=1250000, tax_rate=20, description="20% tax bracket"),
                    TaxRule(min_income=1250000, max_income=1500000, tax_rate=25, description="25% tax bracket"),
                    TaxRule(min_income=1500000, max_income=None, tax_rate=30, description="30% tax bracket")
                ]
                for rule in default_rules:
                    db.session.add(rule)
                db.session.commit()
                logger.info("Default tax rules created")
                
        except Exception as e:
            logger.error(f"Database initialization error: {str(e)}")
            raise
    
    # Security headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response
    
    # Handle proxy headers
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Routes
    @app.route('/')
    def index():
        try:
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if isinstance(current_user, Admin):
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('tax_calculator'))
        except Exception as e:
            app.logger.error(f"Error in index route: {str(e)}")
            return render_template('errors/500.html'), 500

    @app.route('/tax-calculator')
    @login_required
    def tax_calculator():
        try:
            if isinstance(current_user, Admin):
                return redirect(url_for('admin_dashboard'))
            tax_rules = TaxRule.query.filter_by(is_active=True)\
                .filter(TaxRule.effective_from <= datetime.datetime.utcnow())\
                .filter((TaxRule.effective_to.is_(None)) | (TaxRule.effective_to >= datetime.datetime.utcnow()))\
                .order_by(TaxRule.min_income).all()
            return render_template('tax_calculator.html', tax_rules=tax_rules)
        except Exception as e:
            app.logger.error(f"Error in tax_calculator route: {str(e)}")
            return render_template('errors/500.html'), 500

    @app.route('/calculate-tax', methods=['POST'])
    @login_required
    def calculate_tax_route():
        try:
            if isinstance(current_user, Admin):
                return jsonify({'error': 'Admins cannot calculate taxes'}), 403
            
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            
            result = calculate_tax(data)
            
            # Save calculation if requested
            if data.get('save_calculation', False):
                calculation = save_tax_calculation(
                    current_user.id,
                    data,
                    result
                )
                result['calculation_id'] = calculation.id
            
            return jsonify(result)
        except Exception as e:
            app.logger.error(f"Error calculating tax: {str(e)}")
            return jsonify({'error': 'Error calculating tax'}), 500

    @app.route('/tax-history')
    @login_required
    def tax_history():
        try:
            if isinstance(current_user, Admin):
                return redirect(url_for('admin_dashboard'))
            
            page = request.args.get('page', 1, type=int)
            per_page = 10
            
            calculations = TaxCalculation.query.filter_by(user_id=current_user.id)\
                .order_by(TaxCalculation.calculation_date.desc())\
                .paginate(page=page, per_page=per_page)
            
            return render_template('tax_history.html', calculations=calculations)
        except Exception as e:
            app.logger.error(f"Error in tax_history route: {str(e)}")
            return render_template('errors/500.html'), 500

    @app.route('/generate-report/<int:calculation_id>')
    @login_required
    def generate_report(calculation_id):
        try:
            calculation = TaxCalculation.query.get_or_404(calculation_id)
            
            # Check if user has access to this calculation
            if calculation.user_id != current_user.id and not isinstance(current_user, Admin):
                abort(403)
            
            pdf = generate_tax_report(calculation_id)
            return send_file(
                BytesIO(pdf),
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'tax_report_{calculation_id}.pdf'
            )
        except Exception as e:
            app.logger.error(f"Error generating report: {str(e)}")
            flash('Error generating report', 'error')
            return redirect(url_for('tax_history'))

    @app.route('/tax-saving-tips')
    @login_required
    def tax_saving_tips():
        try:
            if isinstance(current_user, Admin):
                return redirect(url_for('admin_dashboard'))
            
            latest_calculation = TaxCalculation.query.filter_by(user_id=current_user.id)\
                .order_by(TaxCalculation.calculation_date.desc()).first()
            
            tips = []
            if latest_calculation:
                tips = latest_calculation.tax_result.get('tax_saving_tips', [])
            
            return render_template('tax_saving_tips.html', tips=tips)
        except Exception as e:
            app.logger.error(f"Error in tax_saving_tips route: {str(e)}")
            return render_template('errors/500.html'), 500

    # Admin routes
    @app.route('/admin/dashboard')
    @login_required
    def admin_dashboard():
        try:
            total_users = Employee.query.count()
            total_calculations = TaxCalculation.query.count()
            recent_calculations = TaxCalculation.query.order_by(
                TaxCalculation.calculation_date.desc()
            ).limit(5).all()
            
            return render_template('admin/dashboard.html',
                                 total_users=total_users,
                                 total_calculations=total_calculations,
                                 recent_calculations=recent_calculations)
        except Exception as e:
            app.logger.error(f"Error in admin_dashboard route: {str(e)}")
            return render_template('errors/500.html'), 500

    @app.route('/admin/tax-rules', methods=['GET', 'POST'])
    @login_required
    def manage_tax_rules():
        try:
            if request.method == 'POST':
                data = request.get_json()
                try:
                    rule = TaxRule(
                        min_income=float(data['min_income']),
                        max_income=float(data['max_income']) if data['max_income'] else None,
                        tax_rate=float(data['tax_rate']),
                        description=data['description'],
                        effective_from=datetime.datetime.strptime(data['effective_from'], '%Y-%m-%d'),
                        effective_to=datetime.datetime.strptime(data['effective_to'], '%Y-%m-%d') if data['effective_to'] else None,
                        created_by_id=current_user.id
                    )
                    db.session.add(rule)
                    db.session.commit()
                    return jsonify({'message': 'Tax rule added successfully'})
                except Exception as e:
                    db.session.rollback()
                    return jsonify({'error': str(e)}), 400
            
            tax_rules = TaxRule.query.order_by(TaxRule.min_income).all()
            return render_template('admin/tax_rules.html', tax_rules=tax_rules)
        except Exception as e:
            app.logger.error(f"Error in manage_tax_rules route: {str(e)}")
            return render_template('errors/500.html'), 500

    @app.route('/admin/users')
    @login_required
    def manage_users():
        try:
            users = Employee.query.order_by(Employee.created_at.desc()).all()
            return render_template('admin/users.html', users=users)
        except Exception as e:
            app.logger.error(f"Error in manage_users route: {str(e)}")
            return render_template('errors/500.html'), 500

    @app.route('/admin/reports')
    @login_required
    def admin_reports():
        try:
            report_type = request.args.get('type', 'daily')
            
            if report_type == 'daily':
                calculations = db.session.query(
                    db.func.date(TaxCalculation.calculation_date).label('date'),
                    db.func.count().label('count'),
                    db.func.avg(TaxCalculation.tax_result['tax_amount'].cast(db.Float)).label('avg_tax')
                ).group_by('date').order_by('date').all()
            else:
                calculations = db.session.query(
                    db.func.strftime('%Y-%m', TaxCalculation.calculation_date).label('month'),
                    db.func.count().label('count'),
                    db.func.avg(TaxCalculation.tax_result['tax_amount'].cast(db.Float)).label('avg_tax')
                ).group_by('month').order_by('month').all()
            
            return render_template('admin/reports.html',
                                 calculations=calculations,
                                 report_type=report_type)
        except Exception as e:
            app.logger.error(f"Error in admin_reports route: {str(e)}")
            return render_template('errors/500.html'), 500

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='127.0.0.1', port=5502, debug=True)
