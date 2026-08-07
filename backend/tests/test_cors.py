"""Tests for explicit browser-origin access to the API."""

import httpx
import pytest

from app.core.config import Settings
from app.main import create_app


@pytest.mark.anyio
async def test_allowed_origin_preflight_is_explicit_and_restricted() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings(_env_file=None)))
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options("/api/auth/login", headers=headers)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == headers["Origin"]
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers
    assert response.headers["access-control-allow-origin"] != "*"
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.anyio
async def test_regular_allowed_origin_receives_exact_cors_header() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings(_env_file=None)))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health", headers={"Origin": "http://localhost:5173"}
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.anyio
async def test_unapproved_origin_receives_no_cors_permission() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings(_env_file=None)))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health", headers={"Origin": "https://untrusted.example"}
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.anyio
async def test_custom_production_origin_is_supported() -> None:
    origin = "https://operations.example.com"
    settings = Settings(cors_allowed_origins=origin, _env_file=None)
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin
