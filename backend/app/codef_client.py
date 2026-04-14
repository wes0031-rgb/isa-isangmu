"""
CODEF (쿠콘) API 클라이언트 — 부동산등기부등본 조회용.

개발환경(demo) 에서는 CODEF 가 고정된 샘플 데이터를 돌려주므로 건당 과금 없이
SafeContract 기능을 시연할 수 있다. 운영환경 전환 시 .env 의 CODEF_API_ENV 를
'prod' 로, CODEF_BASE_URL 을 'https://api.codef.io' 로 바꾸면 된다.

핵심 기능:
  - OAuth 2.0 client_credentials grant 로 access_token 발급 및 메모리 캐싱
  - 7 일 유효기간, 만료 2 분 전 자동 갱신
  - 민감 필드(주민번호·비밀번호·암호) 는 CODEF 공개키로 RSA-PKCS1 암호화
  - 부동산등기부등본 열람 API 호출 래퍼
  - 샘플 모드 여부를 응답에 표시
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import unquote

import httpx

log = logging.getLogger(__name__)


@dataclass
class CodefConfig:
    client_id: str
    client_secret: str
    base_url: str
    oauth_url: str
    public_key_b64: str
    env_mode: str  # "demo" / "prod"

    @classmethod
    def from_env(cls) -> Optional["CodefConfig"]:
        cid = os.environ.get("CODEF_CLIENT_ID")
        csec = os.environ.get("CODEF_CLIENT_SECRET")
        if not cid or not csec:
            return None
        return cls(
            client_id=cid,
            client_secret=csec,
            base_url=os.environ.get("CODEF_BASE_URL", "https://development.codef.io"),
            oauth_url=os.environ.get("CODEF_OAUTH_URL", "https://oauth.codef.io/oauth/token"),
            public_key_b64=os.environ.get("CODEF_PUBLIC_KEY", ""),
            env_mode=os.environ.get("CODEF_API_ENV", "demo"),
        )


class CodefClient:
    """
    토큰 캐싱 + 민감값 암호화 + API 호출 래퍼.
    인스턴스 하나를 싱글턴처럼 재사용한다 (get_client()).
    """

    _token: Optional[str] = None
    _token_exp: float = 0.0

    def __init__(self, cfg: CodefConfig):
        self.cfg = cfg
        self._http = httpx.Client(timeout=30.0)

    # ---------- OAuth ----------

    def _fetch_token(self) -> str:
        auth_raw = f"{self.cfg.client_id}:{self.cfg.client_secret}".encode()
        auth_b64 = base64.b64encode(auth_raw).decode()
        r = self._http.post(
            self.cfg.oauth_url,
            headers={
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": "read"},
        )
        r.raise_for_status()
        payload = r.json()
        self._token = payload["access_token"]
        # 만료 2분 전에 갱신
        self._token_exp = time.time() + float(payload.get("expires_in", 604799)) - 120
        log.info("CODEF access_token 발급 완료 (exp=%.0fs)", payload.get("expires_in", 0))
        return self._token  # type: ignore[return-value]

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp:
            return self._token
        return self._fetch_token()

    # ---------- 암호화 ----------

    def encrypt_sensitive(self, plaintext: str) -> str:
        """CODEF 공개키로 RSA/PKCS1 암호화 → base64 문자열 반환.

        실제 조회 시 민감값(주민번호·비밀번호) 이 필요한 API 에서만 호출된다.
        개발환경 등기부등본 조회는 민감값 불필요.
        cryptography 패키지는 lazy import — 패키지 미설치 시 RuntimeError.
        """
        if not self.cfg.public_key_b64:
            raise RuntimeError("CODEF_PUBLIC_KEY 가 .env 에 없음")
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
        except ImportError as e:
            raise RuntimeError(
                "민감값 암호화에는 cryptography 패키지가 필요합니다. "
                "pip install cryptography"
            ) from e
        # PEM 없이 DER base64 만 저장된 경우에도 동작하도록 PEM 래핑
        pem = (
            "-----BEGIN PUBLIC KEY-----\n"
            + "\n".join(
                self.cfg.public_key_b64[i : i + 64]
                for i in range(0, len(self.cfg.public_key_b64), 64)
            )
            + "\n-----END PUBLIC KEY-----\n"
        )
        key = serialization.load_pem_public_key(pem.encode())
        cipher = key.encrypt(plaintext.encode("utf-8"), PKCS1v15())  # type: ignore[attr-defined]
        return base64.b64encode(cipher).decode()

    # ---------- API 호출 ----------

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """
        CODEF API 는 response 가 URL-encoded JSON 으로 2 중 인코딩되어 있는 경우가 있어
        수동으로 decode.
        """
        token = self._get_token()
        url = self.cfg.base_url.rstrip("/") + path
        r = self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        raw = r.text
        # CODEF 응답 본문은 URL-encoded 되어 내려오는 관행이 있어 시도 후 fallback
        try:
            return json.loads(unquote(raw))
        except json.JSONDecodeError:
            return json.loads(raw)

    # ---------- 부동산등기부등본 주소 검색 ----------
    #
    # CODEF 부동산등기부등본 조회는 2-way 인증 구조:
    #   1차: 주소로 해당 주소의 등기부 후보 목록 조회 (무료, 샘플 응답)
    #   2차: 후보 중 하나 선택 → 실 등기부등본 본문 (유료, 선불카드 필요)
    #
    # 개발환경에서 1차 호출은 실제 대법원 등기소 데이터를 반환 — 시연에 충분.
    # 2차 호출은 운영환경 + 선불카드 등록 이후 제공.

    REAL_ESTATE_REGISTER_PATH = "/v1/kr/public/ck/real-estate-register/status"

    def search_real_estate_candidates(
        self,
        address: str,
        real_estate_type: str = "1",  # 1=집합건물 2=토지 3=건물
    ) -> dict[str, Any]:
        """
        1차 — 주소 기반 등기부 후보 목록 조회.
        반환 dict 는 원본 CODEF 응답을 그대로 포함하며, MoveWise 에서는 `data.extraInfo.resAddrList`
        를 꺼내 사용자에게 선택지로 보여준다.

        개발환경 필수 값:
          - ePrepayPass 는 평문 4 자리 (암호화하지 말 것)
          - password 는 4 자리 숫자의 RSA 암호화
          - ePrepayNo 는 임의 13 자리 숫자
        """
        enc_pw = self.encrypt_sensitive("1234")
        body = {
            "organization": "0002",
            "phoneNo": "01012345678",
            "password": enc_pw,
            "inquiryType": "1",  # 1=열람
            "realEstateType": real_estate_type,
            "address": address,
            "originDataYN": "1",
            "isIdentityViewYN": "0",
            "ePrepayNo": "1234567890123",
            "ePrepayPass": "1234",
        }
        return self.post(self.REAL_ESTATE_REGISTER_PATH, body)

    def issue_real_estate_register(
        self,
        address: str,
        unique_no: str,
        first_response: dict[str, Any],
        real_estate_type: str = "1",
    ) -> dict[str, Any]:
        """
        2차 — 선택한 고유번호로 실 등기부등본 발급.
        운영환경 + 선불카드 번호 필요. 개발환경에서는 CF-13321 로 실패한다 (시연용).
        """
        data = first_response.get("data", {})
        enc_pw = self.encrypt_sensitive("1234")
        body = {
            "organization": "0002",
            "phoneNo": "01012345678",
            "password": enc_pw,
            "inquiryType": "1",
            "realEstateType": real_estate_type,
            "address": address,
            "uniqueNo": unique_no,
            "originDataYN": "1",
            "isIdentityViewYN": "0",
            "ePrepayNo": "1234567890123",
            "ePrepayPass": "1234",
            "is2Way": True,
            "twoWayInfo": {
                "jobIndex": data.get("jobIndex", 0),
                "threadIndex": data.get("threadIndex", 0),
                "jti": data.get("jti"),
                "twoWayTimestamp": data.get("twoWayTimestamp"),
            },
        }
        return self.post(self.REAL_ESTATE_REGISTER_PATH, body)


# ---------- 싱글턴 ----------

_client: Optional[CodefClient] = None


def get_client() -> Optional[CodefClient]:
    global _client
    if _client is not None:
        return _client
    cfg = CodefConfig.from_env()
    if cfg is None:
        return None
    _client = CodefClient(cfg)
    return _client


def is_configured() -> bool:
    return get_client() is not None


def env_mode() -> str:
    c = get_client()
    return c.cfg.env_mode if c else "unavailable"
