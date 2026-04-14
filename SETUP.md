# 이사이상무 — Azure 연결 셋업 가이드

> 이 문서 하나만 따라가면 팀원이 로컬에서 Azure 5종을 연결해 `azure_ready=true` 상태까지 완성합니다.

---

## 📍 현재 상태 (2026-04-13 기준)

- **백엔드**: FastAPI + RAG fallback 모드 **Live** (https://movewise-jf1s.onrender.com)
- **프론트엔드**: Expo SDK 55 앱 (4탭 + Document Intelligence PDF 업로드 스켈레톤)
- **데이터**: Index A 법률 1,950 조문 + Index B 행정 절차 200 청크 (한자 전부 제거됨)
- **품질**: Golden Query 30/30 perfect · pytest 30 passed · smoke test 5/5
- **남은 작업**: **Azure 5종 리소스 연결만** (코드는 lazy-init 준비 완료)

---

## 🧰 사전 요구사항

- **Python 3.12+** 및 `pip`
- **Git** — 레포 clone
- **Azure 구독** — `대한상공회의소 AI School` 구독에 Contributor 권한
- **본인 팀 리소스 그룹** — 예: `9ai-2nd-team5` (학원 운영자가 미리 생성해줘야 함)
- (선택) **Azure CLI** `az` — Portal 대신 CLI 로 작업할 때

**⚠️ 주의:** 다른 팀 리소스 그룹(`9ai-2nd-team4` 등)은 절대 건드리지 않는다.

---

## 🚀 Step 1 — 레포 clone + 의존성 설치

```bash
git clone https://github.com/wes0031-rgb/isa-isangmu.git
cd isa-isangmu

# Python 의존성
pip install -r backend/requirements.txt --break-system-packages --user

# 로컬 백엔드 부팅 검증 (fallback 모드)
python3 -m uvicorn backend.app.main:app --port 8765 --reload &
curl http://127.0.0.1:8765/
# → {"service":"이사이상무", ..., "azure_ready":false}   ← fallback 모드 정상
```

---

## 🏗 Step 2 — Azure 리소스 5종 생성

### 생성 대상 및 권장 SKU

| 서비스 | 리전 권장 | SKU | 용도 |
|---|---|---|---|
| **Azure OpenAI** | East US 2 또는 Korea Central | S0 | GPT-4o 체크리스트 생성, 임베딩 |
| └ GPT-4o 배포 | — | 10K TPM 이상 | 쿼리 변환, 체크리스트 구조화 |
| └ text-embedding-3-small 배포 | — | 120K TPM 이상 | 문서 임베딩 |
| **Azure AI Search** | Korea Central | **Standard S1** | 벡터+세만틱 검색 |
| **Document Intelligence** | East US 또는 Korea Central | S0 | 등기부 PDF 파싱 |
| **Blob Storage** (선택) | Korea Central | Standard LRS | 원본 문서 저장 |
| **App Service** (선택) | Korea Central | B1 | Render 대신 프로덕션 |

### ⚠️ 꼭 지킬 것

1. **AI Search 는 Standard S1 필수** — Free 티어는 벡터 검색 제한으로 실패함
2. **임베딩 모델은 `text-embedding-3-small`** — 차원 1536이 기본 스키마와 호환
   - `-large` 를 쓰면 3072차원이라 `backend/schemas/index_*.json` 의 `dimensions` 필드 수정 필요
3. **GPT-4o quota 거부 시** East US 2 → East US → Sweden Central 순으로 리전 시도
4. **배포명(Deployment name)** 을 `.env` 에 정확히 복사 (`gpt-4o`, `text-embedding-3-small`)

### 생성 순서

1. 본인 팀 리소스 그룹 안에서 **Azure OpenAI** 생성 → 배포 2개 (`gpt-4o`, `text-embedding-3-small`)
2. **AI Search** 생성 (Standard S1)
3. **Document Intelligence** 생성 (SafeContract PDF 파싱용)
4. (선택) **Blob Storage** 생성

각 리소스에서 **Keys and Endpoint** 페이지로 가서 키/엔드포인트 복사.

---

## 🔐 Step 3 — `.env` 파일 작성

```bash
cp .env.example .env
```

`.env` 를 편집해서 다음 값을 채운다:

```bash
# ===== 기존 공공데이터 API (팀장에게 받기) =====
DATA_GO_KR_SERVICE_KEY=<팀장에게 받기>
JUSO_API_KEY=<팀장에게 받기>
LAW_OC=msai09sa

# ===== Azure OpenAI (필수) =====
AZURE_OPENAI_ENDPOINT=https://<리소스이름>.openai.azure.com/
AZURE_OPENAI_API_KEY=<Portal → Keys and Endpoint → Key 1>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o                    # 본인 배포명
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small   # 본인 임베딩 배포명

# ===== Azure AI Search (필수) =====
AZURE_SEARCH_ENDPOINT=https://<리소스이름>.search.windows.net
AZURE_SEARCH_API_KEY=<Portal → Keys → Primary admin key>
AZURE_SEARCH_LAW_INDEX=moving-law-index
AZURE_SEARCH_PROCEDURE_INDEX=moving-procedure-index

# ===== Azure Document Intelligence (선택, SafeContract PDF 업로드용) =====
AZURE_DOCINTEL_ENDPOINT=https://<리소스이름>.cognitiveservices.azure.com/
AZURE_DOCINTEL_API_KEY=<Portal → Keys and Endpoint>

# ===== Azure Blob Storage (선택) =====
AZURE_BLOB_CONNECTION_STRING=
AZURE_BLOB_CONTAINER_NAME=moving-guide-docs
```

**⚠️ Admin key 이어야 함** — Search 는 Query Key 가 아니라 Primary admin key 를 써야 인덱스 생성이 가능하다.

---

## ⚡ Step 4 — 원샷 활성화 스크립트 실행

```bash
python3 backend/scripts/activate_azure.py
```

이 스크립트가 자동으로 수행:

| 단계 | 작업 | 소요 |
|---|---|---|
| 1 | 환경변수 검증 (누락된 키 리포트) | 즉시 |
| 2 | Azure OpenAI 임베딩 스모크 (1건 호출) | 2초 |
| 3 | AI Search 인덱스 A/B 생성 | 10초 |
| 4 | Index A 1,950 법률 조문 임베딩+업로드 | 3~5분 |
| 5 | Index B 200 행정 절차 청크 임베딩+업로드 | 30초 |
| 6 | Golden Query 30건 재평가 | 10초 |
| 7 | `azure_ready=true` 헬스체크 | 즉시 |

**성공**: `🎉 Azure 활성화 완료!` 메시지와 함께 `backend/data/indexes/evaluation_report.json` 생성.

---

## ✅ Step 5 — 로컬 검증

```bash
# 백엔드 재시작 (lru_cache 초기화 필요)
pkill -f "uvicorn backend.app.main"
python3 -m uvicorn backend.app.main:app --port 8765 --reload &

# 헬스체크 — azure_ready 가 true 여야 함
curl http://127.0.0.1:8765/
# → {"service":"이사이상무", ..., "azure_ready":true}

# 스모크 테스트 (5/5 여야 함)
python3 backend/scripts/smoke_test.py
```

---

## 🌐 Step 6 — Render 배포에 Azure 키 주입

팀 공용 Render 배포에도 같은 환경변수를 반영해야 프론트 앱에서 Azure 모드로 접속된다.

1. Render 대시보드 → `movewise` 서비스 → **Environment** 탭
2. `.env` 에 넣은 Azure 키를 **Add Environment Variable** 로 그대로 8개 추가
   - `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME`,
     `AZURE_OPENAI_EMBED_DEPLOYMENT`, `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`,
     `AZURE_DOCINTEL_ENDPOINT`, `AZURE_DOCINTEL_API_KEY`
3. **Save Changes** → 자동 재배포 시작 (5~10분)
4. 배포 완료 후:
   ```bash
   curl https://movewise-jf1s.onrender.com/
   # → "azure_ready":true
   ```

---

## 📱 Step 7 — 프론트엔드 확인

Expo Go 또는 시뮬레이터로:

- **마이 탭 상단 배지**: `🔧 Local fallback 모드` → **`🧠 Azure LLM 모드`** 로 변경
- **체크리스트 탭**: 새 체크리스트 생성 시 warning 메시지 사라짐
- **계약 전 체크 탭**: **PDF 업로드 버튼 활성화** → 등기부 PDF 파싱 실제 동작
- **체크리스트 항목 상세**: 법 조항 원문이 LLM 이 동적으로 검색한 결과로 표시됨

---

## 🧯 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `리소스 그룹 생성 권한 없음` | 학생 계정은 구독 권한 없음. 학원 운영자에게 RG 생성 요청 |
| `dimensions=3072` 경고 | text-embedding-3-**large** 사용 중 → `schemas/index_*.json` 의 `dimensions` 3072 로 수정 |
| Search API `403 Forbidden` | Primary admin key 가 아닌 Query Key 사용 중. Portal → Keys → Primary admin key 복사 |
| `429 rate limit` (OpenAI) | quota 초과. `activate_azure.py` 의 batch size 16 → 8 로 조정 후 재실행 |
| 업로드 성공했는데 `/checklist` 가 여전히 fallback | 백엔드 재시작 안 됨. `pkill -f uvicorn` 후 다시 띄우기 (`lru_cache` 초기화 필요) |
| Render 재배포 후 여전히 fallback | Environment 저장 실패 또는 Manual Deploy 필요. Render → Manual Deploy → Clear build cache & deploy |
| GPT-4o 배포가 안 만들어짐 | 리전 quota 문제. East US 2 → East US → Sweden Central 순으로 시도 |
| Document Intelligence 응답이 엉성 | 등기부 PDF 스캔 품질 확인. `prebuilt-layout` 모델은 텍스트 기반 PDF 에 최적 |

---

## 🎯 완료 기준

- [ ] `curl http://127.0.0.1:8765/` → `azure_ready:true`
- [ ] `curl https://movewise-jf1s.onrender.com/` → `azure_ready:true`
- [ ] `python3 backend/scripts/smoke_test.py` → 5/5 passed
- [ ] `backend/data/indexes/evaluation_report.json` → mean recall ≥ 0.95
- [ ] Expo 앱 마이 탭에 **🧠 Azure LLM 모드** 배지 표시
- [ ] 체크리스트 생성 시 `used_queries` 가 LLM 이 만든 자연어 쿼리 (하드코딩 아님)
- [ ] 계약 전 체크 탭에서 PDF 업로드 → 파싱 결과 표시

7개 체크하면 Azure 연결 완료.

---

## 🔧 주요 파일 위치 참고

| 파일 | 역할 |
|---|---|
| `backend/app/main.py` | FastAPI 엔트리, 엔드포인트 정의 |
| `backend/app/config.py` | pydantic-settings, `azure_ready` 판단 |
| `backend/app/azure_clients.py` | OpenAI / Search / Doc Intel lazy-init |
| `backend/app/checklist_service.py` | 4단계 RAG 파이프라인 |
| `backend/app/safecontract_service.py` | 등기부 분석 + PDF 파싱 |
| `backend/app/local_search.py` | fallback 모드 BM25 + 한자 제거 |
| `backend/scripts/activate_azure.py` | 원샷 활성화 |
| `backend/scripts/upload_to_search.py` | 인덱스 생성 + 임베딩 업로드 |
| `backend/scripts/evaluate_checklist.py` | Golden Query 30건 평가 |
| `backend/schemas/index_a_law.json` | 법률 인덱스 스키마 |
| `backend/schemas/index_b_procedure.json` | 절차 인덱스 스키마 |
| `.env.example` | 환경변수 템플릿 |

막히는 지점 있으면 팀장에게 연락.
