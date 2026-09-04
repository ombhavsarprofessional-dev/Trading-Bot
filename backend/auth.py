"""
JWT Authentication helper and route decorators.
"""

import sys
import time
from pathlib import Path
from functools import wraps
from typing import Dict, Any, Optional
import jwt
from flask import request, jsonify

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import JWT_SECRET_KEY, JWT_EXPIRY_HOURS
from database.models import authenticate_user


def generate_token(username: str) -> str:
    """Generates a JWT token for the authenticated user."""
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + (JWT_EXPIRY_HOURS * 3600),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return token


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def jwt_required(f):
    """Decorator to require valid JWT in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None

        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1].strip()
        elif "token" in request.args:
            token = request.args.get("token")

        if not token:
            return jsonify({"error": "Missing authorization token"}), 401

        payload = decode_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired authorization token"}), 401

        # Attach username to request context
        request.current_user = payload.get("sub")
        return f(*args, **kwargs)

    return decorated
