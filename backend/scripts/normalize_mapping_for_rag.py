"""mapping/*.json → mapping_chunks.jsonl 정규화.

각 파일마다 구조가 다른 mapping JSON 들을 Azure AI Search mapping-index
용 공통 스키마로 변환. 출력은 JSONL (1 청크/line).

입력 : backend/data/mapping/*.json          (원본, 건드리지 않음)
출력 : backend/data/indexes/mapping_chunks.jsonl  (RAG 전용 청크)
      backend/data/indexes/mapping_summary.json  (통계)

패턴별 handler 구조:
- simple          (18개): 평평한 service 문서 → 1 청크
- regional        (2개):  본체 + regional_centers/sub_offices → N+1 청크
- multi_provider  (1개):  공통 + providers → N+1 청크
- mapping_table   (2개):  entries region 그룹핑 → 광역 단위 청크
- multi_level     (1개):  school_transfer 전용
- categorized_sub (1개):  gov24_services 전용
- guide_phases    (1개):  moveout_timeline (D-day 단위)
- guide_stages    (1개):  moveout_deposit_return (단계 단위)
- guide_generic   (4개):  나머지 moveout_* (1~3 청크)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
IN_DIR = ROOT / "backend" / "data" / "mapping"
OUT_DIR = ROOT / "backend" / "data" / "indexes"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSONL = OUT_DIR / "mapping_chunks.jsonl"
OUT_SUMMARY = OUT_DIR / "mapping_summary.json"

TODAY = date.today().isoformat()


# ============================================================
# 파일명 → 패턴 매핑
# ============================================================

FILE_PATTERN: dict[str, str] = {
    # --- Pattern A: Simple service (평평한 구조) ---
    "animal_registration.json": "simple",
    "hometax_nts.json": "simple",
    "nhis_health_insurance.json": "simple",
    "nps_national_pension.json": "simple",
    "mma_military.json": "simple",
    "kftc_accounts.json": "simple",
    "iros_registry.json": "simple",
    "post_office_mail_forwarding.json": "simple",
    "hug_ansim_jeonse.json": "simple",
    "jeonse_victim_support.json": "simple",
    "welfare_address_change.json": "simple",
    "resident_id_reissue.json": "simple",
    "foreigner_registration.json": "simple",
    "legal_aid_132.json": "simple",
    "moj_standard_contract.json": "simple",
    "lease_dispute_committee.json": "simple",
    "seoul_realty_check.json": "simple",
    "building_ledger.json": "simple",
    # --- Pattern B: Regional breakdown ---
    "kepco_electricity.json": "regional",
    "water_region_office.json": "regional",
    # --- Pattern C: Multi-provider ---
    "telecom_internet.json": "multi_provider",
    # --- Pattern D: Pure mapping table ---
    "gas_region_company.json": "mapping_table",
    "hug_default_list.json": "mapping_table",
    # --- Pattern E: Multi-level service ---
    "school_transfer.json": "multi_level",
    # --- Pattern F: Categorized sub-services ---
    "gov24_services.json": "categorized_sub",
    # --- Pattern G: Structured guide ---
    "moveout_timeline.json": "guide_phases",
    "moveout_deposit_return.json": "guide_stages",
    "moveout_restoration.json": "guide_generic",
    "moveout_waste_disposal.json": "guide_generic",
    "moveout_management_refund.json": "guide_generic",
    "moveout_termination_notice.json": "guide_generic",
}

# 파일 source_id → service_category (chunk_easylaw CATEGORY_RULES 호환)
SERVICE_CATEGORY: dict[str, str] = {
    "animal_registration": "반려동물 주소변경",
    "hometax_nts": "행정-세금",
    "nhis_health_insurance": "행정-건강보험",
    "nps_national_pension": "행정-국민연금",
    "mma_military": "행정-병무",
    "kftc_accounts": "행정-금융계좌",
    "iros_registry": "행정-등기",
    "post_office_mail_forwarding": "우편물 전환",
    "hug_ansim_jeonse": "전세-안심전세",
    "jeonse_victim_support": "전세-피해지원",
    "welfare_address_change": "행정-복지",
    "resident_id_reissue": "행정-주민등록",
    "foreigner_registration": "행정-외국인등록",
    "legal_aid_132": "분쟁-법률구조",
    "moj_standard_contract": "계약서",
    "lease_dispute_committee": "분쟁-임대차조정",
    "seoul_realty_check": "전세-시세확인",
    "building_ledger": "행정-건축물대장",
    "kepco_electricity": "공과금-전기",
    "water_region_office": "공과금-수도",
    "telecom_internet": "통신사 이전",
    "gas_region_company": "공과금-가스",
    "hug_default_list": "전세-피해지원",
    "school_transfer": "자녀 전학",
    "gov24_services": "행정-정부24",
    "moveout_timeline": "퇴거-타임라인",
    "moveout_deposit_return": "퇴거-보증금반환",
    "moveout_restoration": "퇴거-원상회복",
    "moveout_waste_disposal": "퇴거-폐기물",
    "moveout_management_refund": "퇴거-관리비정산",
    "moveout_termination_notice": "퇴거-계약해지",
}

# 광역 시도 → 축약 aliases (검색 쿼리 매칭용)
REGION_ALIASES: dict[str, list[str]] = {
    "서울특별시": ["서울", "서울시"],
    "부산광역시": ["부산", "부산시"],
    "대구광역시": ["대구", "대구시"],
    "인천광역시": ["인천", "인천시"],
    "광주광역시": ["광주", "광주시"],
    "대전광역시": ["대전", "대전시"],
    "울산광역시": ["울산", "울산시"],
    "세종특별자치시": ["세종", "세종시"],
    "경기도": ["경기"],
    "강원특별자치도": ["강원", "강원도"],
    "충청북도": ["충북", "충청북도"],
    "충청남도": ["충남", "충청남도"],
    "전북특별자치도": ["전북", "전라북도"],
    "전라남도": ["전남", "전라남도"],
    "경상북도": ["경북", "경상북도"],
    "경상남도": ["경남", "경상남도"],
    "제주특별자치도": ["제주", "제주도"],
    "전국": [],
}

# 광역 시도 → ASCII slug (Azure document key 호환)
REGION_SLUG: dict[str, str] = {
    "서울특별시": "seoul", "부산광역시": "busan", "대구광역시": "daegu",
    "인천광역시": "incheon", "광주광역시": "gwangju", "대전광역시": "daejeon",
    "울산광역시": "ulsan", "세종특별자치시": "sejong",
    "경기도": "gyeonggi", "강원특별자치도": "gangwon",
    "충청북도": "chungbuk", "충청남도": "chungnam",
    "전북특별자치도": "jeonbuk", "전라남도": "jeonnam",
    "경상북도": "gyeongbuk", "경상남도": "gyeongnam",
    "제주특별자치도": "jeju", "전국": "all",
}

# 학교급 → ASCII slug
LEVEL_SLUG: dict[str, str] = {
    "초등학교": "primary", "중학교": "middle", "고등학교": "high",
}


# ============================================================
# 공통 유틸
# ============================================================

def slugify(s: str) -> str:
    """Azure Search document key 호환 ASCII-safe slug.

    허용 문자: letters, digits, underscore, dash, equal sign.
    매핑 테이블에 있으면 그대로 사용, 없으면 ASCII 추출, 그것도 없으면 md5 해시.
    """
    if not s:
        return ""
    if s in REGION_SLUG:
        return REGION_SLUG[s]
    if s in LEVEL_SLUG:
        return LEVEL_SLUG[s]
    # ASCII + 허용 특수문자만 추출
    ascii_only = re.sub(r"[^a-zA-Z0-9_-]", "", s)
    if ascii_only:
        return ascii_only[:20]
    # 한글만으로 구성된 경우 → md5 8자리 해시 (고유성 보장)
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:8]


def make_id(source_id: str, suffix: str | None = None) -> str:
    """ASCII-safe 청크 ID 생성."""
    base = f"map-{source_id}"
    if suffix:
        return f"{base}-{slugify(suffix)}"
    return base


def extract_deadline_days(raw: dict) -> int | None:
    """top-level deadline_days 또는 텍스트에서 '14일 이내' 추출."""
    if "deadline_days" in raw and isinstance(raw["deadline_days"], int):
        return raw["deadline_days"]
    text_fields = []
    for k in ("process", "tip", "note", "importance", "common_tip"):
        v = raw.get(k)
        if isinstance(v, str):
            text_fields.append(v)
        elif isinstance(v, list):
            text_fields.extend(str(x) for x in v)
    combined = " ".join(text_fields)
    m = re.search(r"(\d+)\s*일\s*이내", combined)
    if m:
        return int(m.group(1))
    return None


def extract_penalty_text(raw: dict) -> str | None:
    """top-level penalty 또는 텍스트에서 과태료 문구 추출."""
    if "penalty" in raw and isinstance(raw["penalty"], str):
        return raw["penalty"]
    text_fields = []
    for k in ("note", "importance", "tip"):
        v = raw.get(k)
        if isinstance(v, str):
            text_fields.append(v)
    combined = " ".join(text_fields)
    m = re.search(r"(\d+\s*만원[^.]*과태료)", combined)
    if m:
        return m.group(1).strip()
    return None


def get_region_aliases(region: str) -> list[str]:
    """광역 시도 이름 → 축약 aliases."""
    return REGION_ALIASES.get(region, [])


def listify(v: Any) -> list[str]:
    """값을 Collection(Edm.String) 으로 변환."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v else []
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return [str(v)]


