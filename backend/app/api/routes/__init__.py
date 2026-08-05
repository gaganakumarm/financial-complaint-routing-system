"""Public API router exports."""

from app.api.routes.auth import router as auth_router
from app.api.routes.benchmarks import router as benchmarks_router
from app.api.routes.complaints import router as complaints_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.dataset_examples import router as dataset_examples_router
from app.api.routes.predictions import router as predictions_router
from app.api.routes.reviews import router as reviews_router

__all__ = [
    "auth_router",
    "benchmarks_router",
    "complaints_router",
    "datasets_router",
    "dataset_examples_router",
    "predictions_router",
    "reviews_router",
]
