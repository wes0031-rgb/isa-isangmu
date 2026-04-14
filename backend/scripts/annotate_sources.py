"""모든 데이터 파일에 출처 메타데이터 주입 + 카탈로그 문서 생성.

팀원이 각 파일의 출처·갱신 주기·라이선스를 바로 확인할 수 있도록
`_source_metadata` 필드를 일괄 추가하고, `DATA_SOURCES.md` 카탈로그를 생성.

Usage:
  python3 backend/scripts/annotate_sources.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "backend" / "data"
TODAY = date.today().isoformat()


# ============================================================
# 출처 카탈로그 — 파일명 패턴별 메타데이터
# ============================================================

SOURCES: list[dict] = [
    # ----- Index A (법률 원본) -----
    {
        "pattern": "laws/*.json",
        "category": "법률 원본",
        "authority": "법제처",
        "source_url": "https://www.law.go.kr/DRF/lawService.do",
        "api_name": "국가법령정보 Open API (DRF)",
        "license": "공공누리 제1유형 (출처 표시)",
        "update_cycle": "시행일 기준 즉시 반영",
        "how_collected": "backend/scripts/ingest_laws.py (LAW_OC 인증키)",
        "raw_count_note": "8개 법령 · 1,950 조문",
    },
    # ----- Index A (법률 청크) -----
    {
        "pattern": "indexes/index_a_chunks.jsonl",
        "category": "법률 청크 (RAG Index A)",
        "authority": "법제처",
        "source_url": "https://www.law.go.kr/DRF/lawService.do",
        "api_name": "국가법령정보 Open API",
        "license": "공공누리 제1유형",
        "update_cycle": "법령 개정 시",
        "how_collected": "ingest_laws.py 로 조문별 청크화, 한자 병기 제거",
        "chunks": 1950,
    },
    # ----- Index B (행정 절차 청크) -----
    {
        "pattern": "indexes/index_b_chunks*.jsonl",
        "category": "행정 절차 청크 (RAG Index B)",
        "authority": "법제처",
        "source_url": "https://easylaw.go.kr",
        "api_name": "찾기쉬운 생활법령정보",
        "license": "공공누리 제1유형",
        "update_cycle": "연 1회 이상",
        "how_collected": "ingest_easylaw.py + chunk_easylaw.py + curate_chunks.py",
        "chunks": 200,
    },
    # ----- Index C (유튜브 자막) -----
    {
        "pattern": "indexes/index_c_youtube_chunks.jsonl",
        "category": "유튜브 자막 청크 (RAG Index C, 챗봇용)",
        "authority": "각 유튜브 채널 (영상별 귀속)",
        "source_url": "https://www.youtube.com",
        "api_name": "youtube-transcript-api (무료, 공식/자동 자막) + oEmbed",
        "license": "영상별 채널 귀속 — 프로젝트 내부용만, 외부 공개 금지",
        "update_cycle": "수동 (영상 URL 추가 시)",
        "how_collected": "ingest_youtube.py (12 영상 · 147 청크)",
        "channels": [
            "국토교통부 (공식)",
            "아정당",
            "집 나와라 뚝딱!",
            "이사하우",
            "정희숙의 똑똑한 정리",
            "화물인운송",
            "욜로이사",
        ],
    },
    # ----- 행정 절차 easylaw raw -----
    {
        "pattern": "procedures/easylaw/*.json",
        "category": "행정 절차 원본 스크랩",
        "authority": "법제처 (찾기쉬운 생활법령정보)",
        "source_url": "https://easylaw.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_easylaw.py (이사 + 주택임대차 카테고리, 53 문서)",
    },
    # ----- 공휴일 -----
    {
        "pattern": "raw/holidays_2026.json",
        "category": "공휴일",
        "authority": "한국천문연구원",
        "source_url": "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService",
        "api_name": "특일정보 API",
        "license": "공공누리 제1유형",
        "update_cycle": "연 1회 (연말)",
        "how_collected": "ingest_holidays.py (2026년 22건)",
    },
    # ----- 유튜브 raw -----
    {
        "pattern": "raw/youtube_transcripts/*.json",
        "category": "유튜브 자막 원본",
        "authority": "각 채널 귀속",
        "source_url": "https://www.youtube.com",
        "api_name": "youtube-transcript-api (무료)",
        "license": "영상별 채널 저작권. 프로젝트 내부용 가공만 허용",
        "update_cycle": "수동",
        "how_collected": "ingest_youtube.py",
    },
    # ----- 매핑: 도시가스 -----
    {
        "pattern": "mapping/gas_region_company.json",
        "category": "도시가스 지역별 공급사",
        "authority": "한국도시가스협회",
        "source_url": "http://www.citygas.or.kr/company/situation.jsp",
        "license": "공개 페이지 기반 재가공",
        "update_cycle": "연 1회",
        "how_collected": "ingest_citygas.py (34 회사 · 전국)",
    },
    # ----- 매핑: 수도 -----
    {
        "pattern": "mapping/water_region_office.json",
        "category": "전국 수도사업소",
        "authority": "각 지자체 상수도사업본부",
        "source_url": "각 지자체 공식 홈페이지",
        "license": "공공누리 제1유형 (공개 정보)",
        "update_cycle": "수동 (6개월~1년)",
        "how_collected": "ingest_water.py (17 광역 · 63 산하 사업소)",
    },
    # ----- 매핑: 공과금·행정 서비스 8종 (ingest_services.py) -----
    {
        "pattern": "mapping/kepco_electricity.json",
        "category": "전기 (한전)",
        "authority": "한국전력공사 (KEPCO)",
        "source_url": "https://www.kepco.co.kr, https://cyber.kepco.co.kr",
        "license": "공개 페이지",
        "update_cycle": "수동",
        "how_collected": "ingest_services.py (123 + 13 지역본부)",
    },
    {
        "pattern": "mapping/telecom_internet.json",
        "category": "인터넷·TV 통신 3사",
        "authority": "KT, SK브로드밴드, LG U+",
        "source_url": "각 사 공식 홈페이지",
        "license": "공개 페이지",
        "update_cycle": "수동",
        "how_collected": "ingest_services.py",
    },
    {
        "pattern": "mapping/post_office_mail_forwarding.json",
        "category": "우편물 주소이전 서비스",
        "authority": "우정사업본부",
        "source_url": "https://service.epost.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services.py",
    },
    {
        "pattern": "mapping/gov24_services.json",
        "category": "정부24 주요 민원",
        "authority": "행정안전부",
        "source_url": "https://www.gov.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services.py",
    },
    {
        "pattern": "mapping/animal_registration.json",
        "category": "반려동물 등록 주소변경",
        "authority": "농림축산검역본부 · 동물보호관리시스템",
        "source_url": "https://www.animal.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services.py",
    },
    {
        "pattern": "mapping/car_registration.json",
        "category": "자동차 변경등록",
        "authority": "국토교통부 · 시·도청",
        "source_url": "https://www.gov.kr, 각 시·도청",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services.py",
    },
    {
        "pattern": "mapping/school_transfer.json",
        "category": "자녀 전학",
        "authority": "교육부 · 시·도 교육청",
        "source_url": "https://www.moe.go.kr + 각 교육청",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services.py (17 교육청)",
    },
    {
        "pattern": "mapping/foreigner_registration.json",
        "category": "외국인 주소변경",
        "authority": "법무부 출입국·외국인청",
        "source_url": "https://www.hikorea.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services.py",
    },
    # ----- 매핑: SafeContract 강화 5종 (ingest_services_v2.py) -----
    {
        "pattern": "mapping/hug_*.json",
        "category": "HUG 안심전세 / 임대인 공개",
        "authority": "주택도시보증공사 (HUG)",
        "source_url": "https://www.khug.or.kr, https://jeonse.khug.or.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/iros_registry.json",
        "category": "대법원 인터넷등기소",
        "authority": "대법원 / 법원행정처",
        "source_url": "https://www.iros.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/lease_dispute_committee.json",
        "category": "주택임대차분쟁조정위원회",
        "authority": "법무부 / 대한법률구조공단",
        "source_url": "https://www.hldcc.or.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/jeonse_victim_support.json",
        "category": "전세피해지원센터",
        "authority": "국토교통부",
        "source_url": "https://jeonse119.molit.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/legal_aid_132.json",
        "category": "대한법률구조공단 132",
        "authority": "법무부 산하 공공기관",
        "source_url": "https://www.klac.or.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/moj_standard_contract.json",
        "category": "법무부 표준 임대차계약서",
        "authority": "법무부 / 국토교통부",
        "source_url": "https://www.moj.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/seoul_realty_check.json",
        "category": "서울시 전월세 정보몽땅",
        "authority": "서울특별시",
        "source_url": "https://rent.seoul.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    # ----- 매핑: 행정기관 5종 -----
    {
        "pattern": "mapping/nhis_health_insurance.json",
        "category": "국민건강보험공단",
        "authority": "국민건강보험공단",
        "source_url": "https://www.nhis.or.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/nps_national_pension.json",
        "category": "국민연금공단",
        "authority": "국민연금공단",
        "source_url": "https://www.nps.or.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/hometax_nts.json",
        "category": "국세청 홈택스 주소변경",
        "authority": "국세청",
        "source_url": "https://hometax.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/mma_military.json",
        "category": "병무청 주소변경",
        "authority": "병무청",
        "source_url": "https://www.mma.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/kftc_accounts.json",
        "category": "금융결제원 내계좌한눈에",
        "authority": "금융결제원 (KFTC)",
        "source_url": "https://www.payinfo.or.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_services_v2.py",
    },
    {
        "pattern": "mapping/building_ledger.json",
        "category": "건축물대장 발급",
        "authority": "국토교통부 · 행정안전부",
        "source_url": "https://cloud.eais.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "이사이상무 팀 편집본 (정부24 + 세움터 기반)",
    },
    {
        "pattern": "mapping/resident_id_reissue.json",
        "category": "주민등록증 재발급",
        "authority": "행정안전부",
        "source_url": "https://www.gov.kr/portal/rcvfvrSvc/dtlEx/13100000023",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "이사이상무 팀 편집본 (정부24 공식 안내)",
    },
    {
        "pattern": "mapping/welfare_address_change.json",
        "category": "복지급여 주소변경",
        "authority": "보건복지부",
        "source_url": "https://www.bokjiro.go.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "이사이상무 팀 편집본 (복지로 + 국민기초생활보장법)",
    },
    # ----- 매핑: 퇴거 6종 -----
    {
        "pattern": "mapping/moveout_timeline.json",
        "category": "퇴거 타임라인 체크리스트",
        "authority": "이사이상무 팀 편집본",
        "source_url": "기반: 주택임대차보호법 + 공정위 분쟁해결기준 + 실무 사례",
        "license": "원본 법률·가이드는 공공누리, 편집본은 프로젝트 소유",
        "update_cycle": "수동",
        "how_collected": "ingest_moveout.py (D-60~D+7)",
        "references": [
            "주택임대차보호법 제3조의2/3, 제4조, 제6조~제6조의3",
            "공정거래위원회 소비자분쟁해결기준 2025 (주거생활)",
            "한국소비자원 주거 가이드",
        ],
    },
    {
        "pattern": "mapping/moveout_deposit_return.json",
        "category": "보증금 반환 분쟁 5단계 가이드",
        "authority": "법무부 · 주택임대차분쟁조정위원회 · 대한법률구조공단 참고",
        "source_url": "https://www.hldcc.or.kr, https://www.klac.or.kr",
        "license": "원본 법률은 공공누리, 편집본은 프로젝트 소유",
        "update_cycle": "수동",
        "how_collected": "ingest_moveout.py",
        "references": ["주택임대차보호법 제3조의2/3, 제4조, 제14조"],
    },
    {
        "pattern": "mapping/moveout_restoration.json",
        "category": "원상회복 기준",
        "authority": "공정거래위원회 · 대법원 판례 · 한국소비자원",
        "source_url": "공정위 소비자분쟁해결기준",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_moveout.py",
        "references": ["민법 제615조, 제623조", "공정위 소비자분쟁해결기준 주거생활"],
    },
    {
        "pattern": "mapping/moveout_waste_disposal.json",
        "category": "대형폐기물 배출 전국",
        "authority": "환경부 · 각 시·군·구청 · 한국전자제품자원순환공제조합",
        "source_url": "각 지자체 폐기물 시스템 + https://15990903.or.kr",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_moveout.py",
    },
    {
        "pattern": "mapping/moveout_termination_notice.json",
        "category": "계약 해지·갱신 통지 템플릿",
        "authority": "법무부 주택임대차 표준 양식 기반",
        "source_url": "https://www.moj.go.kr",
        "license": "표준 양식 재배포 가능",
        "update_cycle": "수동",
        "how_collected": "ingest_moveout.py",
        "references": ["주택임대차보호법 제6조, 제6조의2, 제6조의3"],
    },
    {
        "pattern": "mapping/moveout_management_refund.json",
        "category": "장기수선충당금·관리비예치금 반환",
        "authority": "국토교통부",
        "source_url": "공동주택관리법 (국가법령정보)",
        "license": "공공누리 제1유형",
        "update_cycle": "수동",
        "how_collected": "ingest_moveout.py",
        "references": ["공동주택관리법 제24조, 제30조"],
    },
    # ----- 품질 평가 -----
    {
        "pattern": "indexes/golden_queries.json",
        "category": "Golden Query 평가 시나리오",
        "authority": "이사이상무 팀",
        "source_url": "팀 자체 작성",
        "license": "프로젝트 소유",
        "update_cycle": "수동",
        "how_collected": "팀 작성 30건",
    },
    {
        "pattern": "indexes/evaluation_report.json",
        "category": "품질 평가 결과",
        "authority": "이사이상무 팀 (evaluate_checklist.py 실행)",
        "source_url": "N/A",
        "license": "프로젝트 소유",
        "update_cycle": "자동 (평가 재실행 시)",
        "how_collected": "evaluate_checklist.py",
    },
]


def match_pattern(file_path: Path, pattern: str) -> bool:
    """글롭 패턴 매칭 (단순)"""
    p = file_path.relative_to(DATA_DIR).as_posix()
    if "*" in pattern:
        import fnmatch

        return fnmatch.fnmatch(p, pattern)
    return p == pattern


def find_source_entry(file_path: Path) -> dict | None:
    for src in SOURCES:
        if match_pattern(file_path, src["pattern"]):
            return src
    return None


# ============================================================
# JSON 파일에 _source_metadata 주입
# ============================================================


def annotate_json_file(path: Path, source: dict) -> bool:
    """JSON 파일 상단에 _source_metadata 필드 주입. 이미 있으면 업데이트."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False

    if not isinstance(data, dict):
        return False  # jsonl 은 별도 처리 안 함 (로드 시점 오버헤드)

    meta = {
        "category": source["category"],
        "authority": source.get("authority"),
        "source_url": source.get("source_url"),
        "api_name": source.get("api_name"),
        "license": source.get("license"),
        "update_cycle": source.get("update_cycle"),
        "how_collected": source.get("how_collected"),
        "last_annotated": TODAY,
    }
    meta = {k: v for k, v in meta.items() if v is not None}

    data["_source_metadata"] = meta
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def annotate_all_json() -> list[tuple[Path, dict]]:
    annotated: list[tuple[Path, dict]] = []
    for path in DATA_DIR.rglob("*.json"):
        src = find_source_entry(path)
        if not src:
            continue
        if annotate_json_file(path, src):
            annotated.append((path, src))
    return annotated


