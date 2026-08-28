# -*- coding: utf-8 -*-
"""Adapter inference multi-provider (Ollama/Gemini/Groq/OpenAI/DeepSeek) dengan validasi output dan dukungan async."""

import html
import ipaddress
import json
import logging
import re
import socket
import time
import urllib.parse
import urllib.request
from typing import List, Optional, Union, Dict, Any, Callable
from config import Config

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def is_safe_custom_endpoint(endpoint_url: str) -> bool:
    """
    Validasi keamanan SSRF untuk parameter custom base_url:
    - Hanya memperbolehkan scheme http/https.
    - Memblokir Cloud Metadata IP (169.254.169.254) dan private IP blocks.
    """
    if not endpoint_url or not isinstance(endpoint_url, str):
        return False
    try:
        parsed = urllib.parse.urlparse(endpoint_url.strip())
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        
        # Local development loopback exceptions
        if hostname.lower() in ('localhost', '127.0.0.1', '::1'):
            return True

        # Check if IP address directly
        try:
            ip_obj = ipaddress.ip_address(hostname)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or str(ip_obj) == "169.254.169.254":
                return False
        except ValueError:
            # Domain name resolution check
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for res in addr_info:
                    sock_ip = res[4][0]
                    ip_obj = ipaddress.ip_address(sock_ip)
                    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or str(ip_obj) == "169.254.169.254":
                        return False
            except Exception:
                pass
        return True
    except Exception:
        return False


