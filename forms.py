from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo

class ProfileForm(FlaskForm):
    """Form for updating user profile."""
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    current_password = PasswordField('Current Password')
    new_password = PasswordField('New Password', validators=[Length(min=6, message="Password must be at least 6 characters long")])
    confirm_password = PasswordField('Confirm New Password', validators=[EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField('Update Profile')
