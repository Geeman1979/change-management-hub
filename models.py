"""Database models for Change Management Hub."""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='change_manager')  # admin, change_manager, viewer
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class ProjectDocument(db.Model):
    """Uploaded project documents."""
    __tablename__ = 'project_documents'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    category = db.Column(db.String(100), default='General')  # e.g. Charter, Plan, Status, Risk
    filename = db.Column(db.String(500), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    file_type = db.Column(db.String(50), default='')
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)


class Statistic(db.Model):
    """Uploaded statistics / datasets for analytics."""
    __tablename__ = 'statistics'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    source = db.Column(db.String(200), default='')
    period = db.Column(db.String(100), default='')  # e.g. Q2 2026
    filename = db.Column(db.String(500), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    data_summary = db.Column(db.Text, default='')   # AI-generated summary
    chart_config = db.Column(db.Text, default='')    # JSON chart config
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)


class AudienceSegment(db.Model):
    """Target audience / stakeholder groups."""
    __tablename__ = 'audience_segments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    attributes = db.Column(db.Text, default='')       # JSON: key demographics, concerns
    communication_prefs = db.Column(db.Text, default='')  # JSON: preferred channels, tone
    stakeholder_level = db.Column(db.String(50), default='')  # Executive, Manager, Frontline, etc.
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))


class Communication(db.Model):
    """Generated communications."""
    __tablename__ = 'communications'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    comm_type = db.Column(db.String(50), default='email')  # email, memo, newsletter, presentation
    audience_id = db.Column(db.Integer, db.ForeignKey('audience_segments.id'), nullable=True)
    audience_name = db.Column(db.String(200), default='')
    content_text = db.Column(db.Text, default='')
    tone = db.Column(db.String(50), default='professional')
    purpose = db.Column(db.Text, default='')
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    generated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), default='draft')  # draft, finalised, sent

    # Output files
    docx_path = db.Column(db.String(500), default='')
    pptx_path = db.Column(db.String(500), default='')
    email_html = db.Column(db.Text, default='')


class Narrative(db.Model):
    """Narrative & messaging frameworks."""
    __tablename__ = 'narratives'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    narrative_type = db.Column(db.String(50), default='change_story')  # change_story, vision, key_message, talking_points
    content = db.Column(db.Text, default='')
    key_messages = db.Column(db.Text, default='')  # JSON array
    audience_id = db.Column(db.Integer, db.ForeignKey('audience_segments.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    version = db.Column(db.Integer, default=1)


class CorporateIdentity(db.Model):
    """Brand identity settings."""
    __tablename__ = 'corporate_identity'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(200), default='IMPACT Programme — Change Management Hub')
    primary_colour = db.Column(db.String(7), default='#001D38')
    secondary_colour = db.Column(db.String(7), default='#0a2744')
    accent_colour = db.Column(db.String(7), default='#C8A064')
    font_primary = db.Column(db.String(100), default="'Calibri','Segoe UI',sans-serif")
    font_heading = db.Column(db.String(100), default="'Calibri','Segoe UI',sans-serif")
    logo_path = db.Column(db.String(500), default='')
    footer_text = db.Column(db.String(300), default='Gold Fields · IMPACT Programme · Confidential')
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
