"""Tests for the health check endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_check_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["environment"] == "test"
