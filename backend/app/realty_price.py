"""국토교통부 아파트 매매 실거래가 API 연동.

공공데이터포털 'RTMSDataSvcAptTradeDev' 를 사용해 사용자 지역의
최근 거래가를 조회한다. SafeContract 에서 깡통전세 비율 판정 시
시세를 자동 제안하는 용도.

활용신청 필요:
  https://www.data.go.kr/data/15057511/openapi.do
  (서비스키 자체는 발급돼 있어도 이 API는 별도 승인 필요)

Fallback:
  API 키 승인 전까지는 HUG 안심전세 앱 / KB부동산 / 네이버 부동산
  사용 안내 반환.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional
from xml.etree import ElementTree as ET

import requests

from .config import get_settings
from .local_search import clean_hanja


# 주요 지역 → 국토교통부 법정동코드 (5자리) 매핑
# 전체 코드는 행정안전부 주소 기반 표준데이터 참고.
# 아파트 실거래가 조회 시 LAWD_CD 파라미터로 사용.
LAWD_CD: dict[str, str] = {
    # 서울
    "서울특별시 종로구": "11110",
    "서울특별시 중구": "11140",
    "서울특별시 용산구": "11170",
    "서울특별시 성동구": "11200",
    "서울특별시 광진구": "11215",
    "서울특별시 동대문구": "11230",
    "서울특별시 중랑구": "11260",
    "서울특별시 성북구": "11290",
    "서울특별시 강북구": "11305",
    "서울특별시 도봉구": "11320",
    "서울특별시 노원구": "11350",
    "서울특별시 은평구": "11380",
    "서울특별시 서대문구": "11410",
    "서울특별시 마포구": "11440",
    "서울특별시 양천구": "11470",
    "서울특별시 강서구": "11500",
    "서울특별시 구로구": "11530",
    "서울특별시 금천구": "11545",
    "서울특별시 영등포구": "11560",
    "서울특별시 동작구": "11590",
    "서울특별시 관악구": "11620",
    "서울특별시 서초구": "11650",
    "서울특별시 강남구": "11680",
    "서울특별시 송파구": "11710",
    "서울특별시 강동구": "11740",
    # 부산
    "부산광역시 중구": "26110",
    "부산광역시 서구": "26140",
    "부산광역시 동구": "26170",
    "부산광역시 영도구": "26200",
    "부산광역시 부산진구": "26230",
    "부산광역시 동래구": "26260",
    "부산광역시 남구": "26290",
    "부산광역시 북구": "26320",
    "부산광역시 해운대구": "26350",
    "부산광역시 사하구": "26380",
    "부산광역시 금정구": "26410",
    "부산광역시 강서구": "26440",
    "부산광역시 연제구": "26470",
    "부산광역시 수영구": "26500",
    "부산광역시 사상구": "26530",
    "부산광역시 기장군": "26710",
    # 대구
    "대구광역시 중구": "27110",
    "대구광역시 동구": "27140",
    "대구광역시 서구": "27170",
    "대구광역시 남구": "27200",
    "대구광역시 북구": "27230",
    "대구광역시 수성구": "27260",
    "대구광역시 달서구": "27290",
    "대구광역시 달성군": "27710",
    # 인천
    "인천광역시 중구": "28110",
    "인천광역시 동구": "28140",
    "인천광역시 미추홀구": "28177",
    "인천광역시 연수구": "28185",
    "인천광역시 남동구": "28200",
    "인천광역시 부평구": "28237",
    "인천광역시 계양구": "28245",
    "인천광역시 서구": "28260",
    "인천광역시 강화군": "28710",
    "인천광역시 옹진군": "28720",
    # 광주
    "광주광역시 동구": "29110",
    "광주광역시 서구": "29140",
    "광주광역시 남구": "29155",
    "광주광역시 북구": "29170",
    "광주광역시 광산구": "29200",
    # 대전
    "대전광역시 동구": "30110",
    "대전광역시 중구": "30140",
    "대전광역시 서구": "30170",
    "대전광역시 유성구": "30200",
    "대전광역시 대덕구": "30230",
    # 울산
    "울산광역시 중구": "31110",
    "울산광역시 남구": "31140",
    "울산광역시 동구": "31170",
    "울산광역시 북구": "31200",
    "울산광역시 울주군": "31710",
    # 세종
    "세종특별자치시": "36110",
    # 경기도 주요
    "경기도 수원시 장안구": "41111",
    "경기도 수원시 권선구": "41113",
    "경기도 수원시 팔달구": "41115",
    "경기도 수원시 영통구": "41117",
    "경기도 성남시 수정구": "41131",
    "경기도 성남시 중원구": "41133",
    "경기도 성남시 분당구": "41135",
    "경기도 의정부시": "41150",
    "경기도 안양시 만안구": "41171",
    "경기도 안양시 동안구": "41173",
    "경기도 부천시": "41190",
    "경기도 광명시": "41210",
    "경기도 평택시": "41220",
    "경기도 고양시 덕양구": "41281",
    "경기도 고양시 일산동구": "41285",
    "경기도 고양시 일산서구": "41287",
    "경기도 용인시 처인구": "41461",
    "경기도 용인시 기흥구": "41463",
    "경기도 용인시 수지구": "41465",
    "경기도 화성시": "41590",
    "경기도 안산시 상록구": "41271",
    "경기도 안산시 단원구": "41273",
    "경기도 하남시": "41450",
    "경기도 김포시": "41570",
    # 제주
    "제주특별자치도 제주시": "50110",
    "제주특별자치도 서귀포시": "50130",
}


@dataclass
class RealtyPrice:
    """단일 실거래 데이터."""
    apt_name: str
    deal_amount_krw: int  # 원 단위
    deal_year: int
    deal_month: int
    deal_day: int
    area_m2: float
    floor: int
    dong: str


@dataclass
class RealtyPriceSummary:
    """조회 결과 집계."""
    region: str
    lawd_cd: Optional[str]
    query_ym: str  # YYYYMM
    total_count: int
    recent_deals: list[RealtyPrice]
    median_price_krw: Optional[int]
    min_price_krw: Optional[int]
    max_price_krw: Optional[int]
    error: Optional[str] = None


class RealtyApiNotAuthorized(RuntimeError):
    """공공데이터포털에서 이 API 활용신청이 승인되지 않음."""


def lookup_lawd_cd(region: str) -> Optional[str]:
    """지역명으로 법정동코드 5자리 조회 (부분 일치 허용)."""
    if region in LAWD_CD:
        return LAWD_CD[region]
    # 부분 매칭: 구/군 키가 region 에 포함되는지
    for key, code in LAWD_CD.items():
        if key in region or region in key:
            return code
    # 광역시 매칭: '서울특별시' 같은 상위 키워드
    for key, code in LAWD_CD.items():
        parts = key.split()
        if len(parts) >= 1 and parts[0] in region:
            return code
    return None


def fetch_recent_deals(
    lawd_cd: str, year_month: str, num_rows: int = 30
) -> list[dict]:
    """실제 실거래가 API 호출.

    Raises:
        RealtyApiNotAuthorized: API 키가 이 API에 승인되지 않은 경우 (403)
    """
    settings = get_settings()
    if not settings.data_go_kr_service_key:
        raise RealtyApiNotAuthorized("DATA_GO_KR_SERVICE_KEY 미설정")

    # 2026-04 기준 신규 엔드포인트 (publicDataPk 15126469)
    # 이전 getRTMSDataSvcAptTradeDev 는 deprecated
    url = (
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/"
        "getRTMSDataSvcAptTrade"
    )
    params = {
        "serviceKey": settings.data_go_kr_service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": year_month,
        "numOfRows": num_rows,
        "pageNo": 1,
    }
    resp = requests.get(url, params=params, timeout=15)

    if resp.status_code == 403:
        raise RealtyApiNotAuthorized(
            "공공데이터포털에서 '국토교통부_아파트 매매 실거래자료' API "
            "활용신청이 필요합니다. https://www.data.go.kr/data/15057511/openapi.do"
        )
    if resp.status_code != 200:
        raise RuntimeError(f"실거래가 API HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        raise RuntimeError(f"실거래가 API 응답 파싱 실패: {exc}")

    result_code = root.findtext(".//resultCode", default="")
    # 공공데이터포털 성공 코드: '00', '000', '0' 모두 가능
    if result_code not in ("00", "000", "0"):
        msg = root.findtext(".//resultMsg", default="")
        raise RealtyApiNotAuthorized(f"API 응답 오류: {result_code} {msg}")

    items: list[dict] = []
    for item in root.iter("item"):
        items.append(
            {
                "apt_name": clean_hanja((item.findtext("aptNm") or "").strip()),
                "deal_amount": (item.findtext("dealAmount") or "").strip(),
                "deal_year": int(item.findtext("dealYear") or 0),
                "deal_month": int(item.findtext("dealMonth") or 0),
                "deal_day": int(item.findtext("dealDay") or 0),
                "area": float(item.findtext("excluUseAr") or 0),
                "floor": int(item.findtext("floor") or 0),
                "dong": (item.findtext("umdNm") or "").strip(),
            }
        )
    return items


def _parse_amount_to_krw(raw: str) -> int:
    """'85,000' (만원 단위) → 850,000,000 원."""
    clean = raw.replace(",", "").replace(" ", "")
    if not clean.isdigit():
        return 0
    return int(clean) * 10_000  # 만원 → 원


def get_region_price_summary(region: str) -> RealtyPriceSummary:
    """지역명으로 최근 거래가 집계 반환.

    Safe: 모든 예외를 잡아 error 필드에 기록. 호출자는 error 확인만 하면 됨.
    """
    lawd_cd = lookup_lawd_cd(region)
    today = date.today()
    # 이전 달 기준 (당월은 데이터 미확정)
    last_month = today.month - 1 or 12
    last_year = today.year if today.month > 1 else today.year - 1
    ym = f"{last_year}{last_month:02d}"

    summary = RealtyPriceSummary(
        region=region,
        lawd_cd=lawd_cd,
        query_ym=ym,
        total_count=0,
        recent_deals=[],
        median_price_krw=None,
        min_price_krw=None,
        max_price_krw=None,
    )

    if not lawd_cd:
        summary.error = f"지역 '{region}' 에 해당하는 법정동코드 없음. 주요 시·군·구만 지원."
        return summary

    try:
        items = fetch_recent_deals(lawd_cd, ym)
    except RealtyApiNotAuthorized as exc:
        summary.error = f"API 미승인: {exc}"
        return summary
    except Exception as exc:
        summary.error = f"API 호출 실패: {exc}"
        return summary

    deals: list[RealtyPrice] = []
    prices: list[int] = []
    for it in items:
        amount = _parse_amount_to_krw(it["deal_amount"])
        if amount <= 0:
            continue
        prices.append(amount)
        deals.append(
            RealtyPrice(
                apt_name=it["apt_name"],
                deal_amount_krw=amount,
                deal_year=it["deal_year"],
                deal_month=it["deal_month"],
                deal_day=it["deal_day"],
                area_m2=it["area"],
                floor=it["floor"],
                dong=it["dong"],
            )
        )

    summary.total_count = len(deals)
    summary.recent_deals = sorted(
        deals,
        key=lambda d: (d.deal_year, d.deal_month, d.deal_day),
        reverse=True,
    )[:10]
    if prices:
        prices.sort()
        summary.min_price_krw = prices[0]
        summary.max_price_krw = prices[-1]
        mid = len(prices) // 2
        summary.median_price_krw = (
            prices[mid] if len(prices) % 2 == 1 else (prices[mid - 1] + prices[mid]) // 2
        )

    return summary
