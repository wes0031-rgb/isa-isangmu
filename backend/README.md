# 이사이상무 Backend

FastAPI 기반 백엔드. Azure OpenAI + AI Search + Document Intelligence 를 RAG 로 묶어 이사 체크리스트·등기부 해석·챗봇 제공.

---

## 디렉토리 구조

```
backend/
├── app/                    # FastAPI 애플리케이션 (운영 코드)
│   ├── main.py                # FastAPI entry, 라우트 정의
│   ├── config.py              # .env 설정 로딩 (Pydantic Settings)
│   ├── models.py              # Pydantic 요청·응답 스키마
│   ├── azure_clients.py       # Azure SDK 클라이언트 래퍼 (lazy init)
│   ├── chat_service.py        # 챗봇 RAG (AI Search + OpenAI)
│   ├── checklist_service.py   # 체크리스트 4단계 파이프라인
│   ├── safecontract_service.py # 등기부등본 해석 + 위험 판정
│   ├── region_services.py     # 지역별 기관 매핑 (수도·가스·교육청 등)
│   ├── realty_price.py        # 국토부 실거래가 API
│   ├── date_utils.py          # D-day 계산 (공휴일 반영)
│   └── local_search.py        # Azure 미연결 시 로컬 키워드 검색 폴백
├── data/                   # 인덱스·매핑·법령 원본 JSON/JSONL
│   ├── indexes/               # 통합 인덱스 JSONL + 평가 보고서
│   ├── laws/                  # 법령 원본 JSON (주택임대차보호법 등)
│   ├── mapping/               # 지역별 기관 매핑 (수도·가스·전기…)
│   ├── procedures/            # 행정 절차 JSON (easylaw 크롤링)
│   └── raw/                   # 유튜브 스크립트·공휴일 원본
├── scripts/                # 데이터 수집·전처리·인덱싱 스크립트 (19개)
│   └── README.md              # 스크립트 용도별 분류
├── tests/                  # pytest 테스트
│   └── README.md              # 테스트 실행 방법
├── schemas/                # 인덱스 스키마 정의 (Azure AI Search)
├── Dockerfile
├── requirements.txt
└── .env.example            # 환경변수 템플릿
```

---

## API 엔드포인트

| Method | 경로 | 용도 |
|--------|------|------|
| GET | `/` | 서비스 정보 + 엔드포인트 목록 |
| GET | `/health` | 깊은 헬스체크 (Azure 연결·인덱스 상태) |
| POST | `/checklist` | 조건 → AI 맞춤 이사 체크리스트 생성 |
| POST | `/chat` | 챗봇 질문 응답 (RAG + citation) |
| GET | `/chat/presets` | 챗봇 프리셋 질문 리스트 |
| GET | `/realty/summary?region=` | 국토부 실거래가 요약 |
| POST | `/safecontract` | 등기부 텍스트 → 전세 위험 분석 |
| POST | `/safecontract/upload` | 등기부 PDF → Doc Intelligence → 분석 |

---

## 주요 흐름

### 1. 체크리스트 생성 (4단계 RAG)

```
사용자 조건
  │
  ├─ Step 1: build_queries_rule_based → 토글 → 정적 쿼리 (LLM 호출 0회)
  │           + free_text 있으면 build_queries_freetext_llm 추가 (GPT-4o)
  │
  ├─ Step 2: search_procedures → Azure AI Search 통합 인덱스 하이브리드 검색
  │                              (semantic + 벡터, source_type 필터)
  │
  ├─ Step 3: structure_checklist_llm → 항목 JSON 구조화
  │                                    (GPT-4o, json_schema strict)
  │
  └─ Step 4: enrich_item_with_region → 지역별 기관·연락처 주입
                                        (data/mapping/*.json)
```

### 2. SafeContract PDF 분석

```
PDF 업로드
  │
  ├─ Document Intelligence (prebuilt-layout) → 전체 텍스트
  │
  ├─ GPT-4o Structured Output → RegistryExtraction (14개 필드)
  │     · 주소·면적·소유자·근저당·가압류·경매·신탁·가처분…
  │
  ├─ region 자동 파싱 → 국토부 실거래가 API → 시세 자동 조회
  │
  ├─ _compute_ratios → 전세가율·근저당비율·위험도 (green/yellow/red)
  │
  ├─ _search_law_context → 관련 법조문 검색 (AI Search 법률 필터)
  │
  └─ _explain_with_llm → 위험 항목별 쉬운 설명 + citation
```

### 3. 챗봇 (단일 인덱스 시맨틱 RAG)

```
사용자 질문 + 멀티턴 history
  │
  ├─ 도메인 필터 → 인사/오프토픽 거절
  │
  ├─ Azure AI Search `moving-unified-index` 단일 호출
  │     · semantic config: movewise-semantic
  │     · source_type 필터 (law / procedure / video)
  │
  ├─ GPT-4o 답변 생성 (system + history + hits)
  │     · 문장별 [법률]/[절차]/[영상] 태그 부착
  │
  └─ _sanitize_answer → hallucination 방어 (출처에 없는 영상·법률 제거)
```

