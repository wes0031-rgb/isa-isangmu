"""Thin wrappers around Azure SDK clients.

Clients are lazily constructed so the app can boot without Azure credentials
(useful for local dev). When credentials are missing, services fall back to
deterministic mock responses — see `checklist_service.py` and `safecontract_service.py`.

3-index 체제 (experiment/schema-refactor):
  - get_search_client_law()    → law-index
  - get_search_client_guide()  → guide-index
  - get_search_client_video()  → video-index
  - get_search_client_procedure() → guide-index alias (레거시 호환)
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


def _build_search_client(index_name: str):
    """Azure AI Search 클라이언트 공통 빌더. 키 없으면 None."""
    settings = get_settings()
    if not settings.azure_search_api_key or not settings.azure_search_endpoint:
        return None
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


@lru_cache(maxsize=1)
def get_search_client_law():
    return _build_search_client(get_settings().azure_search_law_index)


@lru_cache(maxsize=1)
def get_search_client_guide():
    return _build_search_client(get_settings().azure_search_guide_index)


@lru_cache(maxsize=1)
def get_search_client_video():
    return _build_search_client(get_settings().azure_search_video_index)


def get_search_client_procedure():
    """DEPRECATED: 팀 unified 인덱스 시대 호환용 alias. guide-index로 리다이렉트.

    safecontract_service 등 레거시 호출부를 점진 교체하기 위한 얇은 wrapper.
    차후 커밋에서 모든 호출부가 get_search_client_guide()로 교체되면 제거 예정.
    """
    return get_search_client_guide()


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