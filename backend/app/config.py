"""Application settings loaded from `.env`."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ===== Azure OpenAI =====
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY", repr=False)
    azure_openai_deployment_name: str = Field(default="gpt-4o", alias="AZURE_OPENAI_DEPLOYMENT_NAME")
    azure_openai_api_version: str = Field(default="2024-10-21", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_embed_deployment: str = Field(
        default="text-embedding-3-small", alias="AZURE_OPENAI_EMBED_DEPLOYMENT"
    )

    # ===== Azure AI Search (3-index 체제) =====
    azure_search_endpoint: str = Field(default="", alias="AZURE_SEARCH_ENDPOINT")
    azure_search_api_key: str = Field(default="", alias="AZURE_SEARCH_API_KEY", repr=False)

    # 인덱스 이름
    azure_search_law_index: str = Field(default="law-index", alias="AZURE_SEARCH_LAW_INDEX")
    azure_search_guide_index: str = Field(default="guide-index", alias="AZURE_SEARCH_GUIDE_INDEX")
    azure_search_video_index: str = Field(default="video-index", alias="AZURE_SEARCH_VIDEO_INDEX")

    # 각 인덱스의 semantic config 이름
    azure_search_law_semantic_config: str = Field(
        default="law-semantic-config", alias="AZURE_SEARCH_LAW_SEMANTIC_CONFIG"
    )
    azure_search_guide_semantic_config: str = Field(
        default="guide-semantic-config", alias="AZURE_SEARCH_GUIDE_SEMANTIC_CONFIG"
    )
    azure_search_video_semantic_config: str = Field(
        default="video-semantic-config", alias="AZURE_SEARCH_VIDEO_SEMANTIC_CONFIG"
    )

    # ===== Azure Document Intelligence =====
    azure_docintel_endpoint: str = Field(default="", alias="AZURE_DOCINTEL_ENDPOINT")
    azure_docintel_api_key: str = Field(default="", alias="AZURE_DOCINTEL_API_KEY", repr=False)
    # 모델 ID: "prebuilt-layout" 기본, 커스텀 모델로 바꾸려면 Studio의 Model ID 입력
    # 현재 safecontract_service 는 아직 이 필드를 참조하지 않음 (팀 회의 후 리팩토링 예정)
    azure_docintel_model_id: str = Field(
        default="prebuilt-layout", alias="AZURE_DOCINTEL_MODEL_ID"
    )
    # Custom Neural 모델 — 등기부 구조화 추출. 공란이면 Custom 경로 비활성.
    # layout+LLM 결과에 보조로 머지 (confidence>0.8 식별 필드 덮어쓰기 + 위험 플래그 OR 머지)
    azure_docintel_custom_model_id: str = Field(
        default="", alias="AZURE_DOCINTEL_CUSTOM_MODEL_ID"
    )

    # ===== Azure Blob Storage =====
    azure_blob_connection_string: str = Field(
        default="", alias="AZURE_BLOB_CONNECTION_STRING", repr=False
    )
    azure_blob_container_name: str = Field(
        default="iim-rag-source", alias="AZURE_BLOB_CONTAINER_NAME"
    )

    # ===== External APIs =====
    data_go_kr_service_key: str = Field(default="", alias="DATA_GO_KR_SERVICE_KEY", repr=False)
    juso_api_key: str = Field(default="", alias="JUSO_API_KEY", repr=False)
    law_oc: str = Field(default="", alias="LAW_OC", repr=False)

    @property
    def azure_ready(self) -> bool:
        return bool(self.azure_openai_api_key and self.azure_search_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()