---

## 로컬 실행

### 1. 의존성 설치

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경변수

`.env.example` 을 `.env` 로 복사 후 필요한 키 채우기:

```bash
cp .env.example .env
# .env 편집
```

Azure 키 없이도 **로컬 폴백 모드** 로 동작 (하드코딩 체크리스트 + 로컬 키워드 검색).

### 3. 서버 기동

```bash
# 개발 모드 (reload 자동)
uvicorn app.main:app --reload --port 8000

# 테스트 후 http://localhost:8000/docs 에서 Swagger UI 확인
```

### 4. 헬스체크

```bash
curl http://localhost:8000/health
```

- `mode: "azure"` = Azure 연결됨
- `mode: "fallback"` = 로컬 폴백 (Azure 미연결)

---

## 환경변수 체크리스트

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `AZURE_OPENAI_ENDPOINT` | ⚠️ | - | Azure OpenAI 엔드포인트 URL |
| `AZURE_OPENAI_API_KEY` | ⚠️ | - | OpenAI 키 (비공개) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | ⚠️ | `gpt-4o` | 배포된 GPT 모델 이름 |
| `AZURE_OPENAI_API_VERSION` | ⚠️ | `2024-10-21` | API 버전 |
| `AZURE_OPENAI_EMBED_DEPLOYMENT` | | `text-embedding-3-small` | 임베딩 모델 (검색 때만) |
| `AZURE_SEARCH_ENDPOINT` | ⚠️ | - | AI Search 엔드포인트 |
| `AZURE_SEARCH_API_KEY` | ⚠️ | - | AI Search 키 (비공개) |
| `AZURE_SEARCH_LAW_INDEX` | | `moving-unified-index` | 법률 인덱스 이름 |
| `AZURE_SEARCH_PROCEDURE_INDEX` | | `moving-unified-index` | 절차 인덱스 (통합이라 동일) |
| `AZURE_DOCINTEL_ENDPOINT` | | - | Document Intelligence (PDF 파싱용) |
| `AZURE_DOCINTEL_API_KEY` | | - | DocIntel 키 (비공개) |
| `AZURE_BLOB_CONNECTION_STRING` | | - | Blob Storage (현재 미사용) |
| `DATA_GO_KR_SERVICE_KEY` | | - | 공공데이터포털 (실거래가 조회용) |
| `LAW_OC` | | - | 국가법령정보 Open API OC 값 |
| `JUSO_API_KEY` | | - | 도로명주소 API |

⚠️ 표시는 Azure 모드로 돌리려면 필수.  
미설정 시 자동으로 로컬 폴백 모드.

---

## 테스트

```bash
# 전체
pytest

# 특정 파일
pytest tests/test_safecontract_service.py

# 특정 테스트
pytest -k "test_compute_ratios_red"
```

자세한 내용: [`tests/README.md`](./tests/README.md)

---

## 데이터 갱신 / 인덱스 재빌드

법령·절차·유튜브 스크립트 수집·청킹·인덱스 업로드 스크립트는 모두 `scripts/` 에.  
실행 순서와 용도: [`scripts/README.md`](./scripts/README.md)

---

## 배포

- **Render** (production): `https://movewise-jf1s.onrender.com`
  - `main` 브랜치 푸시 시 자동 배포
  - 환경변수는 Render 대시보드에서 관리
- Dockerfile: 로컬·CI 빌드용
- 자세한 배포 가이드: 프로젝트 루트 `SETUP.md`

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `/health` 에 `mode: "fallback"` | Azure 키 미설정 또는 잘못됨 | `.env` 확인, `/health` 의 `azure` 블록 어느 게 false 인지 체크 |
| `/checklist` 가 하드코딩 항목만 반환 | LLM 호출 실패 → 폴백 | 로그에서 `structure LLM failed` 확인, OpenAI quota·키 체크 |
| `/safecontract` 전세가율 0% | region 파싱 실패 → 시세 조회 안 됨 | 주소 포맷 확인 (시/도 + 시/군/구 필요), `DATA_GO_KR_SERVICE_KEY` 확인 |
| `/safecontract/upload` 503 | Document Intelligence 미설정 | `AZURE_DOCINTEL_*` 환경변수 채움 |
| 챗봇 답변이 일반적/검색 실패 | Azure AI Search 인덱스 문제 | `/health` 의 `indexes` 청크 수 확인 (0 이면 인덱스 비어있음) |

---

## 기여 가이드

- 브랜치: `main` 직접 푸시 (작은 팀)
- 커밋 컨벤션: `feat:` / `fix:` / `docs:` / `refactor:` 프리픽스
- 코드 스타일: Python PEP 8 + 한글 docstring
- PR 전: `pytest` 통과 확인
