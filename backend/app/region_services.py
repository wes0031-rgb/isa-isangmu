"""지역별 서비스 매핑 유틸 — 체크리스트 항목에 지역 맞춤 정보 주입.

MoveWise 의 fallback 체크리스트가 하드코딩 '해당 지역 수도사업소' 대신
실제 '성남시 상하수도사업소 031-729-3114' 같은 정확한 정보를 넣을 수 있도록
매핑 파일(`backend/data/mapping/*.json`)을 조회한다.

LLM 경로(structure_checklist_llm)에서도 같은 유틸을 써서 프롬프트 context 에
매핑 데이터를 주입할 수 있음.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

MAPPING_DIR = Path(__file__).resolve().parent.parent / "data" / "mapping"


@lru_cache(maxsize=32)
def _load(name: str) -> dict:
    path = MAPPING_DIR / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- 개별 서비스 조회 ----------


def find_water_office(region: str) -> Optional[dict]:
    """지역명으로 수도사업소 찾기 (구·군 세분화 우선, 실패 시 광역)."""
    data = _load("water_region_office")
    if not data:
        return None
    for office in data.get("offices", []):
        matched = any(m in region for m in office.get("region_match", []))
        if not matched:
            continue
        # 산하 사업소(구·시·군 단위) 우선 매칭
        for sub in office.get("sub_offices", []):
            for d in sub.get("district", []):
                if d in region:
                    return {
                        "name": sub["name"],
                        "phone": sub.get("phone", office["phone"]),
                        "website": office.get("website"),
                        "online_change_url": office.get("online_change_url"),
                        "sido_office": office["office_name"],
                    }
        # 산하 사업소 없거나 매칭 실패 → 광역 대표
        return {
            "name": office["office_name"],
            "phone": office.get("phone"),
            "website": office.get("website"),
            "online_change_url": office.get("online_change_url"),
            "sido_office": office["office_name"],
        }
    return None


# 수도권(서울/인천/경기) 세분화를 위한 서브 지역 매핑
_GAS_SUBREGION_HINTS = {
    "코원에너지": ["강남", "서초", "송파", "관악", "동작", "영등포", "구로", "금천"],
    "예스코": ["종로", "중구", "성동", "동대문", "중랑", "성북", "강북", "도봉", "노원", "광진"],
    "서울도시가스": ["용산", "마포", "은평", "서대문", "강서", "양천"],
    "삼천리": ["분당", "성남", "안산", "부천", "광명", "시흥", "안양", "의왕", "군포", "화성"],
    "귀뚜라미에너지": ["고양", "파주", "김포"],
    "대륜": ["의정부", "양주", "포천", "동두천", "연천"],
    "인천도시가스": ["인천"],
}


def find_gas_company(region: str) -> Optional[dict]:
    """지역명으로 도시가스 회사 찾기.

    수도권은 세분화 힌트로 추정, 그 외는 region 문자열이 포함되는 지역 첫 매칭.
    """
    data = _load("gas_region_company")
    if not data:
        return None
    entries = data.get("entries", [])

    # 1단계: 수도권 sub-region hint 매칭
    for hint_key, districts in _GAS_SUBREGION_HINTS.items():
        if any(d in region for d in districts):
            for e in entries:
                if hint_key in e["company"]:
                    return {
                        "name": e["company"],
                        "region": e["region"],
                        "note": f"{region} 지역은 {e['company']} 관할",
                    }

    # 2단계: 광역 region 직접 매칭
    region_keywords = [
        "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    ]
    matched_kw = next((kw for kw in region_keywords if kw in region), None)
    if matched_kw:
        for e in entries:
            if matched_kw in e["region"]:
                return {
                    "name": e["company"],
                    "region": e["region"],
                    "note": f"{region} 지역 대표 도시가스 공급사",
                }

    return None


def find_kepco_center(region: str) -> Optional[dict]:
    """지역명으로 한전 지역본부 찾기."""
    data = _load("kepco_electricity")
    if not data:
        return None
    for center in data.get("regional_centers", []):
        if any(r in region for r in center.get("region", [])):
            return {
                "name": center["name"],
                "phone": center["phone"],
                "common_call": data.get("common_call"),  # 123
                "online_url": data.get("online_change", {}).get("url"),
            }
    # 기본: 전국 123
    return {
        "name": "한국전력공사",
        "phone": data.get("common_call", "123"),
        "common_call": "123",
        "online_url": data.get("online_change", {}).get("url"),
    }


def find_education_office(region: str) -> Optional[dict]:
    """지역명으로 시·도 교육청 찾기."""
    data = _load("school_transfer")
    if not data:
        return None
    for office in data.get("sido_education_offices", []):
        if office["sido"] in region or any(
            key in region for key in [office["sido"][:2], office["sido"][:3]]
        ):
            return {
                "name": office["name"],
                "phone": office.get("phone"),
                "website": office.get("website"),
            }
    return None


def find_car_office(region: str) -> Optional[dict]:
    data = _load("car_registration")
    if not data:
        return None
    for office in data.get("sido_offices", []):
        if office["sido"] in region:
            return {
                "name": office["name"],
                "phone": office.get("phone"),
                "website": office.get("website"),
            }
    return None


def find_foreigner_office(region: str) -> Optional[dict]:
    data = _load("foreigner_registration")
    if not data:
        return None
    for office in data.get("major_offices", []):
        if any(r in region or region in r for r in office.get("region", [])):
            return {
                "name": office["name"],
                "phone": office.get("phone"),
                "common_call": data.get("call", "1345"),
            }
    return {
        "name": "외국인종합안내센터",
        "phone": data.get("call", "1345"),
        "common_call": data.get("call", "1345"),
    }


# ---------- 공통 서비스 (지역 무관) ----------


def get_telecom_providers() -> list[dict]:
    data = _load("telecom_internet")
    return [
        {
            "name": p["name"],
            "phone": p["short_call"],
            "move_url": p.get("move_url"),
        }
        for p in data.get("providers", [])
    ]


def get_post_office_info() -> dict:
    data = _load("post_office_mail_forwarding")
    return {
        "service_name": data.get("service"),
        "phone": data.get("call"),
        "online_url": data.get("online_url"),
        "validity_months": data.get("validity_months"),
        "fee": data.get("fee"),
    }


def get_gov24_service(name_keyword: str) -> Optional[dict]:
    """정부24 민원 이름으로 URL 찾기 (예: '전입신고')."""
    data = _load("gov24_services")
    for svc in data.get("services", []):
        if name_keyword in svc["name"]:
            return {
                "name": svc["name"],
                "url": svc.get("url"),
                "deep_link": svc.get("deep_link"),
                "deadline_days": svc.get("deadline_days"),
                "penalty": svc.get("penalty"),
            }
    return None


def get_animal_service() -> dict:
    data = _load("animal_registration")
    return {
        "website": data.get("website"),
        "phone": data.get("call"),
        "deadline_days": data.get("deadline_days"),
        "penalty": data.get("penalty"),
    }


# ---------- 체크리스트 항목 enrichment ----------


def enrich_item_with_region(item: dict, region: Optional[str]) -> dict:
    """체크리스트 항목에 지역 기반 정보 주입.

    체크리스트 generate 단계 맨 끝에서 호출. category 기반으로 적절한 매핑 조회
    후 method/contact/region_hint 필드를 실제 값으로 덮어쓰거나 추가.
    원본 item 을 변경하지 않고 새 dict 반환.
    """
    out = dict(item)
    cat = (item.get("category") or "").strip()
    if not region:
        return out

    # 수도
    if "수도" in cat:
        info = find_water_office(region)
        if info:
            out["contact"] = info.get("phone") or out.get("contact")
            out["region_hint"] = info.get("name")
            method_parts = []
            if info.get("online_change_url"):
                method_parts.append(f"온라인: {info['online_change_url']}")
            method_parts.append(f"전화: {info.get('phone', '-')}")
            out["method"] = " / ".join(method_parts)

    # 도시가스
    elif "도시가스" in cat or "가스" in cat:
        info = find_gas_company(region)
        if info:
            out["region_hint"] = info["name"]
            out["description"] = (
                f"{region} 지역 도시가스 공급사는 {info['name']}입니다. "
                "고객센터에 전화하여 명의변경을 신청하세요."
            )

    # 전기
    elif "전기" in cat:
        info = find_kepco_center(region)
        if info:
            out["contact"] = info.get("common_call", "123")
            out["region_hint"] = info.get("name")
            out["method"] = (
                f"한전 123 전화 또는 한전ON 앱 "
                f"({info.get('online_url') or 'https://online.kepco.co.kr'})"
            )

    # 인터넷·TV
    elif "인터넷" in cat or "TV" in cat or "통신" in cat:
        providers = get_telecom_providers()
        if providers:
            summary = ", ".join(
                f"{p['name']} {p['phone']}" for p in providers
            )
            out["method"] = f"통신사 이전 신청: {summary}"
            out["description"] = (
                "현재 가입된 통신사 고객센터에 전화하여 이사 7일 전에 "
                f"이전 설치 예약을 요청하세요. ({summary})"
            )

    # 우편물
    elif "우편" in cat or "우체국" in cat:
        info = get_post_office_info()
        out["contact"] = info.get("phone")
        out["method"] = (
            f"온라인: {info.get('online_url')} "
            f"({info.get('validity_months', 3)}개월 무료 전송)"
        )

    # 전입신고
    elif "전입신고" in cat:
        svc = get_gov24_service("전입신고")
        if svc:
            out["method"] = f"정부24 온라인: {svc.get('url')} 또는 주민센터 방문"
            if not out.get("deadline_days") and svc.get("deadline_days"):
                out["deadline_days"] = svc["deadline_days"]

    # 확정일자
    elif "확정일자" in cat:
        svc = get_gov24_service("확정일자")
        if svc:
            out["method"] = f"정부24: {svc.get('url')} 또는 주민센터 방문 (600원~1,000원)"

    # 반려동물
    elif "반려동물" in cat or "동물" in cat:
        info = get_animal_service()
        out["contact"] = info.get("phone")
        out["method"] = (
            f"{info.get('website')} 또는 정부24 / 시·군·구청 축산과 방문 "
            f"({info.get('deadline_days')}일 내, {info.get('penalty')})"
        )

    # 자동차
    elif "자동차" in cat:
        info = find_car_office(region)
        if info:
            out["contact"] = info.get("phone")
            out["region_hint"] = info.get("name")
            out["method"] = "정부24 온라인 또는 시·도 차량등록사업소 방문"

    # 자녀 전학
    elif "전학" in cat:
        info = find_education_office(region)
        if info:
            out["contact"] = info.get("phone")
            out["region_hint"] = info.get("name")
            out["method"] = f"전입신고 후 {info['name']} 또는 배정 학교에 전학 신청"

    # 외국인 등록
    elif "외국인" in cat:
        info = find_foreigner_office(region)
        if info:
            out["contact"] = info.get("phone")
            out["region_hint"] = info.get("name")
            out["method"] = (
                f"하이코리아(hikorea.go.kr) 또는 {info['name']} 방문 "
                f"(공통 콜센터 1345)"
            )

    return out
