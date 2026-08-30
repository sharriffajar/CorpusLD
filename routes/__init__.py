# -*- coding: utf-8 -*-
"""CorpusLD API routes package."""

from fastapi import APIRouter
from routes.system import router as system_router
from routes.documents import router as documents_router
from routes.extraction import router as extraction_router
from routes.exports import router as exports_router
from routes.chat import router as chat_router
from routes.enterprise import router as enterprise_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(documents_router)
api_router.include_router(extraction_router)
api_router.include_router(exports_router)
api_router.include_router(chat_router)
api_router.include_router(enterprise_router)

__all__ = [
    "api_router",
    "system_router",
    "documents_router",
    "extraction_router",
    "exports_router",
    "chat_router",
    "enterprise_router",
]
