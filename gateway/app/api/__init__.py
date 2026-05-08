"""HTTP routers for the Inference Gateway."""

from app.api.admin import router as admin_router
from app.api.inference import router as inference_router

__all__ = ["admin_router", "inference_router"]
