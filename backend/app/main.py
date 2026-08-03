"""FastAPI application entry point."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Financial Complaint Routing System API",
        description=(
            "Supports financial complaint routing, AI predictions, and human review."
        ),
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return application


app = create_app()
