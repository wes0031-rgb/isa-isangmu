# 데이터 수집 리포트

**일자:** 2026-04-13
**수집 담당:** Claude (자동화)
**범위:** 전국
**위치:** `/Users/sa/Desktop/2차프로젝트/backend/data/`

---

## ✅ 수집 완료

### 1. easylaw.go.kr 이사/주택임대차 콘텐츠 ⭐
| 항목 | 값 |
|---|---|
| 파일 위치 | `procedures/easylaw/` |
| 문서 수 | **53건** (이사 22 + 주택임대차 31) |
| 총 텍스트 | **216,184 chars** |
| 추출된 법 조항 인용 | **572건** |
| 고유 법률명 | **87개** (주택임대차보호법·주민등록법·민법·동물보호법·공동주택관리법 등) |
| 수집 방식 | 웹 스크래핑 (정적 HTML, BeautifulSoup) |
| 스크립트 | `scripts/ingest_easylaw.py`, `ingest_easylaw_lease.py` |

**커버 토픽** 전입신고 · 확정일자 · 대항력 · 우선변제권 · 공과금 정산 · 주소변경 · 등기 · 이사업체 · 분쟁 해결 등

### 2. 도시가스 공급사 매핑 (citygas.or.kr)
| 항목 | 값 |
|---|---|
| 파일 위치 | `mapping/gas_region_company.json`, `procedures/utility/gas_companies.json` |
| 매핑 엔트리 | **35건** |
| 고유 회사 | **34개** (코원에너지, 예스코, 서울도시가스, 삼천리, 대륜E&S, 부산도시가스, 대성에너지 등) |
| 권역 커버리지 | **전국 16개 시·도** (수도권 6개, 강원 5개, 경북 4개, 전북 3개, 전남 3개 ...) |
| 수집 방식 | situation.jsp 스크래핑 |
| 스크립트 | `scripts/ingest_citygas.py` |

### 3. 2026년 공휴일 (data.go.kr 특일정보 API)
| 항목 | 값 |
|---|---|
| 파일 위치 | `raw/holidays_2026.json` |
| 레코드 | **22건** (신정·설·삼일절·어린이날·부처님오신날·노동절·현충일·광복절·추석·개천절·한글날·성탄절 및 대체공휴일) |
| 수집 방식 | 공공데이터포털 API (`DATA_GO_KR_SERVICE_KEY`) |
| 용도 | D-day 계산 시 법정 기한이 공휴일에 걸리면 다음 평일로 밀어주는 로직 |
| 스크립트 | `scripts/ingest_holidays.py` |

---

## ❌ 수집 실패 / 블록됨

### 1. 국가법령정보 API (law.go.kr DRF) — `LAW_OC` 미발급
- **문제** `.env`의 `LAW_OC` 값이 비어있음
- **영향** 주택임대차보호법·주민등록법·동물보호법 등 **법률 원문 직접 수집 불가**
- **완화책** easylaw 콘텐츠에서 관련 법 조항이 **572건 인용되어 있음** → 이걸로 citation grounding은 충분. 원문 본문이 필요하면 OC 발급 후 재수집
- **해결 방법** `open.law.go.kr` 수정 페이지에서 OC 값 확인 → `.env`의 `LAW_OC=` 에 입력 후 재실행

### 2. law.go.kr 공개 HTML 스크래핑
- **문제** `/법령/...` URL이 JavaScript 렌더링 사용. 서버가 보내는 HTML에는 본문 없음 (1~6KB shell)
- **결론** 대안 없음. OC 방식만 가능

### 3. 법제처 찾기쉬운 생활법령정보 API (`apis.data.go.kr/1170000/law/...`)
- **문제** 초기 테스트에서 `404 API not found` 응답
- **우회** easylaw.go.kr **직접 크롤링**으로 대체 — 오히려 더 많은 페이지 확보 (53건)

### 4. 정부24 (gov.kr) 페이지
- **문제** IP 기반 접속 제어 + JavaScript 렌더링 + 대기열 시스템. HTML에 `"서비스 접속이 차단 되었습니다"` 응답
- **우회** easylaw.go.kr 콘텐츠가 정부24 내용을 사실상 포괄 (전입신고·자동차·반려동물 등 다 있음)

### 5. 공공데이터포털 "전국 주민센터 현황" CSV
- **문제** 웹 UI 기반 CSV 다운로드는 로그인+캡차 필요
- **해결 방법** 사용자가 직접 로그인 후 다운 → `data/raw/`에 배치 → 제가 정규화

---

## 🔑 사용된 API 키

| 키 | 상태 | 사용처 |
|---|---|---|
| `DATA_GO_KR_SERVICE_KEY` | ✅ 정상 | 특일정보(공휴일) API |
| `JUSO_API_KEY` | — | 미사용 (런타임 전용) |
| `LAW_OC` | ❌ 미발급 | 국가법령정보 API 블록 원인 |

---

## 📊 데이터 규모 vs 기반 기획서 목표

| 항목 | 목표 | 실제 | 비고 |
|---|---|---|---|
| 법률 원문 청크 (Index A) | 150~250 | **0** (citation만 572건) | LAW_OC 필요 |
| 행정 절차 청크 (Index B) | 30~50 | **53 documents** (≈ 150~300 청크로 분할 예정) | ⭐ 초과 달성 |
| 고유 법률명 | — | **87개** | citation 정답지로 활용 가능 |
| 도시가스 매핑 | 필수 | **35건 / 34회사** | 전국 커버 |
| 공휴일 | 필수 | **22건** | D-day 계산 준비 |

---

## 📁 최종 디렉토리 구조

```
backend/
├── data/
│   ├── COLLECTION_REPORT.md          (← 이 파일)
│   ├── laws/                          (비어 있음, LAW_OC 발급 대기)
│   ├── mapping/
│   │   └── gas_region_company.json   (35 엔트리)
│   ├── procedures/
│   │   ├── easylaw/                   (53 JSON + _summary)
│   │   ├── gov24/                     (비어 있음, 크롤링 실패 → easylaw 대체)
│   │   ├── telecom/                   (비어 있음, 수동 필요)
│   │   └── utility/
│   │       └── gas_companies.json     (34개 공급사)
│   └── raw/
│       └── holidays_2026.json         (22건)
└── scripts/
    ├── ingest_easylaw.py
    ├── ingest_easylaw_lease.py
    ├── ingest_citygas.py
    └── ingest_holidays.py
```

---

## 🧭 다음 단계 제안

### 즉시 가능 (유저 액션 필요)
1. **`LAW_OC` 발급** → `.env`에 입력 → `ingest_laws.py` 작성 후 법률 원문 수집
2. **공공데이터포털 주민센터 CSV** 수동 다운 → `data/raw/`에 배치
3. **통신사 3사 + 우체국 페이지** 수동 복사 → `procedures/telecom/`에 JSON 저장

### 제가 이어서 할 수 있는 것
1. **easylaw 53건을 AI Search 인덱스 B용 청크로 분할** (섹션 단위 청킹 + 메타데이터 부여)
2. **인덱스 스키마 JSON** 작성 (azure.search)
3. **FastAPI 백엔드 스켈레톤** (`POST /checklist`, `POST /safecontract`)
4. **Citation 자동 링크 테이블** 생성 (572건 인용 → 법률명별 그룹핑)

### 검수 필요
- easylaw 53건 중 이사 RAG에 부적합한 페이지(예: 집 구하기 · 경매 · 집 내놓기)는 사용자 판단으로 제외 필요