def make_chunk(
    chunk_id: str,
    source_id: str,
    title: str,
    content: str,
    authority: str,
    region: str,
    phones: list[str],
    websites: list[str],
    process_steps: list[str],
    deadline_days: int | None = None,
    penalty_text: str | None = None,
    legal_basis: list[str] | None = None,
    tips: list[str] | None = None,
) -> dict:
    """공통 청크 dict 생성 — Azure mapping-index 스키마 1:1 대응."""
    return {
        "id": chunk_id,
        "source_id": source_id,
        "title": title,
        "content": content,
        "authority": authority,
        "region": region,
        "region_aliases": get_region_aliases(region),
        "service_category": SERVICE_CATEGORY.get(source_id, "기타"),
        "phones": phones,
        "websites": websites,
        "process_steps": process_steps,
        "deadline_days": deadline_days,
        "penalty_text": penalty_text,
        "legal_basis": legal_basis or [],
        "tips": tips or [],
        "fetched_at": TODAY,
    }


# ============================================================
# Pattern A: Simple service handler
# ============================================================

def handle_simple(raw: dict, source_id: str) -> list[dict]:
    """평평한 service 문서 → 1 청크."""
    service = raw.get("service") or raw.get("title") or source_id
    authority = raw.get("authority", "")
    website = raw.get("website", "")
    call = raw.get("call") or raw.get("common_call") or raw.get("short_call")
    call_label = raw.get("call_label") or raw.get("common_call_label")

    phones: list[str] = []
    if call and call_label:
        phones.append(f"{call_label} ({call})")
    elif call:
        phones.append(str(call))

    websites: list[str] = []
    if website:
        websites.append(str(website))
    for key in ("online_url", "guide_url"):
        v = raw.get(key)
        if isinstance(v, str) and v:
            websites.append(v)
        elif isinstance(v, dict) and v.get("url"):
            websites.append(v["url"])

    process_steps = listify(raw.get("process"))
    tips = []
    for key in ("tip", "note", "importance", "advantage", "caveat"):
        v = raw.get(key)
        if isinstance(v, str) and v:
            tips.append(v)
    legal_basis = listify(raw.get("legal_basis"))

    content_parts = [f"{service}. 담당 기관: {authority}."]
    if phones:
        content_parts.append(f"연락처: {', '.join(phones)}.")
    if websites:
        content_parts.append(f"웹사이트: {websites[0]}.")
    if process_steps:
        content_parts.append("절차: " + " → ".join(process_steps[:5]))
    deadline_days = extract_deadline_days(raw)
    if deadline_days:
        content_parts.append(f"기한: {deadline_days}일 이내.")
    penalty = extract_penalty_text(raw)
    if penalty:
        content_parts.append(f"미이행 시: {penalty}.")
    if legal_basis:
        content_parts.append(f"법적 근거: {', '.join(legal_basis[:2])}.")
    if tips:
        content_parts.append(f"유의사항: {tips[0][:200]}")
    content = " ".join(content_parts)

    chunk = make_chunk(
        chunk_id=make_id(source_id),
        source_id=source_id,
        title=service,
        content=content,
        authority=authority,
        region="전국",
        phones=phones,
        websites=websites,
        process_steps=process_steps,
        deadline_days=deadline_days,
        penalty_text=penalty,
        legal_basis=legal_basis,
        tips=tips,
    )
    return [chunk]


