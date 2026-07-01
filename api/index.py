"""Vercel serverless entry point for the Change Management Hub Flask app."""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app

# Vercel expects a WSGI app called 'app'
app = flask_app