def repair_malformed_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Pemulihan heuristik untuk respons LLM berupa JSON yang terpotong,
    memiliki trailing commas, backslash LaTeX tidak ter-escape, atau unclosed braces/brackets.
    """
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    
    # 1. Coba parse langsung
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 2. Perbaiki backslash LaTeX unescaped (\frac, \sum, \alpha, etc.)
    fixed_escapes = re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', cleaned)
    try:
        return json.loads(fixed_escapes)
    except Exception:
        pass

    # 3. Cari blok objek {...} atau array [...]
    m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', fixed_escapes)
    if m:
        candidate = m.group(1)
        try:
            return json.loads(candidate)
        except Exception:
            # Hapus trailing commas: ,} -> } atau ,] -> ]
            candidate = re.sub(r',\s*([\}\]])', r'\1', candidate)
            # Perbaiki unquoted / numeric dictionary keys: { 1: ... } atau { key: ... }
            candidate = re.sub(r'(?<=[{,])\s*([A-Za-z0-9_]+)\s*:', r' "\1":', candidate)
            try:
                return json.loads(candidate)
            except Exception:
                pass

    # 4. Upaya penutupan bracket/brace yang menggantung akibat token limit
    open_braces = fixed_escapes.count('{') - fixed_escapes.count('}')
    open_brackets = fixed_escapes.count('[') - fixed_escapes.count(']')
    
    patched = fixed_escapes
    # Hapus trailing comma di ujung jika ada
    patched = re.sub(r',\s*$', '', patched)
    if open_brackets > 0:
        patched += ']' * open_brackets
    if open_braces > 0:
        patched += '}' * open_braces
        
    try:
        return json.loads(patched)
    except Exception:
        pass

    return None


def _post_process_json_response(raw_json: Any, pydantic_schema: Any) -> Dict[str, Any]:
    """Menormalisasi sinonim keys dan menyesuaikan format ke skema Pydantic."""
    schema_fields = getattr(pydantic_schema, 'model_fields', {})
    
    if isinstance(raw_json, list):
        schema_name = getattr(pydantic_schema, '__name__', str(pydantic_schema))
        if 'metrics' in schema_fields:
            raw_json = {"metrics": raw_json}
        elif 'Metric' in schema_name or 'Property' in schema_name:
            raw_json = {"properties_and_metrics": raw_json}
        elif 'Section' in schema_name:
            raw_json = {"sections": raw_json}
        elif 'Table' in schema_name:
            raw_json = {"tables": raw_json}
        elif 'Reference' in schema_name:
            raw_json = {"references_or_sources": raw_json}
        elif len(raw_json) > 0 and isinstance(raw_json[0], dict):
            raw_json = raw_json[0]
            
    if isinstance(raw_json, dict):
        if "title" in raw_json and "name" not in raw_json:
            raw_json["name"] = raw_json.pop("title")
        elif "headline" in raw_json and "name" not in raw_json:
            raw_json["name"] = raw_json.pop("headline")
            
        if "abstract" in raw_json and not raw_json.get("description"):
            raw_json["description"] = raw_json.pop("abstract")
        elif "summary" in raw_json and not raw_json.get("description"):
            raw_json["description"] = raw_json.pop("summary")
        elif "overview" in raw_json and not raw_json.get("description"):
            raw_json["description"] = raw_json.pop("overview")
        elif "desc" in raw_json and not raw_json.get("description"):
            raw_json["description"] = raw_json.pop("desc")
            
        if "authors" in raw_json and "author" not in raw_json:
            raw_json["author"] = raw_json.pop("authors")
        if "entities" in raw_json and "entities_involved" not in raw_json:
            raw_json["entities_involved"] = raw_json.pop("entities")
        if "tags" in raw_json and "keywords" not in raw_json:
            raw_json["keywords"] = raw_json.pop("tags")

        # Sinkronisasi dua arah 'metrics' vs 'properties_and_metrics' tergantung skema tujuan
        if "metrics" in schema_fields:
            if "properties_and_metrics" in raw_json and "metrics" not in raw_json:
                raw_json["metrics"] = raw_json.pop("properties_and_metrics")
            elif "properties" in raw_json and "metrics" not in raw_json:
                raw_json["metrics"] = raw_json.pop("properties")
        else:
            if "metrics" in raw_json and "properties_and_metrics" not in raw_json:
                raw_json["properties_and_metrics"] = raw_json.pop("metrics")
            elif "properties" in raw_json and "properties_and_metrics" not in raw_json:
                raw_json["properties_and_metrics"] = raw_json.pop("properties")
            
        if "chapters" in raw_json and "sections" not in raw_json:
            raw_json["sections"] = raw_json.pop("chapters")
        elif "parts" in raw_json and "sections" not in raw_json:
            raw_json["sections"] = raw_json.pop("parts")
            
        if "references" in raw_json and "references_or_sources" not in raw_json:
            raw_json["references_or_sources"] = raw_json.pop("references")
        elif "citations" in raw_json and "references_or_sources" not in raw_json:
            raw_json["references_or_sources"] = raw_json.pop("citations")
        elif "sources" in raw_json and "references_or_sources" not in raw_json:
            raw_json["references_or_sources"] = raw_json.pop("sources")

    def _sanitize_for_pydantic(item: Any) -> Any:
        if isinstance(item, dict):
            clean = {}
            for k, v in item.items():
                if k == "@type" and "type" not in item:
                    clean["type"] = _sanitize_for_pydantic(v)
                elif k in ("entities", "entities_involved") and isinstance(v, list):
                    clean[k] = [
                        {"name": x, "type": "Organization"} if isinstance(x, str) else _sanitize_for_pydantic(x)
                        for x in v
                    ]
                    continue
                elif k in ("authors", "author") and isinstance(v, list):
                    clean[k] = [
                        {"name": x, "type": "Person"} if isinstance(x, str) else _sanitize_for_pydantic(x)
                        for x in v
                    ]
                    continue
                clean[str(k)] = _sanitize_for_pydantic(v)
            return clean
        elif isinstance(item, list):
            return [_sanitize_for_pydantic(x) for x in item]
        return item

    clean_raw_json = _sanitize_for_pydantic(raw_json)
    try:
        parsed = pydantic_schema.model_validate(clean_raw_json)
        return parsed.model_dump(by_alias=True)
    except Exception:
        try:
            return pydantic_schema().model_dump(by_alias=True)
        except Exception:
            return clean_raw_json if isinstance(clean_raw_json, dict) else {}


def run_agentic_step(
    system_prompt: str, 
    user_text: str, 
    pydantic_schema: Any, 
    num_ctx: int = 4096,
    llm_provider: str = "ollama",
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Menjalankan 1 step ekstraksi sinkron dengan provider agnostic (Ollama, Gemini, Groq, OpenAI)."""
    model_to_use = llm_model or Config.OLLAMA_MODEL_NAME
    provider = (llm_provider or "ollama").lower()
    
    content = ""
    # 1. Google Gemini BYOK
    if provider == "gemini":
        key = api_key or Config.GEMINI_API_KEY
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY belum diset. "
                "Jalankan benchmark dengan argumen '--api-key YOUR_KEY' atau simpan GEMINI_API_KEY di file .env."
            )
        m_name = model_to_use if "gemini" in model_to_use else Config.GEMINI_MODEL_NAME
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"SYSTEM DIRECTIVE:\n{system_prompt}\n\nDATA TO EXTRACT:\n{user_text}"}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": key
        }
        
        if HAS_HTTPX:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                res_data = resp.json()
                content = res_data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                content = res_data["candidates"][0]["content"]["parts"][0]["text"]

    # 2. OpenAI / Groq / DeepSeek / Custom Endpoint BYOK
    elif provider in ["openai", "groq", "deepseek", "custom", "openrouter"]:
        if base_url:
            if not is_safe_custom_endpoint(base_url):
                raise ValueError(f"Disallowed or unsafe custom base_url: {base_url}")
            api_endpoint = base_url
        else:
            api_endpoint = "https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1"
        url = f"{api_endpoint.rstrip('/')}/chat/completions"
        payload = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": f"{system_prompt}\nOutput valid JSON following the schema."},
                {"role": "user", "content": user_text}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        if HAS_HTTPX:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                res_data = resp.json()
                content = res_data["choices"][0]["message"]["content"]
        else:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                content = res_data["choices"][0]["message"]["content"]

    # 3. Default: Local Ollama (100% Offline)
    else:
        try:
            import ollama
            response = ollama.chat(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                format=pydantic_schema.model_json_schema(),
                options={"temperature": 0.1, "num_ctx": num_ctx}
            )
            content = response["message"]["content"]
        except ImportError:
            raise RuntimeError("Package 'ollama' belum terinstall. Silakan pasang dengan 'pip install ollama' atau gunakan cloud provider (Gemini/Groq).")
        except Exception as e:
            err_str = str(e)
            if "Failed to connect" in err_str or "Connection" in err_str or "connection" in err_str.lower():
                raise RuntimeError(
                    "Layanan Ollama lokal (http://127.0.0.1:11434) belum aktif. "
                    "Pastikan aplikasi Ollama sudah dibuka di Windows atau jalankan 'ollama serve', "
                    "atau pilih Cloud Provider (Gemini/Groq) di Engine Settings."
                ) from e
            raise

    raw_json = repair_malformed_json(content)
    if raw_json is None:
        try:
            parsed = pydantic_schema.model_validate_json(content)
            return parsed.model_dump(by_alias=True)
        except Exception:
            try:
                return pydantic_schema().model_dump(by_alias=True)
            except Exception:
                return {}

    return _post_process_json_response(raw_json, pydantic_schema)