# ============================================================
# DATA_SOURCES.md 카탈로그 생성
# ============================================================


def build_catalog_md(annotated: list[tuple[Path, dict]]) -> str:
    lines = [
        "# 이사이상무 데이터 출처 카탈로그",
        "",
        f"> 2026-04-14 기준 · 총 {len(annotated)} 파일 (JSON) + jsonl 인덱스 3종",
        "",
        "---",
        "",
        "## 📌 한눈에 보기",
        "",
        "| 카테고리 | 개수 | 주요 출처 |",
        "|---|---|---|",
    ]

    # 카테고리별 집계
    by_category: dict[str, list] = {}
    for path, src in annotated:
        key = src["category"]
        by_category.setdefault(key, []).append(path)

    for cat, files in sorted(by_category.items()):
        src = next((s for _, s in annotated if s["category"] == cat), {})
        authority = src.get("authority", "-")
        lines.append(f"| {cat} | {len(files)} | {authority} |")

    lines += [
        "",
        "---",
        "",
        "## 📦 RAG 인덱스 (JSONL, 별도 관리)",
        "",
        "| 파일 | 카테고리 | 개수 | 출처 |",
        "|---|---|---|---|",
        "| `indexes/index_a_chunks.jsonl` | 법률 청크 | 1,950 | 국가법령정보 Open API |",
        "| `indexes/index_b_chunks_curated.jsonl` | 행정 절차 청크 | 200 | 찾기쉬운 생활법령정보 |",
        "| `indexes/index_c_youtube_chunks.jsonl` | 유튜브 자막 청크 | 147 | YouTube (12 영상) |",
        "",
        "---",
        "",
        "## 📄 파일별 상세",
        "",
    ]

    # 디렉토리별 그룹화
    by_dir: dict[str, list] = {}
    for path, src in annotated:
        rel = path.relative_to(DATA_DIR)
        subdir = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        by_dir.setdefault(subdir, []).append((path, src))

    for subdir in sorted(by_dir):
        lines.append(f"### 📁 `backend/data/{subdir}/`")
        lines.append("")
        for path, src in sorted(by_dir[subdir], key=lambda x: x[0].name):
            rel = path.relative_to(DATA_DIR)
            lines.append(f"**`{rel}`**")
            lines.append("")
            lines.append(f"- **카테고리**: {src['category']}")
            lines.append(f"- **담당 기관**: {src.get('authority', '-')}")
            if src.get("source_url"):
                lines.append(f"- **출처 URL**: {src['source_url']}")
            if src.get("api_name"):
                lines.append(f"- **API**: {src['api_name']}")
            lines.append(f"- **라이선스**: {src.get('license', '-')}")
            lines.append(f"- **갱신 주기**: {src.get('update_cycle', '-')}")
            lines.append(f"- **수집 방법**: {src.get('how_collected', '-')}")
            if src.get("references"):
                refs = src["references"]
                lines.append(f"- **참고 법령**: {', '.join(refs)}")
            lines.append("")
        lines.append("")

    lines += [
        "---",
        "",
        "## ⚖️ 라이선스 정리",
        "",
        "- **공공누리 제1유형** — 출처 표시 조건으로 자유 이용, 재배포, 상업적 이용 가능",
        "  - 법률, 행정 절차, 공휴일, 지자체 정보, 정부 산하 기관",
        "- **영상별 채널 귀속** — 유튜브 자막 원본",
        "  - 프로젝트 내부용 가공·분석만 허용",
        "  - 발표 시 요약·캡처만 인용, 원본 영상 재배포 금지",
        "- **프로젝트 소유** — 팀 자체 작성물",
        "  - Golden Query, 평가 리포트, 퇴거 타임라인 편집본",
        "",
        "---",
        "",
        "## 🔄 갱신 방법",
        "",
        "각 데이터는 `backend/scripts/ingest_*.py` 를 재실행해서 갱신:",
        "",
        "```bash",
        "# 법률 (LAW_OC 필요)",
        "python3 backend/scripts/ingest_laws.py",
        "",
        "# 행정 절차 (법제처)",
        "python3 backend/scripts/ingest_easylaw.py",
        "python3 backend/scripts/chunk_easylaw.py",
        "python3 backend/scripts/curate_chunks.py",
        "",
        "# 매핑 (수도·전기·통신·정부24·HUG·퇴거 등)",
        "python3 backend/scripts/ingest_water.py",
        "python3 backend/scripts/ingest_services.py",
        "python3 backend/scripts/ingest_services_v2.py",
        "python3 backend/scripts/ingest_moveout.py",
        "",
        "# 공휴일 · 유튜브 · 도시가스",
        "python3 backend/scripts/ingest_holidays.py",
        "python3 backend/scripts/ingest_youtube.py",
        "python3 backend/scripts/ingest_citygas.py",
        "",
        "# 메타데이터 재주입 (이 문서 포함)",
        "python3 backend/scripts/annotate_sources.py",
        "```",
        "",
        "---",
        "",
        "## 📞 문의",
        "",
        "출처 확인·라이선스 검토·갱신 제안은 팀 채널로 연락.",
        "",
        f"*생성일: {TODAY}*",
        "",
    ]
    return "\n".join(lines)


