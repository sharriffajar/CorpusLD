import os
from dotenv import load_dotenv

load_dotenv(override=True)

if os.getenv("HF_HOME"):
    os.environ["HF_HOME"] = os.getenv("HF_HOME")

if os.getenv("OLLAMA_MODELS"):
    os.environ["OLLAMA_MODELS"] = os.getenv("OLLAMA_MODELS")

class Config:
    # Parser API Keys
    LLAMAPARSE_API_KEY = os.getenv("LLAMAPARSE_API_KEY", "")
    UNSTRUCTURED_API_KEY = os.getenv("UNSTRUCTURED_API_KEY", "")
    UNSTRUCTURED_SERVER_URL = os.getenv("UNSTRUCTURED_SERVER_URL", "https://api.unstructured.io/general/v0/general")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    
    # Vector DB & LLM Config
    QDRANT_URL = os.getenv("QDRANT_URL", "./qdrant_db")
    QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "corpusld_workspace")
    OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:3b")
    EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "ibm-granite/granite-embedding-107m-multilingual")
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))

    @classmethod
    def validate_keys(cls):
        return {
            "LlamaParse": "READY" if cls.LLAMAPARSE_API_KEY else "NOT SET",
            "Unstructured": "READY" if cls.UNSTRUCTURED_API_KEY else "NOT SET",
            "Local Fallback": "pypdf (Always Available)"
        }