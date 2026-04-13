# Azure 활성화 가이드

> 목표: Azure 키 꽂으면 자동으로 RAG 모드로 전환 — **이 문서 하나로 끝**

---

## 📋 준비물 (Azure Portal에서)

1. **Azure OpenAI** — `gpt-4o` + `text-embedding-3-small` 2개 배포
   - Endpoint: `https://<name>.openai.azure.com/`
   - API Key
   - GPT 배포명 (보통 `gpt-4o`)
   - 임베딩 배포명 (보통 `text-embedding-3-small`)

2. **Azure AI Search** — Standard S1 권장 (Free 티어는 벡터 검색 제한)
   - Endpoint: `https://<name>.search.windows.net`
   - Admin API Key

3. **(옵션) Azure Document Intelligence** — SafeContract PDF OCR
4. **(옵션) Azure Blob Storage** — 원본 문서 저장

---

## 🔐 1단계: .env 입력

`/Users/sa/Desktop/2차프로젝트/.env` 파일 열고 이 값들 채우기:

```bash
# ===== Azure OpenAI (필수) =====
AZURE_OPENAI_ENDPOINT=https://<name>.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small

# ===== Azure AI Search (필수) =====
AZURE_SEARCH_ENDPOINT=https://<name>.search.windows.net
AZURE_SEARCH_API_KEY=<admin-key>
AZURE_SEARCH_LAW_INDEX=moving-law-index
AZURE_SEARCH_PROCEDURE_INDEX=moving-procedure-index

# ===== Azure Document Intelligence (옵션) =====
AZURE_DOCINTEL_ENDPOINT=
AZURE_DOCINTEL_API_KEY=

# ===== Azure Blob Storage (옵션) =====
AZURE_BLOB_CONNECTION_STRING=
AZURE_BLOB_CONTAINER_NAME=moving-guide-docs
```

---

## ⚡ 2단계: 원샷 활성화 (명령어 1개)

```bash
cd /Users/sa/Desktop/2차프로젝트
python3 backend/scripts/activate_azure.py
```

스크립트가 자동으로 수행:

| 단계 | 작업 | 소요 |
|---|---|---|
| 1 | 환경변수 검증 | 즉시 |
| 2 | 임베딩 엔드포인트 스모크 (1건 호출) | 2초 |
| 3 | Azure AI Search 인덱스 A/B 생성 | 10초 |
| 4 | Index A 1,950 조문 임베딩+업로드 | 3~5분 |
| 5 | Index B 200 청크 임베딩+업로드 | 30초 |
| 6 | Golden Query 30건 재평가 | 10초 |
| 7 | 백엔드 헬스체크 `azure_ready=true` | 즉시 |

총 **4~6분**이면 `🎉 Azure 활성화 완료!` 메시지.

---

## 🔄 3단계: 백엔드 재시작

**로컬 개발 서버:**
```bash
pkill -f "uvicorn backend.app.main" 2>/dev/null
python3 -m uvicorn backend.app.main:app --port 8765 --reload
```

**Render.com 배포:**
1. Dashboard → `movewise` 서비스 → **Environment** 탭
2. 위 `.env` 값 8개 전부 추가 (`Add Environment Variable`)
3. **Save Changes** → 자동 재배포 시작
4. 배포 완료 후:
   ```bash
   curl https://movewise-jf1s.onrender.com/
   # {"azure_ready":true, ...} 확인
   ```

---

## ✅ 4단계: 검증

**로컬:**
```bash
curl http://127.0.0.1:8765/ | python3 -m json.tool
# → azure_ready: true

python3 backend/scripts/smoke_test.py
# → 5/5 passed (Azure 모드로 응답)

python3 backend/scripts/evaluate_checklist.py
# → mean recall 변화 확인 (1.000 유지, citation coverage 상승 예상)
```

**프론트엔드 (Expo 앱):**
- MY 탭 → 상단 배지 **🧠 Azure LLM 모드** 노출
- 체크리스트 생성 시 `warning` 필드 없음 (fallback 경고 사라짐)

---

## 🧯 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `dimensions=3072` 경고 | text-embedding-3-**large** 사용 중 → `schemas/index_*.json` 의 `dimensions` 를 3072 로 수정 후 재실행 |
| Index 생성 실패 `403` | Search API Key가 **Admin Key**가 아닌 Query Key. Portal → Keys → Primary admin key 복사 |
| `429 rate limit` | OpenAI TPM 한도 초과. `activate_azure.py` 의 batch size 16 → 8 로 줄이기 |
| 업로드 후 `/checklist` 가 여전히 fallback | 백엔드 재시작 안됨. `lru_cache` 초기화 필요 → uvicorn 프로세스 kill 후 재실행 |
| Render 재배포 후 여전히 fallback | Render Environment 저장 안됨. Manual Deploy → Clear build cache → Deploy |

---

## 📊 기대 결과

- **체크리스트 품질**: citation_coverage 0.967 → 0.99+ (실제 LLM으로 조문 매칭)
- **SafeContract**: 법률 인용을 Index A 벡터 검색으로 찾아 더 정확한 risk explanation
- **응답 시간**: fallback 50ms → Azure 2~4초 (GPT-4o 호출 포함)
- **발표용 메시지**: "5종 Azure 서비스 통합 RAG 시스템 · 공용 fallback 지원"
