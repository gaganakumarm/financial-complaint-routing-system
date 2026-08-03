"""FastAPI application entry point."""

from fastapi import FastAPI

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

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return application


app = create_app(get_settings())