# ============================================================
# 메인
# ============================================================


def main() -> None:
    print("🏷  모든 JSON 파일에 _source_metadata 주입 중...")
    annotated = annotate_all_json()
    print(f"  ✅ {len(annotated)} 파일 주석 완료")
    print()
    print("📑 DATA_SOURCES.md 카탈로그 생성 중...")
    catalog = build_catalog_md(annotated)

    # 두 곳에 저장: 레포 + 공유 폴더
    out_repo = DATA_DIR / "DATA_SOURCES.md"
    out_repo.write_text(catalog, encoding="utf-8")
    print(f"  ✅ {out_repo.relative_to(ROOT)}")

    shared = Path("/Users/sa/Desktop/movewise-data/데이터_출처_카탈로그.md")
    if shared.parent.exists():
        shared.write_text(catalog, encoding="utf-8")
        print(f"  ✅ {shared}")

    print()
    print("=" * 50)
    print(f"총 {len(annotated)} JSON 파일 주석됨")
    # 디렉토리별 집계
    by_dir: dict[str, int] = {}
    for p, _ in annotated:
        key = p.relative_to(DATA_DIR).parts[0]
        by_dir[key] = by_dir.get(key, 0) + 1
    for k, v in sorted(by_dir.items()):
        print(f"  {k}/: {v}")


if __name__ == "__main__":
    main()
