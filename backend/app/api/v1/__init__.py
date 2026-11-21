"""Version 1 of the public API, mounted at /api/v1."""
from app.api.v1.router import api_router

__all__ = ["api_router"]
