"""WSGI entry point for Gunicorn and Waitress."""

from app import create_app

app = create_app()