# ============================================================
# Pattern B: Regional breakdown handler
# ============================================================

def handle_regional(raw: dict, source_id: str) -> list[dict]:
    """본체 1청크 + 지역별 청크 N개."""
    chunks: list[dict] = []
    service = raw.get("service") or raw.get("title") or source_id
    authority = raw.get("authority", "")
    website = raw.get("website", "")

    base_chunk = handle_simple(raw, source_id)[0]
    chunks.append(base_chunk)

    regional_list = raw.get("regional_centers") or raw.get("offices") or []
    for idx, rc in enumerate(regional_list):
        name = rc.get("name") or rc.get("office_name", f"지역{idx}")
        phone = rc.get("phone", "")
        regions = rc.get("region") or ([rc.get("sido")] if rc.get("sido") else [])
        region_list = listify(regions)

        for region in region_list:
            if not region:
                continue
            chunk_id = make_id(source_id, region)

            phones = [f"{name} ({phone})"] if phone else []
            title = f"{service} — {region} ({name})"

            content_parts = [
                f"{service} 서비스. {region} 담당: {name}.",
                f"전화: {phone}." if phone else "",
            ]
            sub_offices = rc.get("sub_offices", [])
            if sub_offices:
                sub_summary = ", ".join(
                    f"{so['name']} ({so['phone']})"
                    for so in sub_offices[:5]
                    if so.get("name") and so.get("phone")
                )
                if sub_summary:
                    content_parts.append(f"산하 사업소: {sub_summary}")
            note = rc.get("note")
            if note:
                content_parts.append(note)
            content = " ".join(p for p in content_parts if p)

            for so in sub_offices:
                if so.get("name") and so.get("phone"):
                    phones.append(f"{so['name']} ({so['phone']})")

            chunk = make_chunk(
                chunk_id=chunk_id,
                source_id=source_id,
                title=title,
                content=content,
                authority=authority,
                region=region,
                phones=phones,
                websites=[website] if website else [],
                process_steps=listify(raw.get("process"))[:3],
                tips=[rc.get("note")] if rc.get("note") else [],
            )
            chunks.append(chunk)

    return chunks


