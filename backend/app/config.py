"""Application settings loaded from `.env`."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_PATH), env_file_encoding="utf-8", extra="ignore")

    # ===== Azure OpenAI =====
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY", repr=False)
    azure_openai_deployment_name: str = Field(default="gpt-4o", alias="AZURE_OPENAI_DEPLOYMENT_NAME")
    azure_openai_api_version: str = Field(default="2024-10-21", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_embed_deployment: str = Field(default="text-embedding-3-small", alias="AZURE_OPENAI_EMBED_DEPLOYMENT")

    # ===== Azure AI Search =====
    azure_search_endpoint: str = Field(default="", alias="AZURE_SEARCH_ENDPOINT")
    azure_search_api_key: str = Field(default="", alias="AZURE_SEARCH_API_KEY", repr=False)
    azure_search_law_index: str = Field(default="moving-law-index", alias="AZURE_SEARCH_LAW_INDEX")
    azure_search_procedure_index: str = Field(default="moving-procedure-index", alias="AZURE_SEARCH_PROCEDURE_INDEX")

    # ===== Azure Document Intelligence =====
    azure_docintel_endpoint: str = Field(default="", alias="AZURE_DOCINTEL_ENDPOINT")
    azure_docintel_api_key: str = Field(default="", alias="AZURE_DOCINTEL_API_KEY", repr=False)

    # ===== Azure Blob Storage =====
    azure_blob_connection_string: str = Field(default="", alias="AZURE_BLOB_CONNECTION_STRING", repr=False)
    azure_blob_container_name: str = Field(default="moving-guide-docs", alias="AZURE_BLOB_CONTAINER_NAME")

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
