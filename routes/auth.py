"""Authentication routes for the application."""
from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Employee, Admin
from forms.auth_forms import LoginForm, RegistrationForm, PasswordResetRequestForm, PasswordResetForm
from forms import ProfileForm
from functools import wraps
import logging
import traceback
from datetime import datetime, timedelta
import secrets
from flask_mail import Message
from extensions import mail, limiter

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

def admin_required(f):
    """Decorator to check if current user is an admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user, Admin):
            logger.warning(f"Unauthorized access attempt to admin route by user: {current_user}")
            return render_template('errors/403.html'), 403
        return f(*args, **kwargs)
    return decorated_function

def validate_password(password):
    """Validate password strength."""
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    return True, "Password is valid"

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    try:
        # If user is already logged in, redirect to appropriate dashboard
        if current_user.is_authenticated:
            if isinstance(current_user, Admin):
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('employee.dashboard'))
        
        form = LoginForm()
        if form.validate_on_submit():
            email = form.email.data.lower()
            password = form.password.data
            remember = form.remember.data
            
            # Try admin login first
            user = Admin.query.filter_by(email=email).first()
            if not user:
                # If not admin, try employee
                user = Employee.query.filter_by(email=email).first()
            
            if user and user.check_password(password):
                # Log the user in
                login_user(user, remember=remember)
                
                # Set session variables
                session['user_type'] = 'admin' if isinstance(user, Admin) else 'employee'
                session['last_seen'] = datetime.utcnow().isoformat()
                
                # Update last login time
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                # Log successful login
                logger.info(f"User {email} logged in successfully")
                
                # Redirect based on user type
                if isinstance(user, Admin):
                    return redirect(url_for('admin.dashboard'))
                return redirect(url_for('employee.dashboard'))
            
            flash('Invalid email or password.', 'error')
            logger.warning(f"Failed login attempt for email: {email}")
            
        return render_template('auth/login.html', form=form)
        
    except Exception as e:
        logger.error(f"Error in login route: {str(e)}")
        flash('An error occurred. Please try again.', 'error')
        return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    try:
        user_type = 'admin' if isinstance(current_user, Admin) else 'employee'
        logout_user()
        session.clear()
        flash('You have been logged out successfully.', 'success')
        return redirect(url_for('auth.login'))
    except Exception as e:
        logger.error(f"Error in logout route: {str(e)}")
        flash('An error occurred during logout.', 'error')
        return redirect(url_for('main.index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle employee registration."""
    try:
        if current_user.is_authenticated:
            return redirect(url_for('main.dashboard'))
            
        form = RegistrationForm()
        if form.validate_on_submit():
            # Check if email already exists
            if Employee.query.filter_by(email=form.email.data.lower()).first():
                flash('Email already registered.', 'error')
                return render_template('auth/register.html', form=form)
                
            # Validate password
            is_valid, message = validate_password(form.password.data)
            if not is_valid:
                flash(message, 'error')
                return render_template('auth/register.html', form=form)
                
            # Create new employee
            employee = Employee(
                email=form.email.data.lower(),
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                is_active=True
            )
            employee.set_password(form.password.data)
            
            try:
                db.session.add(employee)
                db.session.commit()
                
                # Log the user in
                login_user(employee)
                session['user_type'] = 'employee'
                session['last_seen'] = datetime.utcnow().isoformat()
                
                flash('Registration successful!', 'success')
                return redirect(url_for('employee.dashboard'))
            except Exception as e:
                logger.error(f"Database error in registration: {str(e)}")
                db.session.rollback()
                flash('An error occurred during registration.', 'error')
                return render_template('auth/register.html', form=form)
                
        return render_template('auth/register.html', form=form)
        
    except Exception as e:
        logger.error(f"Error in registration: {str(e)}\n{traceback.format_exc()}")
        flash('An error occurred during registration.', 'error')
        return render_template('auth/register.html', form=form)

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password_request():
    """Handle password reset request."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        user = Employee.query.filter_by(email=form.email.data).first()
        if user:
            token = secrets.token_urlsafe(32)
            # Store token in session with expiry
            session['reset_token'] = token
            session['reset_email'] = user.email
            session['reset_expiry'] = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            
            # Send reset email
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            msg = Message('Password Reset Request',
                        sender='noreply@taxcalc.com',
                        recipients=[user.email])
            msg.body = f'''To reset your password, visit the following link:
{reset_url}

If you did not make this request, please ignore this email.
'''
            mail.send(msg)
            
        # Always show same message whether user exists or not
        flash('If an account exists with that email, you will receive reset instructions.', 'info')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password_request.html', form=form)

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    # Verify token from session
    if not session.get('reset_token') or session.get('reset_token') != token:
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('auth.login'))
        
    # Check token expiry
    try:
        expiry = datetime.fromisoformat(session.get('reset_expiry', ''))
        if datetime.utcnow() > expiry:
            session.pop('reset_token', None)
            session.pop('reset_email', None)
            session.pop('reset_expiry', None)
            flash('Password reset link has expired.', 'error')
            return redirect(url_for('auth.login'))
    except (ValueError, TypeError):
        flash('Invalid reset link.', 'error')
        return redirect(url_for('auth.login'))
        
    form = PasswordResetForm()
    if form.validate_on_submit():
        user = Employee.query.filter_by(email=session.get('reset_email')).first()
        if user:
            # Validate password
            is_valid, message = validate_password(form.password.data)
            if not is_valid:
                flash(message, 'error')
                return render_template('auth/reset_password.html', form=form)
                
            user.set_password(form.password.data)
            db.session.commit()
            
            # Clear session data
            session.pop('reset_token', None)
            session.pop('reset_email', None)
            session.pop('reset_expiry', None)
            
            flash('Your password has been reset.', 'success')
            return redirect(url_for('auth.login'))
            
        flash('Error resetting password.', 'error')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html', form=form)

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Handle user profile management."""
    try:
        form = ProfileForm()
        if form.validate_on_submit():
            # Update name
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data

            # Update password if provided
            if form.current_password.data and form.new_password.data:
                if not current_user.check_password(form.current_password.data):
                    flash('Current password is incorrect.', 'error')
                    return render_template('auth/profile.html', form=form)
                
                # Validate new password
                is_valid, message = validate_password(form.new_password.data)
                if not is_valid:
                    flash(message, 'error')
                    return render_template('auth/profile.html', form=form)
                
                current_user.set_password(form.new_password.data)
                flash('Password updated successfully.', 'success')
                
            db.session.commit()
            flash('Profile updated successfully.', 'success')
            return redirect(url_for('auth.profile'))
            
        # Pre-populate form with current user data
        if request.method == 'GET':
            form.first_name.data = current_user.first_name
            form.last_name.data = current_user.last_name
            
        return render_template('auth/profile.html', form=form)
        
    except Exception as e:
        logger.error(f"Error in profile route: {str(e)}")
        flash('An error occurred. Please try again.', 'error')
        return render_template('auth/profile.html', form=form)