# ============================================================
# Pattern C: Multi-provider handler (telecom_internet)
# ============================================================

def handle_multi_provider(raw: dict, source_id: str) -> list[dict]:
    """공통 1청크 + providers 각 1 청크."""
    chunks: list[dict] = []
    service = raw.get("service", source_id)

    common_chunk = make_chunk(
        chunk_id=make_id(source_id),
        source_id=source_id,
        title=service,
        content=(
            f"{service}. 주요 통신사 3사(KT/SKB/LGU+). "
            + (raw.get("common_tip", ""))
        ),
        authority="KT, SK브로드밴드, LG U+",
        region="전국",
        phones=[],
        websites=[],
        process_steps=[],
        tips=[raw.get("common_tip")] if raw.get("common_tip") else [],
    )
    chunks.append(common_chunk)

    for p in raw.get("providers", []):
        name = p.get("name", "")
        short_call = p.get("short_call", "")
        call_label = p.get("call_label", "")
        website = p.get("website", "")
        move_url = p.get("move_url", "")

        phones = [f"{call_label} ({short_call})"] if short_call else []
        websites = [u for u in (website, move_url) if u]
        process_steps = listify(p.get("process"))

        content_parts = [
            f"{name} 인터넷·TV 이전 설치 서비스.",
            f"연락처: {phones[0]}." if phones else "",
            f"온라인: {move_url}." if move_url else "",
            f"앱: {p.get('app', '')}." if p.get("app") else "",
        ]
        if process_steps:
            content_parts.append("절차: " + " → ".join(process_steps))
        if p.get("lead_time_days"):
            content_parts.append(f"권장 예약: {p['lead_time_days']}일 전.")
        if p.get("fee_note"):
            content_parts.append(p["fee_note"])
        if p.get("tip"):
            content_parts.append(p["tip"])
        content = " ".join(x for x in content_parts if x)

        chunk = make_chunk(
            chunk_id=make_id(source_id, name),
            source_id=source_id,
            title=f"{service} — {name}",
            content=content,
            authority=name,
            region="전국",
            phones=phones,
            websites=websites,
            process_steps=process_steps,
            tips=[p.get("tip")] if p.get("tip") else [],
        )
        chunks.append(chunk)

    return chunks


