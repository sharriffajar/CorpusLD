# -*- coding: utf-8 -*-
"""Unit tests for BYOK LLM and PDF Parser diagnostic test endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from server import app


@pytest.mark.anyio
async def test_diagnostics_pypdf_parser():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/diagnostics/parser/test", json={"parser": "pypdf"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["parser"] == "pypdf"
        assert "100% Offline" in data["message"]


@pytest.mark.anyio
async def test_diagnostics_hybrid_parser_fallback_warning():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/diagnostics/parser/test", json={"parser": "hybrid", "llamaparse_key": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "warning"
        assert data["parser"] == "hybrid"
        assert "locally with PyPDF" in data["message"]


@pytest.mark.anyio
async def test_diagnostics_llamaparse_missing_key_error():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/diagnostics/parser/test", json={"parser": "llamaparse", "llamaparse_key": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "API key" in data["message"]


@pytest.mark.anyio
async def test_diagnostics_llm_ollama_status():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/diagnostics/llm/test", json={"provider": "ollama"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "ollama"
        assert data["status"] in ["ok", "error"]


@pytest.mark.anyio
async def test_diagnostics_llm_gemini_missing_key():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/diagnostics/llm/test", json={"provider": "gemini", "api_key": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "gemini"
        assert data["status"] == "error"
        assert "API key is missing" in data["message"]


@pytest.mark.anyio
async def test_diagnostics_llm_custom_unsafe_url():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/diagnostics/llm/test", json={
            "provider": "custom",
            "base_url": "http://169.254.169.254/latest/meta-data"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "disallowed or targets an unsafe host" in data["message"]
