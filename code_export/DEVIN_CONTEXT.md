# Devin AI 작업 컨텍스트 — MoveWise

> Devin AI 또는 다른 코딩 에이전트에게 이 프로젝트를 맡길 때 붙여넣는 컨텍스트 문서.

---

## 🎯 프로젝트 한 줄

**MoveWise** — 이사 후 전입신고·공과금·인터넷까지 개인 상황에 맞춰 AI가 전체 이사 여정을 가이드하는 RAG 기반 모바일 앱 (MSAI09 부트캠프 2차 프로젝트).

## 📂 전체 경로

```
/Users/sa/Desktop/2차프로젝트/
```

이 `code_export/` 폴더는 **데이터·문서를 뺀 코드만** 담은 서브셋입니다.
전체 컨텍스트가 필요하면 부모 경로를 참조하세요.

## 🏗 아키텍처

```
사용자 → Expo 앱 (React Native + TypeScript)
         ↓ HTTPS
         FastAPI (Python 3.12)
         ↓
         ┌──────────────┬──────────────┬──────────────┐
         Azure OpenAI   Azure AI      Document
         (GPT-4o)       Search        Intelligence
                        Index A (법률)
                        Index B (행정 절차)
```

**Fallback 모드**: Azure 미설정 시 자동으로 로컬 키워드 검색 + rule-based 체크리스트로 전환.

## 🧩 주요 모듈

### 백엔드 (`backend/`)

| 파일 | 역할 |
| --- | --- |
| `app/main.py` | FastAPI 엔트리. `POST /checklist`, `POST /safecontract`, `GET /health` |
| `app/config.py` | pydantic-settings로 `.env` 로딩 |
| `app/models.py` | Pydantic 요청·응답 스키마 |
| `app/date_utils.py` | 공휴일 인식 D-day 계산 (`holidays_2026.json` 사용) |
| `app/azure_clients.py` | Azure SDK lazy-init 래퍼 (OpenAI, AI Search, Document Intelligence) |
| `app/local_search.py` | BM25 lite 로컬 키워드 검색 폴백 (index_b_chunks_curated.jsonl 로드) |
| `app/checklist_service.py` | **4단계 RAG 파이프라인** — 쿼리 생성 → 검색 → 구조화 → 날짜 계산 |
| `app/safecontract_service.py` | 등기부 파싱 → 깡통전세 비율 계산 → 법률 RAG 해석 |
| `schemas/index_a_law.json` | Azure AI Search 법률 인덱스 스키마 (HNSW + ko.lucene + semantic) |
| `schemas/index_b_procedure.json` | 행정 절차 인덱스 스키마 (메타 필터용) |
| `scripts/ingest_easylaw*.py` | easylaw.go.kr 이사·주택임대차 카테고리 크롤링 |
| `scripts/ingest_citygas.py` | 한국도시가스협회 회원사 매핑 |
| `scripts/ingest_holidays.py` | 공공데이터포털 특일정보 API |
| `scripts/ingest_laws.py` | 국가법령정보 DRF API (LAW_OC 필요) |
| `scripts/chunk_easylaw.py` | 문서 → 섹션 청크 분할 (메타데이터 자동 추출) |
| `scripts/curate_chunks.py` | 스코프 밖 문서 제외 |
| `scripts/evaluate_checklist.py` | Golden Query 자동 평가 |
| `scripts/upload_to_search.py` | Azure AI Search 인덱스 생성 + 임베딩 업로드 |

### 프론트엔드 (`frontend/movewise-app/`)

React Native + Expo SDK 54 + TypeScript + expo-router v6