# ============================================================
# Pattern D: Pure mapping table (gas_region_company, hug_default_list)
# ============================================================

def handle_mapping_table(raw: dict, source_id: str) -> list[dict]:
    """entries 를 region 단위로 group by → 광역 청크."""
    chunks: list[dict] = []
    meta = raw.get("_source_metadata", {})
    service = meta.get("category") or source_id
    authority = meta.get("authority", "")
    source_url = meta.get("source_url", "")

    entries = raw.get("entries", [])
    if not entries:
        return [make_chunk(
            chunk_id=make_id(source_id),
            source_id=source_id,
            title=service,
            content=f"{service}. 상세 정보는 {source_url} 에서 확인.",
            authority=authority,
            region="전국",
            phones=[],
            websites=[source_url] if source_url else [],
            process_steps=[],
        )]

    by_region: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        region = e.get("region", "전국")
        by_region[region].append(e)

    common_content = f"{service}. 전국 {len(entries)}개 공급사 매핑 데이터."
    chunks.append(make_chunk(
        chunk_id=make_id(source_id),
        source_id=source_id,
        title=service,
        content=common_content,
        authority=authority,
        region="전국",
        phones=[],
        websites=[source_url] if source_url else [],
        process_steps=[],
    ))

    for region, items in by_region.items():
        companies = [e.get("company") or e.get("name", "") for e in items]
        companies = [c for c in companies if c]
        content = (
            f"{region} 지역 {service}. "
            f"공급사 {len(companies)}개: {', '.join(companies)}."
        )
        chunks.append(make_chunk(
            chunk_id=make_id(source_id, region),
            source_id=source_id,
            title=f"{service} — {region}",
            content=content,
            authority=authority,
            region=region if region in REGION_ALIASES else "전국",
            phones=[],
            websites=[source_url] if source_url else [],
            process_steps=[],
        ))

    return chunks


# ============================================================
# Pattern E: Multi-level service (school_transfer)
# ============================================================

def handle_multi_level(raw: dict, source_id: str) -> list[dict]:
    """공통 + levels 3 + sido_education_offices 17."""
    chunks: list[dict] = []
    service = raw.get("service", "자녀 전학")
    authority = raw.get("authority", "교육부")
    website = raw.get("website", "")
    call = raw.get("call", "")
    call_label = raw.get("call_label", "")
    legal_basis = listify(raw.get("legal_basis"))

    common_phones = [f"{call_label} ({call})"] if call else []
    common_chunk = make_chunk(
        chunk_id=make_id(source_id),
        source_id=source_id,
        title=service,
        content=f"{service}. 담당: {authority}. 초·중·고 전학 절차 안내.",
        authority=authority,
        region="전국",
        phones=common_phones,
        websites=[website] if website else [],
        process_steps=[],
        legal_basis=legal_basis,
    )
    chunks.append(common_chunk)

    # 학교급별 청크 3개
    for lv in raw.get("levels", []):
        level_name = lv.get("level", "")
        process = listify(lv.get("process"))
        docs = listify(lv.get("required_docs"))
        note = lv.get("note", "")
        content = (
            f"{level_name} 전학 절차. "
            + ("준비물: " + ", ".join(docs) + ". " if docs else "")
            + ("절차: " + " → ".join(process) + ". " if process else "")
            + note
        )
        chunks.append(make_chunk(
            chunk_id=make_id(source_id, f"level-{slugify(level_name)}"),
            source_id=source_id,
            title=f"{service} — {level_name}",
            content=content,
            authority=authority,
            region="전국",
            phones=common_phones,
            websites=[website] if website else [],
            process_steps=process,
            legal_basis=legal_basis,
            tips=[note] if note else [],
        ))

    # 시도 교육청 청크 17개
    for office in raw.get("sido_education_offices", []):
        sido = office.get("sido", "")
        name = office.get("name", "")
        phone = office.get("phone", "")
        ow = office.get("website", "")
        content = f"{sido} 자녀 전학 담당: {name}. 전화 {phone}. 웹사이트 {ow}."
        chunks.append(make_chunk(
            chunk_id=make_id(source_id, f"office-{slugify(sido)}"),
            source_id=source_id,
            title=f"{name} (자녀 전학)",
            content=content,
            authority=name,
            region=sido if sido in REGION_ALIASES else "전국",
            phones=[f"{name} ({phone})"] if phone else [],
            websites=[ow] if ow else [],
            process_steps=[],
        ))

    return chunks