async def run_agentic_step_async(
    system_prompt: str, 
    user_text: str, 
    pydantic_schema: Any, 
    num_ctx: int = 4096,
    llm_provider: str = "ollama",
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Menjalankan 1 step ekstraksi asinkron (non-blocking) menggunakan httpx.AsyncClient."""
    model_to_use = llm_model or Config.OLLAMA_MODEL_NAME
    provider = (llm_provider or "ollama").lower()
    
    content = ""
    if provider == "gemini":
        key = api_key or Config.GEMINI_API_KEY
        if not key:
            raise RuntimeError("GEMINI_API_KEY belum diset.")
        m_name = model_to_use if "gemini" in model_to_use else Config.GEMINI_MODEL_NAME
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"SYSTEM DIRECTIVE:\n{system_prompt}\n\nDATA TO EXTRACT:\n{user_text}"}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": key
        }
        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                res_data = resp.json()
                content = res_data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return run_agentic_step(system_prompt, user_text, pydantic_schema, num_ctx, llm_provider, llm_model, api_key, base_url)

    elif provider in ["openai", "groq", "deepseek", "custom", "openrouter"]:
        if base_url:
            if not is_safe_custom_endpoint(base_url):
                raise ValueError(f"Disallowed or unsafe custom base_url: {base_url}")
            api_endpoint = base_url
        else:
            api_endpoint = "https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1"
        url = f"{api_endpoint.rstrip('/')}/chat/completions"
        payload = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": f"{system_prompt}\nOutput valid JSON following the schema."},
                {"role": "user", "content": user_text}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=35.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                res_data = resp.json()
                content = res_data["choices"][0]["message"]["content"]
        else:
            return run_agentic_step(system_prompt, user_text, pydantic_schema, num_ctx, llm_provider, llm_model, api_key, base_url)

    else:
        # Fallback sync run_agentic_step for local ollama
        return run_agentic_step(system_prompt, user_text, pydantic_schema, num_ctx, llm_provider, llm_model, api_key, base_url)

    raw_json = repair_malformed_json(content)
    if raw_json is None:
        try:
            parsed = pydantic_schema.model_validate_json(content)
            return parsed.model_dump(by_alias=True)
        except Exception:
            try:
                return pydantic_schema().model_dump(by_alias=True)
            except Exception:
                return {}

    return _post_process_json_response(raw_json, pydantic_schema)
