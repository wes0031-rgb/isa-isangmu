"""SafeContract 강화 + 핵심 행정기관 매핑 데이터 일괄 수집 (v2).

MoveWise 앱 의도 강화:
- 계약 전 체크의 "다음에 확인하세요" referrals 확장 (4개 → 12개)
- 이사 후 빠지기 쉬운 핵심 행정기관 5종 추가

모든 데이터는 각 기관 공식 페이지 기준 (공공누리 1유형).

Usage:
  python3 backend/scripts/ingest_services_v2.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MAPPING_DIR = ROOT / "backend" / "data" / "mapping"
MAPPING_DIR.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()


# ============================================================
# 🛡 SafeContract 강화 8종
# ============================================================

HUG_ANSIM_JEONSE = {
    "service": "HUG 안심전세 앱",
    "authority": "주택도시보증공사 (HUG)",
    "category": "safecontract_referral",
    "website": "https://www.khug.or.kr",
    "app_url": "https://jeonse.khug.or.kr",
    "app_name": "안심전세 앱",
    "app_store": {
        "ios": "https://apps.apple.com/kr/app/안심전세/id6447189520",
        "android": "https://play.google.com/store/apps/details?id=kr.co.khug.anxjeonse",
    },
    "call": "1566-9009",
    "call_label": "HUG 고객상담센터",
    "purpose": "계약 전 전세 물건의 시세·권리관계·보증 가능 여부를 종합 확인",
    "key_features": [
        "해당 물건 시세 조회 (KB·부동산원 기준)",
        "등기부등본 권리 관계 자동 분석 (근저당·압류 등)",
        "전세보증금 반환보증 가입 가능 여부 즉시 확인",
        "깡통전세 위험 진단",
        "임대인 HUG 블랙리스트 조회",
    ],
    "process": [
        "안심전세 앱 설치 → 회원가입 (간편인증)",
        "주소 입력 → 자동으로 시세·권리관계·보증 가능 여부 표시",
        "결과 보고 계약 여부 판단",
    ],
    "fee": "무료 (보증보험 가입은 별도 유료)",
    "tip": "계약서 작성 '전'에 반드시 조회. 보증 가입 불가 물건은 피해야 함.",
    "source": "https://www.khug.or.kr / https://jeonse.khug.or.kr",
}

HUG_DEFAULT_LIST = {
    "service": "HUG 보증금 미반환 임대인 정보 공개",
    "authority": "주택도시보증공사 (HUG)",
    "category": "safecontract_referral",
    "website": "https://www.khug.or.kr",
    "lookup_url": "https://www.khug.or.kr/hug/web/ig/dg/igdg000001.jsp",
    "call": "1566-9009",
    "call_label": "HUG 고객상담센터",
    "purpose": "보증금 미반환 상습 채무불이행 임대인 정보 조회",
    "legal_basis": "주택도시기금법 제26조의3 (임대인 정보 공개)",
    "who_is_listed": [
        "HUG 전세보증금 반환보증으로 구상 채권을 발생시킨 임대인",
        "2건 이상 미반환 또는 일정 금액 이상 채무 불이행",
        "국토교통부 심의 거쳐 공개 대상 확정",
    ],
    "process": [
        "HUG 홈페이지 → '안심전세포털' → '임대인 정보 공개 조회'",
        "임대인 이름·주민번호 뒤 1자리 입력 (본인 인증 필수)",
        "미반환 내역이 있으면 경고 표시",
    ],
    "tip": (
        "법적으로 공개 대상이 된 임대인만 조회 가능. "
        "공개 대상 아니어도 위험할 수 있으니 등기부등본·안심전세 앱 병행 확인."
    ),
    "fee": "무료",
    "source": "주택도시보증공사 공식 (2026-04)",
}

IROS_REGISTRY = {
    "service": "대법원 인터넷등기소 (등기부등본 열람·발급)",
    "authority": "대법원 / 법원행정처",
    "category": "safecontract_referral",
    "website": "https://www.iros.go.kr",
    "call": "1544-0773",
    "call_label": "인터넷등기소 콜센터",
    "purpose": "부동산 등기부등본 원본 열람 · 발급 (계약 전 필수)",
    "service_types": [
        {"type": "열람", "fee_krw": 700, "validity": "열람용 (법적 효력 없음, 내용 확인만)"},
        {"type": "발급", "fee_krw": 1000, "validity": "공식 발급본 (법적 효력 있음, 은행 제출용)"},
    ],
    "required_info": [
        "부동산 주소 또는 고유번호",
        "결제 수단 (신용카드 또는 휴대폰)",
    ],
    "process": [
        "iros.go.kr 접속 → 부동산 등기 → 열람/발급",
        "주소 검색 → 해당 부동산 선택",
        "결제 → 즉시 PDF 다운로드 (열람 1회, 발급 3회 재인쇄 가능)",
    ],
    "check_points": [
        "표제부: 부동산 개요 (위치·면적·용도)",
        "갑구: 소유권 관계 (소유자·소유권 이전 이력)",
        "을구: 소유권 외 권리 (근저당권·전세권·임차권 등)",
    ],
    "tip": (
        "계약 전 하루 이내 발급본이 가장 안전. "
        "임대인이 보여주는 등기부는 구본일 수 있으니 본인이 직접 발급 권장."
    ),
    "source": "https://www.iros.go.kr (2026-04)",
}

LEASE_DISPUTE = {
    "service": "주택임대차분쟁조정위원회",
    "authority": "법무부 / 대한법률구조공단",
    "category": "safecontract_referral",
    "website": "https://www.hldcc.or.kr",
    "call": "1600-2571",
    "call_label": "분쟁조정위원회 콜센터",
    "purpose": "임대차 분쟁 (보증금 반환·수선·해지 등) 조정 신청",
    "covered_disputes": [
        "보증금 반환 지연",
        "차임(월세) 증감 문제",
        "임대차 계약 해지",
        "보증금 공제·정산",
        "주택의 수선 의무",
        "임대인의 임차인 계약갱신요구 거절",
        "임차권등기명령 관련",
    ],
    "process": [
        "홈페이지 또는 전화로 조정 신청 (신청서 + 증빙)",
        "신청료 입금: 보증금 1억 이하 1만원 / 1~3억 3만원 / 3억 초과 5만원 등 차등",
        "60일 이내 조정 절차 진행 (3개월까지 연장 가능)",
        "조정 성립 시 민사조정 판결과 동일 효력",
    ],
    "legal_basis": "주택임대차보호법 제14조~제20조 (분쟁조정위원회)",
    "advantage": (
        "소송보다 빠르고(60일) 저렴 (수천 원~5만원), 판결과 같은 집행력. "
        "보증금 반환 미이행 1순위 해결 경로."
    ),
    "source": "https://www.hldcc.or.kr (2026-04)",
}

JEONSE_VICTIM_CENTER = {
    "service": "전세피해지원센터",
    "authority": "국토교통부 / HUG",
    "category": "safecontract_referral",
    "website": "https://jeonse119.molit.go.kr",
    "call": "1533-8119",
    "call_label": "전세피해지원센터 대표콜센터",
    "purpose": "전세사기 피해자 종합 지원 (상담·금융·법률·주거)",
    "supported_issues": [
        "보증금 미반환 피해",
        "깡통전세 피해",
        "전세사기 (임대인 도주 등)",
        "임차권등기명령 신청 지원",
        "긴급 주거 이전 지원",
        "저리 대출 지원",
    ],
    "locations": [
        {"name": "서울 강서 센터", "address": "서울 강서구", "phone": "02-2000-0311"},
        {"name": "서울 중부 센터", "address": "서울 중구", "phone": "02-2000-0322"},
        {"name": "인천 센터", "address": "인천시", "phone": "032-830-6030"},
        {"name": "경기 수원 센터", "address": "수원", "phone": "031-8008-2010"},
        {"name": "부산 센터", "address": "부산시", "phone": "051-888-3410"},
        {"name": "대전 센터", "address": "대전시", "phone": "042-270-6150"},
        {"name": "대구 센터", "address": "대구시", "phone": "053-803-6900"},
    ],
    "free_services": [
        "무료 법률 자문 (변호사 1:1 상담)",
        "긴급 주거 지원 (임시 거처)",
        "보증금 저리 대출 (최대 2억, 연 1~2%)",
        "임차권등기명령 신청 대행",
        "경매 대응 지원",
    ],
    "fee": "전체 무료",
    "source": "https://jeonse119.molit.go.kr (2026-04)",
}

LEGAL_AID = {
    "service": "대한법률구조공단 (무료 법률 상담)",
    "authority": "법무부 산하 공공기관",
    "category": "safecontract_referral",
    "website": "https://www.klac.or.kr",
    "call": "132",
    "call_label": "법률상담 132 (전국 공통)",
    "purpose": "임대차 등 민사 분쟁 무료 법률 상담 및 소송구조",
    "services": [
        "전화 법률 상담 (132, 평일 09~18시, 무료)",
        "방문 상담 (전국 18개 지부, 사전 예약 권장)",
        "소송 구조 (경제적 어려움 시 변호사비·인지대 지원)",
        "사이버 상담 (홈페이지 1:1 문의)",
    ],
    "covered_issues": [
        "보증금 반환 청구",
        "임대차 계약 해지·갱신",
        "임차권등기명령",
        "경매 배당 참여",
        "전세사기 피해 대응",
    ],
    "income_criteria": (
        "소송구조는 중위소득 125% 이하 또는 기초생활수급자 대상. "
        "단순 상담은 소득 무관 무료."
    ),
    "tip": (
        "임대차 분쟁은 전국에서 가장 흔한 민사 사건이라 132 상담원이 매우 숙련됨. "
        "분쟁조정위원회 신청 전 132 먼저 상담 권장."
    ),
    "source": "https://www.klac.or.kr (2026-04)",
}

STANDARD_CONTRACT = {
    "service": "법무부 표준 임대차계약서",
    "authority": "법무부 / 국토교통부",
    "category": "safecontract_referral",
    "website": "https://www.moj.go.kr",
    "download_url": "https://www.moj.go.kr/moj/215/subview.do",
    "purpose": "법무부·국토교통부 공동 배포 주택임대차 표준계약서",
    "versions": [
        "주택임대차 표준계약서 (일반)",
        "주택임대차 표준계약서 (전세 확정일자 포함)",
        "주택임대차 표준계약서 (갱신계약용)",
    ],
    "key_clauses": [
        "임차인이 특별히 요청할 수 있는 임의 특약 조항",
        "임대인 정보 고지 의무 (다른 소유자·저당권 등)",
        "임대인 세금 체납 여부 고지",
        "보증금 반환 조건",
        "원상회복 범위",
    ],
    "legal_basis": "주택임대차보호법 제30조 (표준계약서 권장)",
    "tip": (
        "표준계약서 사용은 의무는 아니지만, 법적 분쟁 시 표준계약서 기준으로 "
        "해석되므로 임차인 보호에 유리. 특약 란에 '세금 체납 없음 확인' 명시 권장."
    ),
    "source": "법무부 공식 (2026-04)",
}

SEOUL_REALTY_CHECK = {
    "service": "서울시 전월세 정보몽땅",
    "authority": "서울특별시",
    "category": "safecontract_referral",
    "website": "https://rent.seoul.go.kr",
    "call": "120",
    "call_label": "서울 다산콜센터",
    "purpose": "서울 지역 전월세 계약 시 종합 검토 도구 (서울 한정)",
    "key_features": [
        "집주인 정보 확인 (세금 체납 여부 등)",
        "전세보증금 반환 능력 검토",
        "등기부 분석 자동화",
        "실거래가 비교",
        "안심거래 서비스 (중개사 인증)",
    ],
    "note": (
        "서울 거주자 또는 서울 지역 계약 시 유용. "
        "다른 지역은 HUG 안심전세 앱 권장."
    ),
    "source": "https://rent.seoul.go.kr (2026-04)",
}


# ============================================================
# 🏥 핵심 행정기관 5종
# ============================================================

HEALTH_INSURANCE = {
    "service": "국민건강보험공단 주소변경",
    "authority": "국민건강보험공단",
    "category": "admin_after_move",
    "website": "https://www.nhis.or.kr",
    "call": "1577-1000",
    "call_label": "건강보험 고객센터",
    "online_url": "https://www.nhis.or.kr/nhis/minwon/retrieveWbmcb07200lm01.do",
    "purpose": "건강보험 가입자 주소 변경 (지역가입자는 보험료 영향 있음)",
    "process": [
        "전입신고 시 자동 반영 (대부분의 경우)",
        "자동 반영 안 된 경우: 건강보험공단 사이버민원 또는 1577-1000",
        "지역가입자는 주소에 따라 보험료 재산정 가능성 있음",
    ],
    "important_notes": [
        "직장가입자: 회사 인사팀에 주소변경 별도 통보",
        "지역가입자: 재산 기준 변경으로 보험료 조정 가능",
        "피부양자: 주소이전 시 자동 연동",
    ],
    "tip": "이사 후 보험료 고지서에 새 주소 찍혔는지 확인. 안 되면 바로 연락.",
    "source": "https://www.nhis.or.kr (2026-04)",
}

NATIONAL_PENSION = {
    "service": "국민연금공단 주소변경",
    "authority": "국민연금공단",
    "category": "admin_after_move",
    "website": "https://www.nps.or.kr",
    "call": "1355",
    "call_label": "국민연금 콜센터",
    "online_url": "https://www.nps.or.kr/jsppage/service/minwon/minwon_05_01.jsp",
    "purpose": "국민연금 가입자 주소 변경 (수령 알림 등 수신 확인)",
    "process": [
        "전입신고 시 자동 반영",
        "자동 반영 안 된 경우: 국민연금 홈페이지 사이버민원 → 주소변경",
        "지사 방문 또는 1355 전화",
    ],
    "importance": (
        "연금 수급자 또는 추납·임의가입자는 주소 미갱신 시 중요 안내 우편 "
        "(보험료 고지·수급 관련)을 놓칠 수 있음."
    ),
    "tip": (
        "납부 중인 가입자는 자동 연동되지만, 수급자(노령연금·장애연금)는 "
        "반드시 공단 지사에 직접 확인."
    ),
    "source": "https://www.nps.or.kr (2026-04)",
}

HOMETAX = {
    "service": "국세청 홈택스 주소변경",
    "authority": "국세청",
    "category": "admin_after_move",
    "website": "https://hometax.go.kr",
    "call": "126",
    "call_label": "국세청 세미래 콜센터 126",
    "online_url": "https://www.hometax.go.kr/websquare/websquare.html?w2xPath=/ui/pp/index_pp.xml",
    "purpose": "사업자·근로자 주소 변경 (세무 관련 문서 수신지)",
    "target": [
        "사업자: 사업장 주소 변경 (부가가치세·종합소득세 영향)",
        "근로자: 거주지 주소 변경 (연말정산·주택공제 영향)",
        "개인: 세금 고지서 수신 주소",
    ],
    "process": [
        "홈택스 접속 → 공동인증서 로그인",
        "신청·제출 → 신청·민원 → 주소변경 신청",
        "즉시 처리 (변경 즉시 홈택스에 반영)",
    ],
    "importance": (
        "연말정산 시 주택청약·월세 세액공제는 주소지 기준으로 판단. "
        "주소 미변경 상태면 세액공제 증빙 어려울 수 있음."
    ),
    "tip": (
        "전입신고해도 홈택스는 자동 연동 안 됨. 별도 신청 필수. "
        "월세 세액공제 받으려면 확정일자 + 홈택스 주소 모두 일치해야 함."
    ),
    "source": "https://hometax.go.kr (2026-04)",
}

MILITARY = {
    "service": "병무청 주소변경",
    "authority": "병무청",
    "category": "admin_after_move",
    "website": "https://www.mma.go.kr",
    "call": "1588-9090",
    "call_label": "병무청 통합 콜센터",
    "online_url": "https://www.mma.go.kr/contents.do?mc=mma0000000",
    "purpose": "병역 대상 남성 주소 변경 (영장 수신 확인)",
    "target": [
        "18세 이상 병역 의무자 (예비군 포함)",
        "현역/보충역/공익근무요원 복무 중",
        "예비군 훈련 대상자 (만 8년)",
    ],
    "process": [
        "전입신고 시 자동 연계 (주민등록 연동)",
        "자동 연계 안 되거나 해외거주 → 병무청 홈페이지 / 1588-9090",
        "전입 후 14일 이내 확인 권장",
    ],
    "importance": (
        "영장이 이전 주소로 가면 수령 못 해도 법적 책임. "
        "예비군 훈련 통지서도 주소지 기준이라 미수령 시 불이익 가능."
    ),
    "legal_basis": "병역법 제11조 (주소 이동 신고 의무)",
    "tip": "전입신고 완료 후 1주 내 병무청 사이트에서 주소 확인 권장",
    "source": "https://www.mma.go.kr (2026-04)",
}

KFTC_ACCOUNTS = {
    "service": "금융결제원 내계좌 한눈에 (계좌·카드 일괄 주소변경)",
    "authority": "금융결제원 (KFTC)",
    "category": "admin_after_move",
    "website": "https://www.payinfo.or.kr",
    "call": "1577-5500",
    "call_label": "어카운트인포 콜센터",
    "online_url": "https://www.payinfo.or.kr/payinfo.html",
    "purpose": "은행·카드·증권 계좌 주소를 한 번에 확인·변경",
    "features": [
        "전 은행 본인 명의 계좌 조회",
        "카드 주소 일괄 변경",
        "휴면 계좌 조회 및 환급",
        "자동이체 출금계좌 변경",
    ],
    "process": [
        "payinfo.or.kr 접속 → 공동인증서 또는 금융인증서 로그인",
        "계좌 정보 변경 → 주소 변경",
        "선택한 금융사 일괄 적용",
    ],
    "advantage": (
        "은행·카드사 각각 개별 변경하면 10곳 이상 전화해야 함. "
        "어카운트인포로 한 번에 처리 가능."
    ),
    "caveat": (
        "모든 금융사가 자동 변경되는 건 아님. 제2금융권 일부 · 보험사는 별도. "
        "자동이체 변경은 별도 메뉴."
    ),
    "source": "https://www.payinfo.or.kr (2026-04)",
}


# ============================================================
# 실행
# ============================================================


def write_file(name: str, data: dict) -> Path:
    data["generated_at"] = TODAY
    path = MAPPING_DIR / f"{name}.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def main() -> None:
    files = [
        # SafeContract 강화 8종
        ("hug_ansim_jeonse", HUG_ANSIM_JEONSE, "HUG 안심전세 앱"),
        ("hug_default_list", HUG_DEFAULT_LIST, "HUG 임대인 공개"),
        ("iros_registry", IROS_REGISTRY, "인터넷등기소"),
        ("lease_dispute_committee", LEASE_DISPUTE, "주택임대차분쟁조정"),
        ("jeonse_victim_support", JEONSE_VICTIM_CENTER, "전세피해지원센터"),
        ("legal_aid_132", LEGAL_AID, "법률구조공단 132"),
        ("moj_standard_contract", STANDARD_CONTRACT, "법무부 표준계약서"),
        ("seoul_realty_check", SEOUL_REALTY_CHECK, "서울 전월세 정보몽땅"),
        # 핵심 행정기관 5종
        ("nhis_health_insurance", HEALTH_INSURANCE, "국민건강보험공단"),
        ("nps_national_pension", NATIONAL_PENSION, "국민연금공단"),
        ("hometax_nts", HOMETAX, "국세청 홈택스"),
        ("mma_military", MILITARY, "병무청"),
        ("kftc_accounts", KFTC_ACCOUNTS, "금융결제원 내계좌한눈에"),
    ]
    print(f"🚀 {len(files)}개 서비스 데이터 생성 (SafeContract 8 + 행정 5)")
    print()
    for fname, data, label in files:
        path = write_file(fname, data)
        size = path.stat().st_size
        print(f"  ✅ {label:25s} → {path.name} ({size:,}B)")
    print()
    print(f"📁 저장 위치: {MAPPING_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
