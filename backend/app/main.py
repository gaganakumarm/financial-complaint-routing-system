"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes import (
    auth_router,
    benchmarks_router,
    benchmark_comparisons_router,
    complaints_router,
    datasets_router,
    dataset_examples_router,
    predictions_router,
    reviews_router,
    model_promotions_router,
)
from app.core.config import Settings, get_settings


def create_app(settings: Settings) -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title=settings.app_name,
        description=(
            "Supports financial complaint routing, AI predictions, and human review."
        ),
        debug=settings.debug,
    )
    application.state.settings = settings
    application.include_router(auth_router, prefix=settings.api_prefix)
    application.include_router(benchmarks_router, prefix=settings.api_prefix)
    application.include_router(benchmark_comparisons_router, prefix=settings.api_prefix)
    application.include_router(complaints_router, prefix=settings.api_prefix)
    application.include_router(datasets_router, prefix=settings.api_prefix)
    application.include_router(dataset_examples_router, prefix=settings.api_prefix)
    application.include_router(predictions_router, prefix=settings.api_prefix)
    application.include_router(reviews_router, prefix=settings.api_prefix)
    application.include_router(model_promotions_router, prefix=settings.api_prefix)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return application


app = create_app(get_settings())
