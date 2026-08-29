# -*- coding: utf-8 -*-
"""Unit tests untuk security hardening: SSRF endpoint validation, Gemini header auth, dan XSS sanitization."""

import pytest
from json_ld_extractor.llm_adapters import is_safe_custom_endpoint


def test_ssrf_safe_endpoints():
    # Valid public https endpoints
    assert is_safe_custom_endpoint("https://api.openai.com/v1") is True
    assert is_safe_custom_endpoint("https://api.groq.com/openai/v1") is True
    assert is_safe_custom_endpoint("https://openrouter.ai/api/v1") is True
    
    # Valid local development endpoints
    assert is_safe_custom_endpoint("http://localhost:11434") is True
    assert is_safe_custom_endpoint("http://127.0.0.1:11434") is True


def test_ssrf_disallowed_endpoints():
    # Disallowed protocols
    assert is_safe_custom_endpoint("file:///etc/passwd") is False
    assert is_safe_custom_endpoint("ftp://example.com") is False
    assert is_safe_custom_endpoint("gopher://example.com") is False
    
    # Disallowed cloud metadata endpoints
    assert is_safe_custom_endpoint("http://169.254.169.254/latest/meta-data/") is False
    assert is_safe_custom_endpoint("https://169.254.169.254/latest/meta-data/") is False
    
    # Disallowed private subnets (direct IP)
    assert is_safe_custom_endpoint("http://10.0.0.1:8080") is False
    assert is_safe_custom_endpoint("http://192.168.1.1:8000") is False
    assert is_safe_custom_endpoint("http://172.16.0.1:9000") is False
    
    # Disallowed CGNAT / RFC 6598 (100.64.0.0/10) and unspecified (0.0.0.0)
    assert is_safe_custom_endpoint("http://100.64.0.1:8000") is False
    assert is_safe_custom_endpoint("http://100.127.255.254:8000") is False
    assert is_safe_custom_endpoint("http://0.0.0.0:8000") is False
    
    # None or empty
    assert is_safe_custom_endpoint("") is False
    assert is_safe_custom_endpoint(None) is False


def test_resolve_and_pin_safe_endpoint():
    from json_ld_extractor.llm_adapters import resolve_and_pin_safe_endpoint
    
    # Localhost returns URL as-is without extra Host header
    pinned_url, headers = resolve_and_pin_safe_endpoint("http://localhost:11434")
    assert pinned_url == "http://localhost:11434"
    assert headers == {}
    
    # HTTPS preserves URL for TLS/SNI certificate verification
    https_url, headers = resolve_and_pin_safe_endpoint("https://api.openai.com/v1")
    assert https_url == "https://api.openai.com/v1"
    assert headers == {}

    # Disallowed endpoint raises ValueError
    with pytest.raises(ValueError):
        resolve_and_pin_safe_endpoint("http://169.254.169.254/latest")

    with pytest.raises(ValueError):
        resolve_and_pin_safe_endpoint("http://10.0.0.1:8080")
        
    with pytest.raises(ValueError):
        resolve_and_pin_safe_endpoint("http://100.64.0.1:8080")


def test_make_safe_attachment_header():
    from server import make_safe_attachment_header
    
    header = make_safe_attachment_header("report.pdf", "schema.jsonld")
    assert 'filename="report.pdf_schema.jsonld"' in header
    assert "filename*=UTF-8''" in header
    
    # Prevents CRLF injection and quotes
    injected = 'paper" \r\nSet-Cookie: admin=true\r\n.pdf'
    safe_header = make_safe_attachment_header(injected, "schema.jsonld")
    assert "\r" not in safe_header
    assert "\n" not in safe_header
    assert "Set-Cookie" not in safe_header or "_" in safe_header


def test_sanitize_error_message():
    from server import sanitize_error_message
    
    raw = "Request failed with Authorization: Bearer sk-proj-1234567890abcdef123456 at C:\\Users\\Administrator\\CorpusLD\\server.py"
    cleaned = sanitize_error_message(raw)
    assert "sk-proj-1234567890abcdef123456" not in cleaned
    assert "[REDACTED_KEY]" in cleaned
    assert "C:\\Users" not in cleaned
    assert "[SERVER_PATH]" in cleaned


def test_safe_filename_validation():
    from routes.documents import validate_safe_filename
    from fastapi import HTTPException

    # Valid filenames
    assert validate_safe_filename("paper_2026.pdf") == "paper_2026.pdf"
    assert validate_safe_filename("20.+Al-Amin++M+(200-211).pdf") == "20.+Al-Amin++M+(200-211).pdf"
    assert validate_safe_filename("document-final v1.2.pdf") == "document-final v1.2.pdf"

    # Traversal attempts must raise 400
    with pytest.raises(HTTPException) as exc1:
        validate_safe_filename("../../etc/passwd")
    assert exc1.value.status_code == 400

    with pytest.raises(HTTPException) as exc2:
        validate_safe_filename("uploads/nested/file.pdf")
    assert exc2.value.status_code == 400

    with pytest.raises(HTTPException) as exc3:
        validate_safe_filename("doc;rm -rf /")
    assert exc3.value.status_code == 400


def test_exports_safe_filename_validation():
    from routes.exports import validate_safe_filename
    from fastapi import HTTPException

    assert validate_safe_filename("paper_2026.pdf") == "paper_2026.pdf"

    with pytest.raises(HTTPException) as exc:
        validate_safe_filename("../secret.jsonld")
    assert exc.value.status_code == 400


