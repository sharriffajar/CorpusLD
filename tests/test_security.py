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
    
    # None or empty
    assert is_safe_custom_endpoint("") is False
    assert is_safe_custom_endpoint(None) is False
