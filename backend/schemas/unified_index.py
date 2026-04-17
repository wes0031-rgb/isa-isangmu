"""단일 통합 인덱스 스키마 (Option B).

A (법률) / B (행정절차) / C (유튜브) 를 하나의 Azure AI Search 인덱스로
업로드하기 위한 Pydantic 모델. `source_type` 디스크리미네이터로 타입을 구분하고,
타입별 특화 필드는 nullable 로 유지.

Usage:
    from backend.schemas.unified_index import UnifiedChunk, SourceType

    chunk = UnifiedChunk(
        id="law_abc123",
        source_id="주택임대차보호법__제3조",
        source_type="law",
        title="대항력 등",
        content="① 임대차는 그 등기가 없는 경우에도...",
        source_url="https://www.law.go.kr/...",
        law_name="주택임대차보호법",
        article="제3조",
    )
"""
from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, Field

SourceType = Literal["law", "procedure", "video"]


def make_safe_id(prefix: str, source_id: str) -> str:
    """사람이 읽는 source_id → Azure Search 규칙(영숫자·_·-·=) 에 맞는 안전 ID.

    Azure Search document key 제약상 한글 직접 사용 불가. 16-char sha1 prefix 로
    결정적(deterministic) 변환 — 세션 간 재현 가능하고 충돌 확률 극히 낮음.
    """
    h = hashlib.sha1(source_id.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{h}"


class UnifiedChunk(BaseModel):
    """모든 인덱스 타입을 수용하는 단일 스키마.

    Azure Search 는 `null` 필드를 sparse 하게 저장하므로, 타입별 특화 필드가
    많더라도 저장 비용·쿼리 성능에 거의 영향 없음.
    """

    # ===== Core (모든 타입 공통) =====
    id: str = Field(description="Azure-safe key: {prefix}_{sha1[:16]}")
    source_id: str = Field(description="사람이 읽는 원본 ID (디버깅·매핑용)")
    source_type: SourceType
    title: str
    content: str
    source_url: str
    deep_link: Optional[str] = None  # 유튜브 타임코드 링크
    keywords: list[str] = Field(default_factory=list)
    category: list[str] = Field(default_factory=list)
    fetched_at: str = Field(description="ISO date (YYYY-MM-DD)")

    # ===== 유저 프로필 필터 (3 타입 공통) =====
    applicable_to: list[str] = Field(
        default_factory=lambda: ["자취", "신혼", "가족"],
        description="해당 가구 유형",
    )
    contract_type: list[str] = Field(
        default_factory=lambda: ["전세", "월세", "자가"],
        description="해당 계약 유형",
    )
    region: str = "전국"

    # ===== 법적 메타 =====
    deadlines: list[str] = Field(default_factory=list)

    # ===== 크로스 인덱스 =====
    related_laws: list[str] = Field(default_factory=list)
    related_procedures: list[str] = Field(default_factory=list)
    related_videos: list[str] = Field(default_factory=list)

    # ===== Type-specific: law =====
    law_name: Optional[str] = None
    article: Optional[str] = None

    # ===== Type-specific: procedure =====
    parent_doc: Optional[str] = None
    breadcrumb: Optional[str] = None
    chunk_index: Optional[int] = None
    chunk_total: Optional[int] = None

    # ===== Type-specific: video =====
    video_id: Optional[str] = None
    channel: Optional[str] = None
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    timecode: Optional[str] = None

    # ===== 벡터 (Azure OpenAI 임베딩 후 채움) =====
    content_vector: Optional[list[float]] = None


# Azure AI Search 인덱스 스키마 JSON 생성 함수 (upload_to_search.py 에서 사용)
def azure_index_schema(index_name: str = "moving-unified-index") -> dict:
    """Pydantic 모델 기반으로 Azure Search 인덱스 JSON 스키마 생성.

    필드별 searchable/filterable/facetable 속성은 RAG 품질 관점에서 수동 튜닝.
    """
    return {
        "name": index_name,
        # NOTE: "description" 필드는 Azure Search API 2024-07-01 에서 제거됨 (지원 안 함)
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True, "retrievable": True},
            {"name": "source_id", "type": "Edm.String", "searchable": False, "filterable": True, "retrievable": True},
            {"name": "source_type", "type": "Edm.String", "searchable": False, "filterable": True, "facetable": True, "retrievable": True},
            {"name": "title", "type": "Edm.String", "searchable": True, "retrievable": True, "analyzer": "ko.lucene"},
            {"name": "content", "type": "Edm.String", "searchable": True, "retrievable": True, "analyzer": "ko.lucene"},
            {"name": "source_url", "type": "Edm.String", "searchable": False, "retrievable": True},
            {"name": "deep_link", "type": "Edm.String", "searchable": False, "retrievable": True},
            {"name": "keywords", "type": "Collection(Edm.String)", "searchable": True, "filterable": True, "facetable": True, "retrievable": True},
            {"name": "category", "type": "Collection(Edm.String)", "searchable": False, "filterable": True, "facetable": True, "retrievable": True},
            {"name": "fetched_at", "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True, "retrievable": True},
            # 유저 프로필 필터
            {"name": "applicable_to", "type": "Collection(Edm.String)", "searchable": False, "filterable": True, "facetable": True, "retrievable": True},
            {"name": "contract_type", "type": "Collection(Edm.String)", "searchable": False, "filterable": True, "facetable": True, "retrievable": True},
            {"name": "region", "type": "Edm.String", "searchable": False, "filterable": True, "facetable": True, "retrievable": True},
            # 법적 메타
            {"name": "deadlines", "type": "Collection(Edm.String)", "searchable": True, "filterable": True, "facetable": True, "retrievable": True},
            # 크로스 인덱스
            {"name": "related_laws", "type": "Collection(Edm.String)", "searchable": True, "filterable": True, "retrievable": True},
            {"name": "related_procedures", "type": "Collection(Edm.String)", "searchable": False, "filterable": True, "retrievable": True},
            {"name": "related_videos", "type": "Collection(Edm.String)", "searchable": False, "filterable": True, "retrievable": True},
            # Type-specific: law
            {"name": "law_name", "type": "Edm.String", "searchable": True, "filterable": True, "facetable": True, "retrievable": True, "analyzer": "ko.lucene"},
            {"name": "article", "type": "Edm.String", "searchable": False, "filterable": True, "retrievable": True},
            # Type-specific: procedure
            {"name": "parent_doc", "type": "Edm.String", "searchable": False, "filterable": True, "retrievable": True},
            {"name": "breadcrumb", "type": "Edm.String", "searchable": True, "retrievable": True, "analyzer": "ko.lucene"},
            {"name": "chunk_index", "type": "Edm.Int32", "filterable": True, "retrievable": True},
            {"name": "chunk_total", "type": "Edm.Int32", "filterable": True, "retrievable": True},
            # Type-specific: video
            {"name": "video_id", "type": "Edm.String", "searchable": False, "filterable": True, "retrievable": True},
            {"name": "channel", "type": "Edm.String", "searchable": True, "filterable": True, "facetable": True, "retrievable": True},
            {"name": "start_seconds", "type": "Edm.Double", "filterable": True, "retrievable": True},
            {"name": "end_seconds", "type": "Edm.Double", "filterable": True, "retrievable": True},
            {"name": "timecode", "type": "Edm.String", "searchable": False, "retrievable": True},
            # 벡터
            {
                "name": "content_vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "filterable": False,
                "retrievable": False,
                "dimensions": 1536,
                "vectorSearchProfile": "movewise-vector-profile",
            },
        ],
        "vectorSearch": {
            "algorithms": [
                {
                    "name": "movewise-hnsw",
                    "kind": "hnsw",
                    "hnswParameters": {
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500,
                        "metric": "cosine",
                    },
                }
            ],
            "profiles": [
                {"name": "movewise-vector-profile", "algorithm": "movewise-hnsw"}
            ],
        },
        "semantic": {
            "configurations": [
                {
                    "name": "movewise-semantic",
                    "prioritizedFields": {
                        "titleField": {"fieldName": "title"},
                        "prioritizedContentFields": [
                            {"fieldName": "content"},
                            {"fieldName": "breadcrumb"},
                        ],
                        "prioritizedKeywordsFields": [
                            {"fieldName": "keywords"},
                            {"fieldName": "law_name"},
                            {"fieldName": "channel"},
                            {"fieldName": "category"},
                        ],
                    },
                }
            ]
        },
    }
