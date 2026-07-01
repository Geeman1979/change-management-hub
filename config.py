import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-mgmt-hub-secret-key-2026')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'database.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
    LOGO_FOLDER = os.path.join(basedir, 'static', 'logos')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

    # OpenAI config (optional — used for AI interpretation of stats)
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

    # Default corporate identity
    BRAND = {
        'primary_colour': '#001D38',       # Gold Fields navy
        'secondary_colour': '#0a2744',      # Slightly lighter navy
        'accent_colour': '#C8A064',         # Gold Fields gold
        'accent_hover': '#b38a4f',          # Darker gold
        'teal_colour': '#00B398',           # Gold Fields teal
        'text_light': '#ffffff',
        'text_dark': '#1d2733',
        'text_muted': '#6c7a8a',
        'card_bg': '#ffffff',
        'card_border': '#dfe4ea',
        'body_bg': '#eef1f4',
        'success': '#00B398',
        'warning': '#C8A064',
        'danger': '#c0392b',
        'info': '#44546A',
        'font_primary': "'Calibri','Segoe UI','Carlito',system-ui,sans-serif",
        'font_heading': "'Calibri','Segoe UI','Carlito',system-ui,sans-serif",
        'brand_name': 'IMPACT Programme — Change Management Hub',
        'brand_short': 'IMPACT CM Hub',
        'footer_text': 'Gold Fields · IMPACT Programme · Confidential',
    }
