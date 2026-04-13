# MoveWise — MSAI09 2차 프로젝트

> **이사 후 전입신고·공과금·인터넷까지, 개인 상황에 맞춰 AI가 전체 이사 여정을 한 곳에서 가이드**

| 항목 | 내용 |
| --- | --- |
| 프로젝트명 | **MoveWise** |
| 과정 | MSAI09 부트캠프 2차 프로젝트 |
| 작성일 | 2026-04-13 |
| 필수 Azure 서비스 | OpenAI · AI Search · Document Intelligence · Blob Storage · App Service |
| 지역 범위 | **전국** |
| 상태 | 데이터 수집 · 청킹 · 백엔드 · 프론트엔드 스켈레톤 완료. Azure 리소스 대기 중 |

---

## 📖 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [디렉토리 구조](#3-디렉토리-구조)
4. [기술 스택](#4-기술-스택)
5. [로컬 개발 환경 세팅](#5-로컬-개발-환경-세팅)
6. [실행 방법](#6-실행-방법)
7. [API 엔드포인트](#7-api-엔드포인트)
8. [데이터 수집 스크립트](#8-데이터-수집-스크립트)
9. [품질 지표](#9-품질-지표-2026-04-13-기준)
10. [현재 공유 링크](#10-현재-공유-링크)
11. [팀 역할 분담 제안](#11-팀-역할-분담-제안)
12. [다음 단계 TODO](#12-다음-단계-todo)
13. [참고 문서](#13-참고-문서)

---

## 1. 프로젝트 개요

### 핵심 기능 (메인)
**RAG 기반 개인화 이사 체크리스트** — 사용자가 세대 유형·계약 유형·지역·이사 날짜·조건(반려동물·자동차·자녀 등)을 입력하면 LLM이 Azure AI Search에서 행정 절차 문서를 검색하여 D-day 기준 타임라인으로 체크리스트를 생성합니다. 각 항목에는 법률 조항 citation이 첨부됩니다.

### 부가 기능 (SafeContract)
**등기부등본 해석기** — 등기부등본 텍스트를 입력하면 LLM이 갑구/을구의 위험 요소(근저당·가압류·신탁·경매)를 추출하고, Python이 깡통전세 비율을 계산하며, 주택임대차보호법 RAG를 통해 쉬운 말 해석과 기존 서비스(HUG·인터넷등기소 등) 안내를 생성합니다.

### 스코어링 제외 결정
Rule-based 위험도 점수는 **제외**했습니다. 가중치 산정에 부동산 도메인 전문성이 필요하고, 근거 없는 수치는 사용자에게 잘못된 판단 근거를 제공할 수 있기 때문입니다. AI 윤리 6대 원칙 중 **책임성**·**신뢰성** 구현의 일환입니다.

---

## 2. 시스템 아키텍처

![System Architecture](movewise_architecture.png)

```
사용자 ──HTTPS──► FastAPI (/checklist, /safecontract)
                    │
                    ├──► Azure OpenAI (쿼리 생성 · 구조화 · 해석)
                    ├──► Azure AI Search
                    │      ├─ Index A (법률 조문)
                    │      └─ Index B (행정 절차)
                    ├──► Document Intelligence (등기부 PDF OCR)
                    └──► Blob Storage (원본 저장)

[배치] 국가법령 API / 생활법령 API / 정부24 ──► ingest_*.py ──► Blob ──► DocIntel ──► Indexes
```

소스: `architecture.py` (재생성 가능)

---

## 3. 디렉토리 구조

```
2차프로젝트/
├── README.md                         (← 이 파일)
├── 기반_기획서.md                     유저 직접 전달 원본 기획서 (수정 금지)
├── architecture.py                   아키텍처 다이어그램 소스
├── movewise_architecture.png         생성된 다이어그램
├── .env                              🔒 API 키 (git 제외 필수)
│
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                   FastAPI 엔트리 (GET / · POST /checklist · POST /safecontract)
│   │   ├── config.py                 pydantic-settings 기반 .env 로딩
│   │   ├── models.py                 Pydantic 요청·응답 모델
│   │   ├── date_utils.py             공휴일 인식 D-day 계산
│   │   ├── azure_clients.py          Azure SDK 래퍼 (lazy init)
│   │   ├── local_search.py           로컬 키워드 검색 폴백 (Azure 없을 때)
│   │   ├── checklist_service.py      4단계 RAG 파이프라인
│   │   └── safecontract_service.py   등기부 추출·계산·해석
│   │
│   ├── schemas/
│   │   ├── index_a_law.json          Azure AI Search 법률 인덱스 스키마
│   │   └── index_b_procedure.json    Azure AI Search 절차 인덱스 스키마
│   │
│   ├── scripts/
│   │   ├── ingest_easylaw.py         easylaw 이사 카테고리 22건 수집
│   │   ├── ingest_easylaw_lease.py   easylaw 주택임대차 31건 수집
│   │   ├── ingest_citygas.py         도시가스 공급사 매핑 (전국 35건)
│   │   ├── ingest_holidays.py        2026 공휴일 API 호출
│   │   ├── ingest_laws.py            ⏳ LAW_OC 대기, 법률 원문 8종 수집
│   │   ├── chunk_easylaw.py          53 docs → 361 청크 분할
│   │   ├── curate_chunks.py          361 → 200 청크 큐레이션
│   │   ├── evaluate_checklist.py     Golden Query 20건 자동 평가
│   │   └── upload_to_search.py       ⏳ Azure 대기, 인덱스 생성·업로드
│   │
│   └── data/
│       ├── COLLECTION_REPORT.md      수집 결과 리포트
│       ├── CURATION_PROPOSAL.md      문서 큐레이션 제안 (유저 검수용)
│       ├── laws/                     (⏳ 비어 있음 — LAW_OC 대기)
│       ├── mapping/
│       │   └── gas_region_company.json
│       ├── procedures/
│       │   ├── easylaw/              53 JSON (이사 22 + 주택임대차 31)
│       │   ├── gov24/                (비어 있음)
│       │   ├── telecom/              (비어 있음)
│       │   └── utility/gas_companies.json
│       ├── raw/
│       │   └── holidays_2026.json    2026 공휴일 22건
│       └── indexes/
│           ├── index_b_chunks.jsonl              원본 청크 361건
│           ├── index_b_chunks_curated.jsonl      큐레이션 후 200건
│           ├── index_b_summary.json
│           ├── index_b_curated_summary.json
│           ├── golden_queries.json               20 시나리오
│           └── evaluation_report.json            20/20 perfect 기록
│
└── frontend/
    ├── streamlit_app.py              파이썬 데모 UI (빠른 확인용)
    └── movewise-app/                 React Native + Expo 앱
        ├── app/                      expo-router 라우트
        │   ├── _layout.tsx           루트 스택
        │   ├── index.tsx             Splash
        │   ├── onboarding.tsx        온보딩
        │   └── (tabs)/
        │       ├── _layout.tsx       4-tab 네비게이션
        │       ├── index.tsx         Home Dashboard
        │       ├── checklist.tsx     체크리스트 폼 + 결과
        │       ├── safecontract.tsx  SafeContract
        │       └── my.tsx            MY 페이지
        ├── lib/api.ts                FastAPI 클라이언트 + 타입
        ├── theme/colors.ts           디자인 토큰
        └── package.json
```

---

## 4. 기술 스택

| 계층 | 기술 |
| --- | --- |
| 백엔드 | Python 3.14 · FastAPI · Pydantic v2 · httpx · BeautifulSoup4 |
| LLM | Azure OpenAI (GPT-4o) — 설정되어 있지 않으면 rule-based + local search 폴백 |
| 검색 | Azure AI Search (hnsw vector + ko.lucene + semantic) — 설정 전엔 `local_search.py` (BM25 lite) |
| 문서 처리 | Azure Document Intelligence (등기부 PDF/사진 OCR) |
| 데이터 소스 | 국가법령정보 공동활용 API · 찾기쉬운 생활법령정보 (웹) · 한국도시가스협회 · 공공데이터포털(특일정보) |
| 프론트엔드 | React Native + Expo SDK 54 + expo-router v6 · TypeScript · @expo/vector-icons |
| 추가 UI | Streamlit (파이썬 데모) |
| 배포 (MVP) | Azure App Service (계획) · 현재는 Cloudflare Quick Tunnel 임시 공유 |
| 다이어그램 | `diagrams` (Python) + Graphviz |

---

## 5. 로컬 개발 환경 세팅

### 5.1 사전 요구 사항

```bash
python3 --version   # 3.11 이상
node --version      # 20 이상
npm --version       # 10 이상

# macOS 기준 graphviz (아키텍처 다이어그램 재생성 시에만)
brew install graphviz
```

### 5.2 저장소 받기

현재 로컬 디렉토리는 `~/Desktop/2차프로젝트/` 입니다. Git 저장소를 만들 때는 반드시 `.gitignore`에 다음을 포함:

```
.env
.env.*
backend/data/samples/
backend/data/laws/*.json
node_modules/
__pycache__/
*.pyc
```

### 5.3 `.env` 설정

`.env` 템플릿 (팀에 공유된 `.env.team` 참조):

```bash
# 발급 완료 (공유)
DATA_GO_KR_SERVICE_KEY=<공공데이터포털 마스터키>
JUSO_API_KEY=<도로명주소 API 키>

# ⏳ 발급 필요
LAW_OC=                       # open.law.go.kr 마이페이지 → OC 확인
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small

AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_LAW_INDEX=moving-law-index
AZURE_SEARCH_PROCEDURE_INDEX=moving-procedure-index

AZURE_DOCINTEL_ENDPOINT=
AZURE_DOCINTEL_API_KEY=

AZURE_BLOB_CONNECTION_STRING=
AZURE_BLOB_CONTAINER_NAME=moving-guide-docs
```

### 5.4 Python 의존성

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

필수 패키지:
```
fastapi · uvicorn · pydantic · pydantic-settings · python-dotenv
httpx · openai · azure-search-documents · azure-ai-documentintelligence · azure-storage-blob
```

### 5.5 Node 의존성

```bash
cd frontend/movewise-app
npm install
```

---

## 6. 실행 방법

### 6.1 FastAPI 백엔드

```bash
cd 2차프로젝트
python3 -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8765
```

- Swagger UI: http://127.0.0.1:8765/docs
- Health: http://127.0.0.1:8765/health
- Root: http://127.0.0.1:8765/

Azure 키가 없으면 `azure_ready: false`로 표시되고 자동으로 **local fallback** (rule-based 체크리스트 + 로컬 키워드 검색)으로 동작합니다. 실제 데이터(200 청크)를 사용하여 응답합니다.

### 6.2 Streamlit 데모 (파이썬 UI)

```bash
cd 2차프로젝트
streamlit run frontend/streamlit_app.py
```

기본 포트 8501. 사이드바에서 백엔드 URL 변경 가능.

### 6.3 Expo 앱 (React Native)

```bash
cd frontend/movewise-app

# 웹 브라우저 (가장 빠른 확인)
npx expo start --web

# iOS 시뮬레이터 (Xcode 필요)
npx expo start --ios

# Android 에뮬레이터 (Android Studio 필요)
npx expo start --android

# 실제 폰 (Expo Go 앱 설치 후 QR 스캔)
npx expo start
```

**백엔드 URL 변경** — 기본은 `http://127.0.0.1:8765`. 다른 URL을 쓰려면:

```bash
EXPO_PUBLIC_API_URL=https://your-backend.example.com npx expo start --web
```

### 6.4 팀원과 공유 (Cloudflare Quick Tunnel)

1. 백엔드 터널

   ```bash
   cloudflared tunnel --url http://127.0.0.1:8765
   ```
   → `https://<random>.trycloudflare.com` URL 출력. 복사.

2. 프론트엔드 재기동 (백엔드 터널 URL 주입)

   ```bash
   cd frontend/movewise-app
   EXPO_PUBLIC_API_URL="https://<backend-tunnel>.trycloudflare.com" \
     npx expo start --web --port 19006
   ```

3. 프론트엔드 터널

   ```bash
   cloudflared tunnel --url http://127.0.0.1:19006
   ```
   → 팀원에게 이 URL을 공유.

⚠️ `trycloudflare.com`은 Mac 켜놓은 동안만 유지됩니다. 영구 링크가 필요하면 Cloudflare Tunnel 계정 터널 또는 Azure App Service 배포로 전환해야 합니다.

---

## 7. API 엔드포인트

### `GET /`

서비스 상태 확인.

**응답**
```json
{
  "service": "MoveWise",
  "version": "0.1.0",
  "azure_ready": false,
  "endpoints": ["/checklist", "/safecontract"]
}
```

### `GET /health`

```json
{ "status": "ok" }
```

### `POST /checklist`

**요청**
```json
{
  "household": "자취",
  "contract": "월세",
  "region": "경기도 성남시 분당구",
  "move_date": "2026-05-01",
  "has_pet": true,
  "has_car": false,
  "has_children": false,
  "children_school_level": null,
  "is_foreigner": false,
  "special_concerns": []
}
```

**응답 (요약)**
```json
{
  "total_items": 9,
  "used_queries": ["전입신고 방법", "확정일자 월세", ...],
  "items": [
    {
      "category": "전입신고",
      "title": "전입신고",
      "description": "이사한 날부터 14일 이내에 ...",
      "d_day_offset": 1,
      "start_date": "2026-05-04",
      "has_legal_deadline": true,
      "deadline_date": "2026-05-15",
      "deadline_days": 14,
      "penalty": "5만원 이하 과태료",
      "method": "정부24 온라인 또는 주민센터 방문",
      "citations": [
        { "law_name": "주민등록법", "article": "제16조" }
      ]
    },
    ...
  ],
  "warning": "Azure 자격 증명이 설정되지 않아 rule-based fallback 결과입니다."
}
```

### `POST /safecontract`

**요청**
```json
{
  "text": "[갑구] 1. 2020.05.12 소유권이전 김철수 ... [을구] 1. 2021.03.05 근저당권설정 채권최고액 금 2억4천만원 ...",
  "deposit_krw": 100000000,
  "expected_market_price_krw": 300000000
}
```

**응답 (요약)**
```json
{
  "extraction": {
    "mortgage_claim_amount_krw": 240000000,
    "seizure_count": 1,
    "auction_in_progress": true,
    ...
  },
  "jeontse_ratio": 0.887,
  "summary": "🟡 부채비율 주의",
  "risks": [
    {
      "severity": "red",
      "label": "가압류 1건",
      "explanation_plain": "가압류는 채권자가 집주인 재산을 묶어둔 것입니다. ...",
      "related_laws": [...]
    }
  ],
  "referrals": [
    {"icon": "🏛️", "name": "HUG 안심전세 앱", "url": "...", "description": "..."}
  ],
  "disclaimer": "이 서비스는 법률 자문이 아닌 참고용 ..."
}
```

---

## 8. 데이터 수집 스크립트

각 스크립트는 독립 실행 가능. 실행 순서는 다음과 같음:

| 순서 | 스크립트 | 내용 | 실행 여부 |
| --- | --- | --- | --- |
| 1 | `ingest_easylaw.py` | easylaw 이사 카테고리 22건 → `data/procedures/easylaw/` | ✅ 실행됨 |
| 2 | `ingest_easylaw_lease.py` | easylaw 주택임대차 31건 → 같은 폴더 | ✅ |
| 3 | `ingest_citygas.py` | 도시가스 공급사 → `data/mapping/gas_region_company.json` | ✅ |
| 4 | `ingest_holidays.py` | 2026 공휴일 → `data/raw/holidays_2026.json` | ✅ |
| 5 | `chunk_easylaw.py` | 문서를 섹션 청크로 분할 → `data/indexes/index_b_chunks.jsonl` (361 청크) | ✅ |
| 6 | `curate_chunks.py` | 스코프 밖 문서 제외 → `data/indexes/index_b_chunks_curated.jsonl` (200 청크) | ✅ |
| 7 | `evaluate_checklist.py` | Golden Query 20건 자동 평가 → `evaluation_report.json` | ✅ **mean recall 1.000** |
| 8 | `ingest_laws.py` | 국가법령 DRF API → `data/laws/*.json` + `index_a_chunks.jsonl` | ⏳ LAW_OC 대기 |
| 9 | `upload_to_search.py` | Azure AI Search 인덱스 생성 + 청크 업로드 (embeddings 포함) | ⏳ Azure 대기 |

### 재실행
모든 스크립트는 멱등적(같은 파일 덮어쓰기)입니다. 수집 업데이트가 필요하면 같은 순서로 재실행.

---

## 9. 품질 지표 (2026-04-13 기준)

Golden Query 20건에 대한 평가 결과 (로컬 폴백 모드):

| 지표 | 값 |
| --- | --- |
| **mean recall** | **1.000** (20/20 모든 쿼리가 expected 카테고리 100% 커버) |
| mean citation coverage | 0.950 |
| mean deadline accuracy | 0.775 |
| must-not violations | 0 |
| perfect queries | **20/20** |

상세: `backend/data/indexes/evaluation_report.json`

> Azure OpenAI + AI Search 연결 후 재평가하여 rule-based vs LLM vs RAG 3-way 비교가 가능합니다 (기반 기획서 § 10 실험 3).

---

## 10. 현재 공유 링크

> ⚠️ Cloudflare Quick Tunnel이라 Mac이 켜져 있는 동안만 유효합니다.

| 서비스 | URL |
| --- | --- |
| 프론트엔드 (팀 공유용) | `https://plots-discovered-monte-produces.trycloudflare.com` |
| 백엔드 (내부 호출) | `https://habitat-surrounded-websites-accessible.trycloudflare.com` |

터널이 끊어지면 위 [6.4 Cloudflare Quick Tunnel](#64-팀원과-공유-cloudflare-quick-tunnel) 절차를 다시 수행.

---

## 11. 팀 역할 분담 제안

| 담당 | 주요 작업 | 관련 파일 |
| --- | --- | --- |
| **#1 PM / 기획** | 기반 기획서 관리, 큐레이션 검수, 발표 스토리 | `기반_기획서.md`, `CURATION_PROPOSAL.md` |
| **#2 데이터 엔지니어** | 수집 스크립트, Azure Search 인덱싱, 청킹 최적화 | `backend/scripts/*` |
| **#3 RAG / 백엔드** | FastAPI, 4단계 파이프라인, 프롬프트 튜닝 | `backend/app/*` |
| **#4 SafeContract** | 등기부 추출 로직, Structured Output 프롬프트 | `backend/app/safecontract_service.py`, `app/(tabs)/safecontract.tsx` |
| **#5 프론트엔드** | Expo 앱 디자인, 스티치 목업 구현 | `frontend/movewise-app/*` |
| **#6 QA / 평가 / 발표** | Golden Query 확장, 경쟁 분석 슬라이드, 데모 페르소나 | `evaluate_checklist.py`, `golden_queries.json` |

---

## 12. 다음 단계 TODO

### 🔴 High (블록 중)

- [ ] **`LAW_OC` 발급** — `open.law.go.kr` 마이페이지 → `.env`에 입력 → `python3 backend/scripts/ingest_laws.py` 실행
- [ ] **Azure 리소스 5종 발급** — Azure Portal에서 OpenAI · AI Search · Document Intelligence · Blob · App Service 생성
- [ ] **`upload_to_search.py` 실행** — 인덱스 A/B 생성 및 200+ 청크 업로드

### 🟡 Medium

- [ ] `CURATION_PROPOSAL.md` 유저 검수 (🟡 카테고리 중 제외할 것 확정)
- [ ] `golden_queries.json` 팀 검수 (20건 시나리오 적절성)
- [ ] 프론트엔드 스티치 목업 그대로 재현 (Home Dashboard D-day 카운트다운, Task Detail)
- [ ] 등기부등본 샘플 10건 발급 (`iros.go.kr` 유료 ~7,000원)
- [ ] 발표자료 작성 (경쟁 분석 → 빈 칸 → 솔루션 → 라이브 데모)

### 🟢 Low

- [ ] 외국인·접근성 (Phase 2)
- [ ] 실거래가 API 연동 (Phase 2)
- [ ] 백엔드 pytest 추가
- [ ] Expo EAS Build로 실제 앱 배포

---

## 13. 참고 문서

| 파일 | 내용 |
| --- | --- |
| `기반_기획서.md` | 유저 전달 원본 기획서 — 13개 섹션, RAG 파이프라인, 인덱스 설계, 평가 기준 |
| `backend/data/COLLECTION_REPORT.md` | 수집 결과 상세 (53 docs, 572 citations, 87 laws) |
| `backend/data/CURATION_PROPOSAL.md` | 🟢 Core 10 / 🟡 Useful 26 / 🔴 Out 17 분류 |
| `backend/data/indexes/evaluation_report.json` | 품질 평가 20건 상세 |
| `movewise_architecture.png` | 시스템 아키텍처 다이어그램 |
| `architecture.py` | 다이어그램 재생성 스크립트 |

---

## 🔗 참고 링크

- **국가법령정보 공동활용**: https://open.law.go.kr
- **찾기쉬운 생활법령정보**: https://easylaw.go.kr
- **공공데이터포털**: https://www.data.go.kr
- **Azure Portal**: https://portal.azure.com
- **Expo Router 문서**: https://docs.expo.dev/router/introduction/
- **Azure AI Search 문서**: https://learn.microsoft.com/azure/search/

---

## 🏷 AI 윤리 6대 원칙 (MVP 구현)

| 원칙 | 구현 |
| --- | --- |
| 투명성 | 체크리스트 각 항목에 법 조항 citation 표시, 시스템 프롬프트 공개 |
| 책임성 | 면책 고지 상시 표시, 스코어링 제외 판단 자체가 구현, 기존 서비스 연결 |
| 신뢰성·안전성 | 타임스탬프 `last_updated` 필드, 입력 검증, 판단 불가 시 "확인 필요" |
| 개인정보 보호 | 등기부 원문 즉시 파기, 비로그인 사용 가능 |
| 공정성 | 지역·건물 유형 기준 통일, 주택임대차보호법 기준 명시 |
| 포용성 (Phase 2) | 영어·스크린리더·큰글씨 모드 |

---

**© 2026 MSAI09 2차 프로젝트 · MoveWise**