# ============================================================
# Pattern F: Categorized sub-services (gov24_services)
# ============================================================

def handle_categorized_sub(raw: dict, source_id: str) -> list[dict]:
    """공통 1 + services[] 각 1 청크."""
    chunks: list[dict] = []
    service = raw.get("service", "정부24 민원")
    authority = raw.get("authority", "")
    main_url = raw.get("main_url", "")
    call = raw.get("call", "")
    call_label = raw.get("call_label", "")

    common_phones = [f"{call_label} ({call})"] if call else []

    chunks.append(make_chunk(
        chunk_id=make_id(source_id),
        source_id=source_id,
        title=service,
        content=(
            f"{service}. 담당: {authority}. "
            f"주요 민원: "
            + ", ".join(s.get("name", "") for s in raw.get("services", []))
        ),
        authority=authority,
        region="전국",
        phones=common_phones,
        websites=[main_url] if main_url else [],
        process_steps=[],
    ))

    for idx, s in enumerate(raw.get("services", [])):
        name = s.get("name", "")
        url = s.get("url", "")
        deep = s.get("deep_link", "")
        auth = s.get("authentication", "")
        fee = s.get("fee", "")
        ddays = s.get("deadline_days")
        penalty = s.get("penalty", "")
        note = s.get("note", "")
        legal = s.get("legal_basis", "")

        content_parts = [
            f"{name} (정부24). 담당: {authority}.",
            f"URL: {url}." if url else "",
            f"인증: {auth}." if auth else "",
            f"수수료: {fee}." if fee else "",
            f"기한: {ddays}일 이내." if ddays else "",
            f"미이행: {penalty}." if penalty else "",
            f"법적 근거: {legal}." if legal else "",
            note,
        ]
        content = " ".join(x for x in content_parts if x)

        # service 이름이 순한글일 가능성 높음 → md5 해시 방지용으로 index 병기
        suffix = f"svc{idx:02d}-{slugify(name)}"
        websites_list = [u for u in (url, deep) if u]
        chunks.append(make_chunk(
            chunk_id=make_id(source_id, suffix),
            source_id=source_id,
            title=f"정부24 — {name}",
            content=content,
            authority=authority,
            region="전국",
            phones=common_phones,
            websites=websites_list,
            process_steps=[],
            deadline_days=ddays if isinstance(ddays, int) else None,
            penalty_text=penalty if penalty else None,
            legal_basis=[legal] if legal else [],
            tips=[note] if note else [],
        ))

    return chunks


# ============================================================
# Pattern G: Structured guide handlers
# ============================================================

