from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

def get_session_id(request: Request):
    """
    Identifies a session based on X-Session-ID or X-Client-ID headers.
    Falls back to remote IP address if neither is present.
    """
    return (
        request.headers.get("X-Session-ID") or 
        request.headers.get("X-Client-ID") or 
        get_remote_address(request)
    )

def get_global_key(request: Request):
    """
    Returns a constant key for global rate limiting across all users.
    """
    return "global_post_limit"

# Initialize Limiter
# We don't set default_limits to ensure SSE/streaming routes are NEVER rate limited by accident.
limiter = Limiter(key_func=get_remote_address)
