"""체크리스트 항목별 기관·절차 매핑 데이터 일괄 수집.

전기·통신·우편·정부24·반려동물·자동차·전학·외국인 등록 등
이사이상무 체크리스트에서 인용할 공식 기관 정보를 한 파일씩 저장한다.

모든 데이터는 각 기관 공식 페이지 기준 (공공누리 1유형 또는 공공 안내).
출처 URL 포함, 정기 수동 갱신 대상.

Usage:
  python3 backend/scripts/ingest_services.py
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
# 1. 한전 (KEPCO) - 전기 명의변경
# ============================================================
KEPCO = {
    "service": "전기 명의변경",
    "authority": "한국전력공사 (KEPCO)",
    "common_call": "123",
    "common_call_label": "한전 고객센터 123 (전국)",
    "website": "https://www.kepco.co.kr",
    "online_change": {
        "label": "한전ON / 한전 앱",
        "url": "https://online.kepco.co.kr",
        "note": "공동인증서 필요, 24시간 가능",
    },
    "guide_url": "https://cyber.kepco.co.kr/ckepco/front/jsp/CY/A/A/CYAAPP000.jsp",
    "required_info": [
        "고객번호 (고지서 또는 계량기 옆 스티커)",
        "이사 주소 (전/신주소)",
        "본인 확인 정보 (이름·주민번호 또는 사업자등록번호)",
        "이사일",
    ],
    "process": [
        "한전 123 전화 → 이사 알림 → 자동 명의변경 안내",
        "또는 한전ON 접속 → 로그인 → 이사 신청 → 폐전(기존집) + 전입(새집) 동시 신청",
        "지역 관계없이 전국 공통 콜센터 123 사용",
    ],
    "tip": "이사 전날이나 당일에 연락. 폐전과 전입을 같은 날짜로 지정하면 공백 없음.",
    "regional_centers": [
        {"name": "서울지역본부", "phone": "02-3464-0000", "region": ["서울특별시"]},
        {"name": "경기지역본부", "phone": "031-259-3000", "region": ["경기도"]},
        {"name": "인천지역본부", "phone": "032-420-7114", "region": ["인천광역시"]},
        {"name": "강원지역본부", "phone": "033-258-2114", "region": ["강원특별자치도"]},
        {"name": "대전·세종·충남지역본부", "phone": "042-865-6114", "region": ["대전광역시", "세종특별자치시", "충청남도"]},
        {"name": "충북지역본부", "phone": "043-261-2114", "region": ["충청북도"]},
        {"name": "전북지역본부", "phone": "063-250-6114", "region": ["전북특별자치도"]},
        {"name": "광주·전남지역본부", "phone": "062-260-8114", "region": ["광주광역시", "전라남도"]},
        {"name": "대구지역본부", "phone": "053-606-8114", "region": ["대구광역시"]},
        {"name": "경북지역본부", "phone": "054-840-3114", "region": ["경상북도"]},
        {"name": "부산·울산지역본부", "phone": "051-792-8114", "region": ["부산광역시", "울산광역시"]},
        {"name": "경남지역본부", "phone": "055-279-7114", "region": ["경상남도"]},
        {"name": "제주지역본부", "phone": "064-740-9000", "region": ["제주특별자치도"]},
    ],
    "source": "한국전력공사 공식 홈페이지 (kepco.co.kr) 및 cyber.kepco.co.kr",
    "legal_basis": "전기사업법 시행규칙 (사용자 변경 신고)",
}


# ============================================================
# 2. 통신사 (KT / SKB / LGU+) - 인터넷·TV 이전 설치
# ============================================================
TELECOM = {
    "service": "인터넷·TV·유선전화 이전 설치",
    "providers": [
        {
            "name": "KT",
            "short_call": "100",
            "call_label": "KT 고객센터 100",
            "english_call": "01485-100",
            "website": "https://product.kt.com",
            "move_url": "https://shop.kt.com/unit/moveInfo.do",
            "app": "마이 KT 앱",
            "process": [
                "100 전화 → 상담사 연결 → '이사 합니다' 안내",
                "또는 마이 KT 앱 → 나의 상품 → 이사 예약",
                "또는 KT 매장 방문 (신분증 지참)",
            ],
            "lead_time_days": 7,
            "fee_note": "이전 설치비 33,000원 (기사 방문 시), 약정 유지 시 무료",
            "tip": "이사 7일 전에 예약해야 당일 설치 가능. 3일 전 미만이면 기사 배정 어려움.",
        },
        {
            "name": "SK브로드밴드 / SK텔레콤",
            "short_call": "106",
            "call_label": "SK브로드밴드 106 / SKT 114",
            "english_call": "080-828-8288",
            "website": "https://www.skbroadband.com",
            "move_url": "https://www.skbroadband.com/customer/MoveInstall.do",
            "app": "B 우리집 / T world",
            "process": [
                "106 (SKB) / 114 (SKT) 전화 → 이사 신청",
                "또는 B우리집 앱 → 이사 예약",
                "또는 온라인 MoveInstall 페이지에서 예약",
            ],
            "lead_time_days": 7,
            "fee_note": "이전 설치비 33,000원, 약정 유지 시 무료",
            "tip": "3일 전까지 예약 필수. 주말/월요일은 배정 어려움.",
        },
        {
            "name": "LG U+",
            "short_call": "101",
            "call_label": "LG U+ 고객센터 101",
            "english_call": "1644-7000",
            "website": "https://www.lguplus.com",
            "move_url": "https://www.lguplus.com/support/moving",
            "app": "당신의 U+",
            "process": [
                "101 전화 → 이사 상담",
                "또는 당신의 U+ 앱 → 이사 예약",
                "또는 홈페이지 지원센터 → 이사예약",
            ],
            "lead_time_days": 7,
            "fee_note": "이전 설치비 33,000원, 약정 유지 시 무료",
            "tip": "7일 전 권장. 단독주택은 현장 점검 필요할 수 있어 더 일찍.",
        },
    ],
    "common_tip": (
        "모든 통신사는 '약정 기간이 남아 있으면 이전 설치 무료'가 원칙. "
        "약정 해지 시 위약금 발생. 이사 가는 집이 통신사 신호 잡히는지 "
        "(특히 SKB 동축 케이블, LGU+ 광케이블) 미리 문의 필수."
    ),
    "source": "각 통신사 공식 홈페이지 및 2026년 4월 기준 상담 안내",
}


# ============================================================
# 3. 우체국 주소이전 서비스
# ============================================================
POST_OFFICE = {
    "service": "우편물 주소이전 서비스",
    "authority": "우정사업본부 / 한국우편사업진흥원",
    "call": "1588-1300",
    "call_label": "우체국 콜센터 1588-1300",
    "website": "https://service.epost.go.kr",
    "online_url": "https://service.epost.go.kr/front.RetrieveAddressMoveLeafletMap.postal",
    "process": [
        "service.epost.go.kr 접속",
        "메뉴 → 우편 → 주소이전 서비스",
        "본인 인증 (공동인증서 또는 네이버/카카오)",
        "이전 주소 + 새 주소 + 기간 입력 (최대 3개월)",
        "신청 완료 → 해당 기간 동안 이전 주소로 오는 우편물이 새 주소로 전달",
    ],
    "validity_months": 3,
    "fee": "무료",
    "tip": (
        "이사 후 1~2주 내 바로 신청 권장. "
        "3개월 동안 이전 주소로 오는 우편물만 전달되니 은행·카드 등 "
        "주요 기관은 별도로 주소변경도 해야 함."
    ),
    "legal_basis": "우편법 및 우편법 시행령 (우편물 전송 서비스)",
    "source": "https://service.epost.go.kr (2026-04 확인)",
}


# ============================================================
# 4. 정부24 주요 민원 카탈로그
# ============================================================
GOV24 = {
    "service": "정부24 온라인 민원",
    "authority": "행정안전부",
    "main_url": "https://www.gov.kr",
    "call": "110",
    "call_label": "정부민원안내콜센터 110",
    "services": [
        {
            "name": "전입신고",
            "url": "https://www.gov.kr/portal/main/resident",
            "deep_link": "https://www.gov.kr/mw/AA020InfoCappView.do?HighCtgCD=A01010&CappBizCD=13100000015",
            "authentication": "공동인증서 / 간편인증 (카카오·네이버·토스·KB 등)",
            "processing_time": "즉시 (온라인 신청 완료 시)",
            "fee": "무료",
            "deadline_days": 14,
            "penalty": "5만원 이하 과태료",
            "note": "정부24 전입신고 시 확정일자·자동차 주소변경·양육수당 주소변경도 연계 신청 가능",
        },
        {
            "name": "확정일자 부여 신청",
            "url": "https://www.gov.kr/portal/rcvfvrCn/mypagePtl/list",
            "deep_link": "https://www.gov.kr/mw/AA020InfoCappView.do?HighCtgCD=A01010&CappBizCD=15000000019",
            "authentication": "공동인증서 필수",
            "processing_time": "즉시",
            "fee": "600원 (온라인) / 1,000원 (방문)",
            "deadline_days": 1,
            "note": "전입신고 당일 확정일자 받아야 보증금 우선변제권 확보",
        },
        {
            "name": "주민등록표 등본 발급",
            "url": "https://www.gov.kr/portal/rcvfvrCn/mypagePtl",
            "authentication": "공동인증서 또는 간편인증",
            "fee": "무료 (온라인) / 400원 (발급기) / 500원 (방문)",
            "note": "이사 후 각종 증명서로 필요",
        },
        {
            "name": "반려동물 등록 변경신고",
            "url": "https://www.gov.kr/portal/main/service/13100000170",
            "deep_link": "https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=13100000170",
            "authentication": "공동인증서",
            "deadline_days": 30,
            "penalty": "50만원 이하 과태료",
            "legal_basis": "동물보호법 제15조",
            "note": "정부24 또는 시·군·구청 축산과 / 동물보호관리시스템 animal.go.kr",
        },
        {
            "name": "자동차 변경등록 (주소)",
            "url": "https://www.gov.kr/portal/main/service/13100000037",
            "authentication": "공동인증서",
            "deadline_days": 30,
            "penalty": "50만원 이하 과태료",
            "note": "전입신고 시 자동 반영 가능. 다른 시·도 이사인 경우 직접 신청 필요",
        },
        {
            "name": "인감 주소변경",
            "url": "https://www.gov.kr/portal/main/service/13100000029",
            "note": "전입신고 시 자동 변경됨",
        },
    ],
    "source": "정부24 공식 https://www.gov.kr (2026-04)",
}


# ============================================================
# 5. 반려동물 등록 주소변경
# ============================================================
ANIMAL = {
    "service": "반려동물 등록 주소변경",
    "authority": "농림축산식품부 · 동물보호관리시스템 (APMS)",
    "website": "https://www.animal.go.kr",
    "call": "1577-0954",
    "call_label": "농림축산검역본부 민원콜센터",
    "process": [
        "animal.go.kr 접속 또는 정부24 → '반려동물 등록 변경신고'",
        "공동인증서 로그인",
        "동물 정보 조회 → 주소 변경",
        "즉시 완료 (시스템 반영)",
    ],
    "offline_options": [
        "시·군·구청 축산과 방문 (등록증 지참)",
        "지정 동물등록 대행기관 (동물병원·동물보호센터) 방문",
    ],
    "deadline_days": 30,
    "penalty": "50만원 이하 과태료",
    "legal_basis": "동물보호법 제15조 (등록대상동물 등록·변경신고)",
    "note": (
        "이사뿐만 아니라 소유자 변경, 잃어버림, 사망 등도 30일 이내 신고 필수. "
        "내장칩(마이크로칩) 또는 외장 태그 등록 여부 확인."
    ),
    "source": "https://www.animal.go.kr (2026-04)",
}


# ============================================================
# 6. 자동차 변경등록 (시·도별 등록사업소)
# ============================================================
CAR_REGISTRATION = {
    "service": "자동차 변경등록 (주소)",
    "authority": "국토교통부 · 시·도청 차량등록사업소",
    "website": "https://www.gov.kr/portal/main/service/13100000037",
    "online_url": "https://www.gov.kr (정부24 자동차 변경등록)",
    "call": "110",
    "call_label": "정부민원안내콜센터 110",
    "process": [
        "같은 시·도 내 이사: 전입신고 시 자동 반영 (별도 신청 불필요)",
        "다른 시·도 이사: 정부24 또는 해당 시·도 차량등록사업소 직접 신청",
        "온라인: 정부24 → 자동차 → 변경등록 → 공동인증서 인증",
        "오프라인: 차량등록사업소 방문 (자동차등록증 + 신분증)",
    ],
    "deadline_days": 30,
    "penalty": "최대 50만원 이하 과태료 (자동차관리법)",
    "fee": "무료 (주소변경), 4,000원 (차량등록증 재발급 시)",
    "legal_basis": "자동차관리법 제11조 및 시행령 제13조",
    "sido_offices": [
        {"sido": "서울특별시", "name": "서울시 차량등록소", "phone": "02-120", "website": "https://car.seoul.go.kr"},
        {"sido": "부산광역시", "name": "부산시 차량등록사업소", "phone": "051-888-3114"},
        {"sido": "대구광역시", "name": "대구시 차량등록사업소", "phone": "053-803-6114"},
        {"sido": "인천광역시", "name": "인천시 차량등록사업소", "phone": "032-440-6114"},
        {"sido": "광주광역시", "name": "광주시 차량등록사업소", "phone": "062-613-6114"},
        {"sido": "대전광역시", "name": "대전시 차량등록사업소", "phone": "042-270-6114"},
        {"sido": "울산광역시", "name": "울산시 차량등록사업소", "phone": "052-229-6114"},
        {"sido": "세종특별자치시", "name": "세종시 차량등록소", "phone": "044-300-6114"},
        {"sido": "경기도", "name": "경기도 각 시·군 차량등록사업소", "phone": "031-120"},
        {"sido": "강원특별자치도", "name": "강원도 차량등록사업소", "phone": "033-249-6114"},
        {"sido": "충청북도", "name": "충북 차량등록사업소", "phone": "043-220-6114"},
        {"sido": "충청남도", "name": "충남 차량등록사업소", "phone": "041-635-6114"},
        {"sido": "전북특별자치도", "name": "전북 차량등록사업소", "phone": "063-280-6114"},
        {"sido": "전라남도", "name": "전남 차량등록사업소", "phone": "061-286-6114"},
        {"sido": "경상북도", "name": "경북 차량등록사업소", "phone": "054-880-6114"},
        {"sido": "경상남도", "name": "경남 차량등록사업소", "phone": "055-211-6114"},
        {"sido": "제주특별자치도", "name": "제주시 차량등록소", "phone": "064-710-6114"},
    ],
    "source": "국토교통부 · 정부24 및 각 시·도청 공식 페이지",
}


# ============================================================
# 7. 자녀 전학 절차
# ============================================================
SCHOOL_TRANSFER = {
    "service": "자녀 전학 (초·중·고)",
    "authority": "교육부 · 시·도 교육청",
    "website": "https://www.moe.go.kr",
    "call": "1577-7110",
    "call_label": "교육부 민원콜센터",
    "levels": [
        {
            "level": "초등학교",
            "process": [
                "전입신고 시 주민센터에서 전학 연계 자동 처리 (학구 내 학교 배정)",
                "주민센터에서 '취학아동 전입확인서' 발급",
                "전입확인서를 새 주소지 관할 학교에 제출 → 학적 이관",
                "학교가 배정되면 담임과 등교일 조율",
            ],
            "required_docs": ["전입신고 확인서", "재학증명서 (이전 학교)", "건강기록부"],
            "note": "초등학교는 의무교육이라 전입신고만 하면 거의 자동 배정",
        },
        {
            "level": "중학교",
            "process": [
                "전입신고 → 시·도 교육청 배정",
                "교육지원청에서 학교 배정받음",
                "지정된 학교에 전학 신청 + 학적 이관",
            ],
            "required_docs": ["전입신고 확인서", "재학증명서", "건강기록부", "학생부"],
            "note": "중학교도 의무교육. 교육지원청에서 배정 지역 확인 필요",
        },
        {
            "level": "고등학교",
            "process": [
                "시·도 교육청에 전입학 신청서 제출",
                "교육청이 정원 여유 있는 학교 배정",
                "배정된 학교에서 학적 이관 처리",
            ],
            "required_docs": ["전입신고 확인서", "재학증명서", "학생부", "성적표", "건강기록부"],
            "note": (
                "고등학교는 의무교육이 아니라 정원 확인 필수. "
                "평준화 지역과 비평준화 지역 배정 방식 다름. "
                "교육청 사이트에서 '전학 안내' 페이지 참고."
            ),
        },
    ],
    "sido_education_offices": [
        {"sido": "서울특별시", "name": "서울시교육청", "phone": "02-3999-000", "website": "https://www.sen.go.kr"},
        {"sido": "부산광역시", "name": "부산시교육청", "phone": "051-860-0114", "website": "https://www.pen.go.kr"},
        {"sido": "대구광역시", "name": "대구시교육청", "phone": "053-231-0114", "website": "https://www.dge.go.kr"},
        {"sido": "인천광역시", "name": "인천시교육청", "phone": "032-420-8114", "website": "https://www.ice.go.kr"},
        {"sido": "광주광역시", "name": "광주시교육청", "phone": "062-380-4114", "website": "https://www.gen.go.kr"},
        {"sido": "대전광역시", "name": "대전시교육청", "phone": "042-616-8114", "website": "https://www.dje.go.kr"},
        {"sido": "울산광역시", "name": "울산시교육청", "phone": "052-210-5114", "website": "https://www.use.go.kr"},
        {"sido": "세종특별자치시", "name": "세종시교육청", "phone": "044-320-1000", "website": "https://www.sje.go.kr"},
        {"sido": "경기도", "name": "경기도교육청", "phone": "031-820-0114", "website": "https://www.goe.go.kr"},
        {"sido": "강원특별자치도", "name": "강원도교육청", "phone": "033-258-5114", "website": "https://www.gwe.go.kr"},
        {"sido": "충청북도", "name": "충북교육청", "phone": "043-290-2000", "website": "https://www.cbe.go.kr"},
        {"sido": "충청남도", "name": "충남교육청", "phone": "041-640-7777", "website": "https://www.cne.go.kr"},
        {"sido": "전북특별자치도", "name": "전북교육청", "phone": "063-239-3114", "website": "https://www.jbe.go.kr"},
        {"sido": "전라남도", "name": "전남교육청", "phone": "061-260-0114", "website": "https://www.jne.go.kr"},
        {"sido": "경상북도", "name": "경북교육청", "phone": "054-850-8000", "website": "https://www.gbe.kr"},
        {"sido": "경상남도", "name": "경남교육청", "phone": "055-268-1080", "website": "https://www.gne.go.kr"},
        {"sido": "제주특별자치도", "name": "제주교육청", "phone": "064-710-0114", "website": "https://www.jje.go.kr"},
    ],
    "legal_basis": "초·중등교육법 제13조 (전학)",
    "source": "교육부 및 각 시·도 교육청 공식 페이지",
}


# ============================================================
# 8. 외국인 등록 주소변경
# ============================================================
FOREIGNER = {
    "service": "외국인등록 주소변경",
    "authority": "법무부 출입국·외국인청",
    "website": "https://www.hikorea.go.kr",
    "call": "1345",
    "call_label": "외국인종합안내센터 1345 (19개 언어 지원)",
    "process": [
        "전입신고 완료 후 주소 변경된 주민등록증(외국인등록증) 준비",
        "하이코리아(hikorea.go.kr) 접속 → 전자민원 → 체류지 변경신고",
        "또는 관할 출입국·외국인청 방문 신청 (사전 예약 권장)",
        "외국인등록증 뒷면 주소 갱신 또는 전자 주소 변경",
    ],
    "deadline_days": 14,
    "penalty": "100만원 이하 과태료",
    "legal_basis": "출입국관리법 제36조 (체류지 변경신고)",
    "note": (
        "하이코리아 온라인 신청 시 공동인증서 불필요 (아이디/패스워드). "
        "단기 체류자는 대상 아님 (90일 초과 장기 체류자만)."
    ),
    "major_offices": [
        {"name": "서울출입국·외국인청", "phone": "02-2650-6399", "region": ["서울특별시"]},
        {"name": "인천공항출입국·외국인청", "phone": "032-740-7400", "region": ["인천광역시"]},
        {"name": "수원출입국·외국인청", "phone": "031-695-3800", "region": ["경기도 남부"]},
        {"name": "의정부출입국·외국인청", "phone": "031-828-9300", "region": ["경기도 북부", "강원특별자치도"]},
        {"name": "부산출입국·외국인청", "phone": "051-461-3000", "region": ["부산광역시", "울산광역시", "경상남도 동부"]},
        {"name": "대구출입국·외국인청", "phone": "053-980-3512", "region": ["대구광역시", "경상북도"]},
        {"name": "광주출입국·외국인청", "phone": "062-381-1281", "region": ["광주광역시", "전라남도"]},
        {"name": "대전출입국·외국인청", "phone": "042-220-2011", "region": ["대전광역시", "세종특별자치시", "충청남도", "충청북도"]},
        {"name": "전주출입국·외국인청", "phone": "063-278-9503", "region": ["전북특별자치도"]},
        {"name": "제주출입국·외국인청", "phone": "064-722-1494", "region": ["제주특별자치도"]},
    ],
    "source": "https://www.hikorea.go.kr (2026-04)",
}


# ============================================================
# 쓰기
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
        ("kepco_electricity", KEPCO, "전기"),
        ("telecom_internet", TELECOM, "인터넷·TV"),
        ("post_office_mail_forwarding", POST_OFFICE, "우편물 주소이전"),
        ("gov24_services", GOV24, "정부24 민원"),
        ("animal_registration", ANIMAL, "반려동물 주소변경"),
        ("car_registration", CAR_REGISTRATION, "자동차 변경등록"),
        ("school_transfer", SCHOOL_TRANSFER, "자녀 전학"),
        ("foreigner_registration", FOREIGNER, "외국인 등록 주소변경"),
    ]
    print(f"🚀 {len(files)}개 서비스 데이터 생성")
    print()
    for fname, data, label in files:
        path = write_file(fname, data)
        size = path.stat().st_size
        print(f"  ✅ {label:20s} → {path.relative_to(ROOT)} ({size:,}B)")
    print()
    print(f"📁 저장 위치: {MAPPING_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