| 경로 | 역할 |
| --- | --- |
| `app/_layout.tsx` | 루트 스택 네비게이션 |
| `app/index.tsx` | Splash |
| `app/onboarding.tsx` | 온보딩 |
| `app/(tabs)/index.tsx` | **Home Dashboard** — D-day 카운트다운, 임박 마감일, 진행률 |
| `app/(tabs)/checklist.tsx` | 조건 폼 + 체크리스트 결과 + 체크박스 완료 |
| `app/(tabs)/safecontract.tsx` | 등기부 입력 → 위험 분석 |
| `app/(tabs)/my.tsx` | 설정 (API URL, 사용자 이름, 데이터 초기화) |
| `app/checklist/[id].tsx` | Task Detail — 항목 상세 + 법조항 링크 + 공유 |
| `lib/api.ts` | FastAPI 클라이언트 + TypeScript 타입 (`ChecklistRequest`, `SafeContractResponse` 등) |
| `lib/storage.ts` | AsyncStorage 래퍼 (체크리스트·완료 상태·설정 영속화) |
| `theme/colors.ts` | 디자인 토큰 (#003A75 primary · #1F6FD0 sub · #F5A623 accent) |

## ⚙️ 동작 상태 (2026-04-13 기준)

- ✅ **백엔드** FastAPI fallback 모드로 완전 동작. `http://127.0.0.1:8765`
- ✅ **프론트엔드** Expo 웹 빌드 성공. 4탭 + Task Detail + AsyncStorage 영속화
- ✅ **데이터** 53 문서 / 200 curated chunks / 572 법률 인용 / 34 도시가스 회사 / 공휴일 22건
- ✅ **품질 평가** Golden Query 20/20 perfect · mean recall 1.000
- ✅ **Docker** 백엔드 Dockerfile + docker-compose.yml 작성됨
- ⏳ **LAW_OC** 미발급 → 법률 원문 Index A 비어있음
- ⏳ **Azure 리소스** 미발급 → fallback 모드

## 🔑 환경 변수 (`.env.example` 참고)

- `DATA_GO_KR_SERVICE_KEY` — 공공데이터포털 마스터키 (발급 완료)
- `JUSO_API_KEY` — 도로명주소 (발급 완료)
- `LAW_OC` — 국가법령정보 (미발급)
- `AZURE_OPENAI_*` — 미발급
- `AZURE_SEARCH_*` — 미발급
- `AZURE_DOCINTEL_*` — 미발급
- `AZURE_BLOB_*` — 미발급

## 🚀 실행

```bash
# 백엔드
cd 2차프로젝트
python3 -m uvicorn backend.app.main:app --reload --port 8765

# 프론트엔드 (웹 프리뷰)
cd frontend/movewise-app
npm install
npx expo start --web

# 품질 평가
python3 backend/scripts/evaluate_checklist.py

# Docker
docker compose up --build
```

## 🎯 남은 작업 (Devin이 도와줄 수 있는 것)

### High priority
1. **Azure 리소스 연결** — 환경변수 주입 후 `upload_to_search.py --create-indexes` 실행
2. **LAW_OC 발급 후 법률 원문 수집** — `ingest_laws.py` 실행
3. **Golden Query 확장** — 20 → 30건으로 증가, edge case 커버
4. **프롬프트 튜닝** — `checklist_service.py`의 `QUERY_SYSTEM_PROMPT`, `STRUCTURE_SYSTEM_PROMPT` 실제 LLM으로 돌려 최적화

### Medium priority
5. **SafeContract 프롬프트 개선** — 등기부 Structured Output 스키마 검증
6. **에러 핸들링** — 백엔드 에러 리커버리, 프론트 재시도 UI
7. **테스트** — pytest 단위 테스트, Expo jest 설정
8. **CI/CD** — GitHub Actions (lint + test + type check)

### Low priority
9. **Streamlit 데모 업그레이드** — 발표용 개선
10. **아이콘/스플래시 에셋** — 스티치 목업 기반 이미지 생성
11. **i18n** — 영어 지원 (Phase 2 AI 윤리 포용성)
12. **PDF 내보내기** — 체크리스트 PDF 생성

## 📚 문서

| 파일 | 내용 |
| --- | --- |
| `README.md` | 이 프로젝트 개요 |
| `DEPLOYMENT.md` | Azure App Service / Render / Fly / Docker 배포 옵션 |
| `.env.example` | 환경변수 템플릿 |
| 부모 경로의 `README.md` | 전체 README (더 자세함) |
| 부모 경로의 `기반_기획서.md` | 원본 PRD (유저 전달본) |
| 부모 경로의 `notion_share/` | 팀 공유용 문서 11종 |
| 부모 경로의 `backend/data/COLLECTION_REPORT.md` | 데이터 수집 결과 |
| 부모 경로의 `backend/data/indexes/evaluation_report.json` | 품질 평가 상세 |

## 🧪 품질 확인 명령어

```bash
# 백엔드 헬스
curl http://127.0.0.1:8765/

# 체크리스트 생성
curl -X POST http://127.0.0.1:8765/checklist \
  -H "Content-Type: application/json" \
  -d '{"household":"자취","contract":"월세","region":"경기도 성남시 분당구","move_date":"2026-05-01","has_pet":true,"has_car":false,"has_children":false}'

# SafeContract
curl -X POST http://127.0.0.1:8765/safecontract \
  -H "Content-Type: application/json" \
  -d '{"text":"[을구] 근저당권설정 금 2억4천만원","deposit_krw":100000000,"expected_market_price_krw":300000000}'

# Golden Query 평가
python3 backend/scripts/evaluate_checklist.py

# TypeScript 체크
cd frontend/movewise-app && npx tsc --noEmit
```

## 💬 Devin에게 작업 지시 예시

> "`/Users/sa/Desktop/2차프로젝트/code_export/` 폴더의 코드를 분석하고,
> Azure OpenAI 환경변수를 설정한 뒤 `backend/app/checklist_service.py`의
> LLM 프롬프트를 최적화해줘. 평가는 `backend/scripts/evaluate_checklist.py`로
> 돌리고, mean recall 1.0을 유지하면서 citation coverage를 0.95 → 0.99로
> 끌어올리는 것이 목표."