def handle_guide_phases(raw: dict, source_id: str) -> list[dict]:
    """moveout_timeline: phases[] → phase 단위 청크 (D-60 ~ D+7)."""
    chunks: list[dict] = []
    title = raw.get("title", "퇴거 타임라인")
    authority = raw.get("authority", "")
    description = raw.get("description", "")

    chunks.append(make_chunk(
        chunk_id=make_id(source_id),
        source_id=source_id,
        title=title,
        content=f"{title}. {description}",
        authority=authority,
        region="전국",
        phones=[],
        websites=[],
        process_steps=[],
    ))

    for phase in raw.get("phases", []):
        d_day = phase.get("d_day")
        label = phase.get("label", f"D{d_day}")
        tasks = phase.get("tasks", [])
        task_summary_parts = []
        all_legal = []
        for t in tasks:
            task_summary_parts.append(
                f"[{t.get('category', '')}] {t.get('title', '')}: {t.get('description', '')}"
            )
            if t.get("legal_basis"):
                all_legal.append(t["legal_basis"])
        content = f"{label} 해야 할 일. " + " / ".join(task_summary_parts[:5])
        d_day_str = str(d_day).replace("-", "minus").replace("+", "plus")
        phase_slug = f"dday{d_day_str}"
        chunks.append(make_chunk(
            chunk_id=make_id(source_id, phase_slug),
            source_id=source_id,
            title=f"{title} — {label}",
            content=content,
            authority=authority,
            region="전국",
            phones=[],
            websites=[],
            process_steps=[t.get("title", "") for t in tasks if t.get("title")],
            legal_basis=all_legal,
            tips=[t.get("tip") for t in tasks if t.get("tip")],
        ))

    return chunks


def handle_guide_stages(raw: dict, source_id: str) -> list[dict]:
    """moveout_deposit_return: stages[] → stage 단위 청크 (5개)."""
    chunks: list[dict] = []
    title = raw.get("title", "보증금 반환 분쟁")
    authority = raw.get("authority", "")
    legal_basis_list = [
        f"{l.get('law', '')} {l.get('article', '')}"
        for l in raw.get("legal_basis", [])
    ]

    chunks.append(make_chunk(
        chunk_id=make_id(source_id),
        source_id=source_id,
        title=title,
        content=f"{title}. 5단계 대응 가이드. 담당: {authority}.",
        authority=authority,
        region="전국",
        phones=[],
        websites=[],
        process_steps=[],
        legal_basis=legal_basis_list,
        tips=listify(raw.get("prevention_tips")),
    ))

    for stage in raw.get("stages", []):
        stage_num = stage.get("stage", 0)
        stage_title = stage.get("title", f"{stage_num}단계")
        timing = stage.get("timing", "")
        action = stage.get("action", "")
        cost = stage.get("cost", "")
        ptime = stage.get("processing_time", "")
        legal = stage.get("legal_basis", "")
        referral = stage.get("referral", "")
        template = stage.get("template", "")

        content_parts = [
            stage_title,
            f"시기: {timing}." if timing else "",
            f"대응: {action}" if action else "",
            f"비용: {cost}." if cost else "",
            f"소요시간: {ptime}." if ptime else "",
            f"참고: {referral}." if referral else "",
        ]
        if template:
            content_parts.append(f"템플릿: {template[:300]}")
        content = " ".join(x for x in content_parts if x)

        chunks.append(make_chunk(
            chunk_id=make_id(source_id, f"stage-{stage_num}"),
            source_id=source_id,
            title=stage_title,
            content=content,
            authority=authority,
            region="전국",
            phones=[],
            websites=[],
            process_steps=[action] if action else [],
            legal_basis=[legal] if legal else legal_basis_list,
        ))

    return chunks


def handle_guide_generic(raw: dict, source_id: str) -> list[dict]:
    """범용 가이드. 문서 전체를 1 청크로 요약."""
    chunks: list[dict] = []
    title = raw.get("title", source_id)
    authority = raw.get("authority", "")

    content_parts = [title]
    for key in ("description", "authority", "common_process", "common_fee_range_krw",
                "importance", "tip", "note", "purpose"):
        v = raw.get(key)
        if isinstance(v, str) and v:
            content_parts.append(v)
        elif isinstance(v, list):
            content_parts.append(" / ".join(str(x) for x in v if x))

    if "major_cities" in raw:
        for c in raw["major_cities"]:
            content_parts.append(
                f"{c.get('name', '')}: {c.get('url', '')} {c.get('note', '')}"
            )
    if "fee_examples" in raw:
        examples = ", ".join(
            f"{e.get('item')} {e.get('fee_krw')}원"
            for e in raw["fee_examples"][:5]
        )
        content_parts.append(f"예시 요금: {examples}")
    if "free_pickup_service" in raw:
        fp = raw["free_pickup_service"]
        content_parts.append(
            f"무상 수거: {fp.get('name', '')} ({fp.get('call', '')})"
        )

    legal_basis = []
    if isinstance(raw.get("legal_basis"), str):
        legal_basis.append(raw["legal_basis"])
    elif isinstance(raw.get("legal_basis"), list):
        for l in raw["legal_basis"]:
            if isinstance(l, str):
                legal_basis.append(l)
            elif isinstance(l, dict):
                legal_basis.append(f"{l.get('law', '')} {l.get('article', '')}")

    content = " ".join(str(x) for x in content_parts if x)[:2000]

    phones = []
    if "free_pickup_service" in raw:
        fp = raw["free_pickup_service"]
        if fp.get("call"):
            phones.append(f"{fp.get('name', '')} ({fp['call']})")

    chunks.append(make_chunk(
        chunk_id=make_id(source_id),
        source_id=source_id,
        title=title,
        content=content,
        authority=authority,
        region="전국",
        phones=phones,
        websites=[],
        process_steps=listify(raw.get("common_process")),
        legal_basis=legal_basis,
        tips=[raw.get("tip")] if raw.get("tip") else [],
    ))

    return chunks


