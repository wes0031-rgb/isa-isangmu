# MoveWise — Code Export

이사 여정 가이드 앱의 **코드만** 담긴 폴더입니다. 데이터·문서는 제외됐습니다.

> 문서가 필요하면 별도 폴더(`notion_share/`) 참고.

---

## 📁 구조

```
code_export/
├── .env.example                  환경변수 템플릿
├── .gitignore                    Git 제외 규칙
├── architecture.py               아키텍처 다이어그램 소스 (diagrams + graphviz)
│
├── backend/
│   ├── requirements.txt
│   ├── app/                      FastAPI 애플리케이션
│   │   ├── __init__.py
│   │   ├── main.py               엔트리 포인트 (POST /checklist · /safecontract)
│   │   ├── config.py             pydantic-settings 기반 .env 로더
│   │   ├── models.py             Pydantic 요청·응답 모델
│   │   ├── date_utils.py         공휴일 인식 D-day 계산
│   │   ├── azure_clients.py      Azure SDK lazy-init 래퍼
│   │   ├── local_search.py       로컬 키워드 검색 폴백 (Azure 없을 때)
│   │   ├── checklist_service.py  4단계 RAG 파이프라인
│   │   └── safecontract_service.py 등기부 추출·계산·해석
│   │
│   ├── schemas/                  Azure AI Search 인덱스 스키마
│   │   ├── index_a_law.json      법률 조문 인덱스
│   │   └── index_b_procedure.json 행정 절차 인덱스
│   │
│   └── scripts/                  데이터 파이프라인 스크립트
│       ├── ingest_easylaw.py         easylaw 이사 카테고리 크롤링
│       ├── ingest_easylaw_lease.py   easylaw 주택임대차 카테고리 크롤링
│       ├── ingest_citygas.py         도시가스 공급사 매핑
│       ├── ingest_holidays.py        2026 공휴일 API
│       ├── ingest_laws.py            국가법령정보 DRF API (LAW_OC 필요)
│       ├── chunk_easylaw.py          문서 → 섹션 청크 분할
│       ├── curate_chunks.py          스코프 밖 문서 필터링
│       ├── evaluate_checklist.py     Golden Query 자동 평가
│       └── upload_to_search.py       Azure AI Search 인덱싱 + 업로드
│
└── frontend/
    ├── streamlit_app.py          파이썬 데모 UI (빠른 확인)
    └── movewise-app/             React Native + Expo 앱
        ├── app.json              Expo 설정
        ├── package.json          의존성 선언
        ├── tsconfig.json         TypeScript 설정
        ├── app/                  expo-router 라우트
        │   ├── _layout.tsx       루트 스택
        │   ├── index.tsx         Splash
        │   ├── onboarding.tsx    온보딩
        │   └── (tabs)/
        │       ├── _layout.tsx   4-tab 네비게이션
        │       ├── index.tsx     Home Dashboard
        │       ├── checklist.tsx 체크리스트 폼 + 결과
        │       ├── safecontract.tsx SafeContract
        │       └── my.tsx        MY 페이지
        ├── lib/
        │   └── api.ts            FastAPI 클라이언트 + TypeScript 타입
        └── theme/
            └── colors.ts         디자인 토큰
```

---

## 🚀 실행

### 1) 환경 변수 설정

```bash
cp .env.example .env
# 에디터로 .env 열어서 각 키 입력
```

### 2) Python 의존성

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Node 의존성

```bash
cd frontend/movewise-app
npm install
```

### 4) 백엔드 실행

```bash
# 프로젝트 루트에서
python3 -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8765
```

→ http://127.0.0.1:8765/docs

### 5) 앱 실행

```bash
cd frontend/movewise-app
npx expo start --web       # 브라우저
npx expo start --ios       # iOS 시뮬레이터
npx expo start --android   # Android 에뮬레이터
npx expo start             # 실기기 Expo Go
```

### 6) 데이터 수집 (옵션)

데이터 파일은 이 export에 포함되지 않았습니다. 재수집이 필요하면:

```bash
python3 backend/scripts/ingest_easylaw.py         # 이사 카테고리 22건
python3 backend/scripts/ingest_easylaw_lease.py   # 주택임대차 31건
python3 backend/scripts/ingest_citygas.py         # 도시가스 매핑
python3 backend/scripts/ingest_holidays.py        # 공휴일
python3 backend/scripts/chunk_easylaw.py          # 청킹
python3 backend/scripts/curate_chunks.py          # 큐레이션
python3 backend/scripts/evaluate_checklist.py     # 품질 평가

# LAW_OC 발급 후
python3 backend/scripts/ingest_laws.py            # 법률 원문

# Azure 리소스 발급 후
python3 backend/scripts/upload_to_search.py --create-indexes
```

---

## 🔌 API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/` | 서비스 상태 |
| `GET` | `/health` | 헬스체크 |
| `POST` | `/checklist` | 개인화 체크리스트 생성 |
| `POST` | `/safecontract` | 등기부등본 해석 |

상세 스키마는 `backend/app/models.py` 또는 Swagger UI (`/docs`) 참고.

---

## ⚙️ 동작 모드

### Azure 모드 (프로덕션)
`.env`에 Azure 키가 채워지면 자동으로:
- Azure OpenAI (쿼리 생성 · 구조화 · 해석)
- Azure AI Search (하이브리드 검색 + 시맨틱 랭킹)
- Document Intelligence (등기부 OCR)

### Local fallback 모드 (개발용)
Azure 키가 없으면 자동으로:
- Rule-based 쿼리 생성 (`checklist_service.build_queries_rule_based`)
- 로컬 키워드 검색 (`local_search.py`, BM25 lite)
- 정규식 기반 등기부 추출 (`_extract_rule_based`)

**폴백 모드에서도 Golden Query 20건 기준 recall 1.000 달성** (조건에 데이터 있을 때).
