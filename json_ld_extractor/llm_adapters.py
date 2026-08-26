# -*- coding: utf-8 -*-
"""Adapter inference multi-provider (Ollama/Gemini/Groq/OpenAI/DeepSeek) dengan validasi output."""

import html
import json
import logging
import re
import time
import urllib.request
import warnings
import ollama
from typing import List, Optional, Union, Dict, Any, Callable
from pydantic import BaseModel, Field, ConfigDict, model_validator
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from config import Config


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
    """Menjalankan 1 step ekstraksi terfokus dengan provider agnostic (Ollama, Gemini, Groq, OpenAI)."""
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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"SYSTEM DIRECTIVE:\n{system_prompt}\n\nDATA TO EXTRACT:\n{user_text}"}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            content = res_data["candidates"][0]["content"]["parts"][0]["text"]

    # 2. OpenAI / Groq / DeepSeek / Custom Endpoint BYOK
    elif provider in ["openai", "groq", "deepseek", "custom", "openrouter"]:
        api_endpoint = base_url or ("https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1")
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
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            content = res_data["choices"][0]["message"]["content"]

    # 3. Default: Local Ollama (100% Offline)
    else:
        try:
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
        except Exception as e:
            err_str = str(e)
            if "Failed to connect" in err_str or "Connection" in err_str or "connection" in err_str.lower():
                raise RuntimeError(
                    "Layanan Ollama lokal (http://127.0.0.1:11434) belum aktif. "
                    "Pastikan aplikasi Ollama sudah dibuka di Windows atau jalankan 'ollama serve', "
                    "atau pilih Cloud Provider (Gemini/Groq) di Engine Settings."
                ) from e
            raise

    # 1. Bersihkan formatting markdown (```json ... ```) jika LLM menyertakannya
    cleaned_content = re.sub(r'^```(?:json)?\s*', '', content.strip(), flags=re.IGNORECASE)
    cleaned_content = re.sub(r'\s*```$', '', cleaned_content.strip())
    
    # 2. Parse JSON secara fleksibel
    try:
        raw_json = json.loads(cleaned_content)
    except Exception:
        m_json = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', cleaned_content)
        if m_json:
            try:
                raw_json = json.loads(m_json.group(1))
            except Exception:
                parsed = pydantic_schema.model_validate_json(cleaned_content)
                return parsed.model_dump(by_alias=True)
        else:
            parsed = pydantic_schema.model_validate_json(cleaned_content)
            return parsed.model_dump(by_alias=True)

    # 3. Auto-wrap jika model cloud (seperti Gemini Flash) mengembalikan top-level JSON List bukan Object
    if isinstance(raw_json, list):
        schema_name = getattr(pydantic_schema, '__name__', str(pydantic_schema))
        if 'Metric' in schema_name or 'Property' in schema_name:
            raw_json = {"properties_and_metrics": raw_json}
        elif 'Section' in schema_name:
            raw_json = {"sections": raw_json}
        elif 'Table' in schema_name:
            raw_json = {"tables": raw_json}
        elif 'Reference' in schema_name:
            raw_json = {"references_or_sources": raw_json}
        elif len(raw_json) > 0 and isinstance(raw_json[0], dict):
            raw_json = raw_json[0]
            
    # 4. Auto-map sinonim key dari berbagai model LLM
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
                clean[k] = _sanitize_for_pydantic(v)
            return clean
        elif isinstance(item, list):
            return [_sanitize_for_pydantic(x) for x in item]
        return item

    clean_raw_json = _sanitize_for_pydantic(raw_json)
    parsed = pydantic_schema.model_validate(clean_raw_json)
    return parsed.model_dump(by_alias=True)