# ============================================================
# Handler 등록
# ============================================================

HANDLERS = {
    "simple": handle_simple,
    "regional": handle_regional,
    "multi_provider": handle_multi_provider,
    "mapping_table": handle_mapping_table,
    "multi_level": handle_multi_level,
    "categorized_sub": handle_categorized_sub,
    "guide_phases": handle_guide_phases,
    "guide_stages": handle_guide_stages,
    "guide_generic": handle_guide_generic,
}


# ============================================================
# Main
# ============================================================

def main() -> None:
    if not IN_DIR.exists():
        print(f"❌ 입력 디렉토리 없음: {IN_DIR}")
        return

    all_chunks: list[dict] = []
    per_file_counts: dict[str, int] = {}
    per_pattern_counts: dict[str, int] = defaultdict(int)
    missing_files: list[str] = []
    errors: list[tuple[str, str]] = []

    for file_name, pattern in FILE_PATTERN.items():
        file_path = IN_DIR / file_name
        if not file_path.exists():
            missing_files.append(file_name)
            continue

        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            source_id = file_name.replace(".json", "")
            handler = HANDLERS[pattern]
            chunks = handler(raw, source_id)
            all_chunks.extend(chunks)
            per_file_counts[file_name] = len(chunks)
            per_pattern_counts[pattern] += len(chunks)
            print(f"  ✓ {file_name:45s} [{pattern:20s}] → {len(chunks)} chunks")
        except Exception as exc:
            errors.append((file_name, f"{type(exc).__name__}: {exc}"))
            print(f"  ✗ {file_name}: {exc}")

    # id 중복 검증
    id_counts: dict[str, int] = defaultdict(int)
    for c in all_chunks:
        id_counts[c["id"]] += 1
    dup_ids = {k: v for k, v in id_counts.items() if v > 1}

    # ASCII 검증
    non_ascii_ids = [c["id"] for c in all_chunks if any(ord(ch) > 127 for ch in c["id"])]

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    summary = {
        "generated_at": TODAY,
        "total_chunks": len(all_chunks),
        "total_files_processed": len(per_file_counts),
        "missing_files": missing_files,
        "errors": errors,
        "duplicate_ids": dup_ids,
        "non_ascii_ids": non_ascii_ids,
        "per_pattern_counts": dict(per_pattern_counts),
        "per_file_counts": per_file_counts,
    }
    OUT_SUMMARY.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 60)
    print(f"✅ {len(all_chunks)} chunks → {OUT_JSONL.relative_to(ROOT)}")
    print(f"📊 summary → {OUT_SUMMARY.relative_to(ROOT)}")
    print(f"📁 패턴별: {dict(per_pattern_counts)}")
    if missing_files:
        print(f"⚠️  누락 파일 {len(missing_files)}개: {missing_files}")
    if dup_ids:
        print(f"❌ 중복 ID {len(dup_ids)}개: {dup_ids}")
    if non_ascii_ids:
        print(f"❌ 비-ASCII ID {len(non_ascii_ids)}개: {non_ascii_ids[:5]}")
    if errors:
        print(f"❌ 에러 {len(errors)}건:")
        for fn, err in errors:
            print(f"    {fn}: {err}")


if __name__ == "__main__":
    main()