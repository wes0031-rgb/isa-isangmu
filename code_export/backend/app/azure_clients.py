"""Thin wrappers around Azure SDK clients.

Clients are lazily constructed so the app can boot without Azure credentials
(useful for local dev). When credentials are missing, services fall back to
deterministic mock responses — see `checklist_service.py` and `safecontract_service.py`.
"""
from __future__ import annotations

from functools import lru_cache

from .config import get_settings


@lru_cache(maxsize=1)
def get_openai_client():
    settings = get_settings()
    if not settings.azure_openai_api_key or not settings.azure_openai_endpoint:
        return None
    from openai import AzureOpenAI

    return AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
    )


@lru_cache(maxsize=1)
def get_search_client_procedure():
    settings = get_settings()
    if not settings.azure_search_api_key or not settings.azure_search_endpoint:
        return None
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_procedure_index,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


@lru_cache(maxsize=1)
def get_search_client_law():
    settings = get_settings()
    if not settings.azure_search_api_key or not settings.azure_search_endpoint:
        return None
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_law_index,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


@lru_cache(maxsize=1)
def get_docintel_client():
    settings = get_settings()
    if not settings.azure_docintel_api_key or not settings.azure_docintel_endpoint:
        return None
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    return DocumentIntelligenceClient(
        endpoint=settings.azure_docintel_endpoint,
        credential=AzureKeyCredential(settings.azure_docintel_api_key),
    )
