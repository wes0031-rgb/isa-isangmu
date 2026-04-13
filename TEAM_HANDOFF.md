# 👋 MoveWise 팀원 온보딩 — Azure 작업 이어받기

> 이 문서 하나만 따라가면 Azure 5종 리소스 연결까지 끝납니다.

---

## 📍 현재 상태 (2026-04-13)

### ✅ 이미 완료 (수정 불필요)
- **백엔드**: FastAPI + fallback 모드 완전 동작, Render 배포 Live
  - URL: https://movewise-jf1s.onrender.com
- **프론트엔드**: Expo SDK 55 + TypeScript, 4탭 + 달력/지역 picker + 특이상황 11칩
- **데이터**: Index A 법률 1,950 조문 + Index B 행정 절차 200 청크 (한자 전부 제거됨)
- **품질**: Golden Query 30/30 perfect · pytest 30 passed · smoke test 5/5

### 🔴 팀원이 해야 할 것 — **Azure 5종 연결만**
- Azure OpenAI (GPT-4o + text-embedding-3-small)
- Azure AI Search
- Azure Document Intelligence (옵션)
- Azure Blob Storage (옵션)
- Azure App Service (옵션, Render 로 대체 가능)

---

## 1️⃣ 환경 준비 (5분)

```bash
# 1. 클론
git clone https://github.com/wes0031-rgb/movewise.git
cd movewise

# 2. 백엔드 파이썬 패키지
cd backend
pip install -r requirements.txt --break-system-packages --user
cd ..

# 3. 로컬 백엔드 실행 확인 (fallback 모드)
python3 -m uvicorn backend.app.main:app --port 8765 --reload

# 별도 터미널에서:
curl http://127.0.0.1:8765/
# → {"service":"MoveWise", ... "azure_ready":false}  ← fallback 모드 정상
```

---

## 2️⃣ Azure 리소스 생성 (30~60분)

### 필요한 리소스 목록

| 서비스 | 리전 | SKU | 용도 |
|---|---|---|---|
| **Azure OpenAI** | East US 2 또는 Korea Central | S0 | GPT-4o 체크리스트 생성, 임베딩 |
| - GPT-4o 배포 | — | 10K TPM 이상 | |
| - text-embedding-3-small 배포 | — | 120K TPM 이상 | |
| **Azure AI Search** | Korea Central 권장 | **Standard S1** | 벡터 + 세만틱 검색 |
| **Document Intelligence** | East US 또는 Korea Central | S0 | 등기부 PDF 파싱 |
| **Blob Storage** | Korea Central | Standard LRS | 문서 원본 저장 (옵션) |

### ⚠️ 주의사항
- **Standard S1 Search 필수** (Free 티어는 벡터 검색 제한). 비용은 시간당 $0.336 ≈ 하루 $8
- OpenAI quota 는 리전마다 다름. East US 2 가 가장 안정
- 반드시 **기존 `9ai-2nd-team4` 같은 다른 팀 리소스 그룹은 건드리지 말 것**
- 본인 팀 리소스 그룹(`9ai-2nd-team5` 또는 운영자가 배정한 이름)에만 생성

### 리소스 생성 순서
1. **Azure OpenAI** 생성 → GPT-4o·embedding 배포
2. **AI Search** 생성 → 키 복사
3. **Document Intelligence** 생성 → 키 복사
4. (옵션) Blob Storage 생성 → connection string 복사

---

## 3️⃣ `.env` 값 입력 (5분)

`.env.example` 을 `.env` 로 복사 후 Azure 값 채우기:

```bash
cp .env.example .env
```

`.env` 편집해서 다음 값 입력:

```bash
# 기존 공공데이터 API 키 (이미 발급 완료 — 팀장에게 받기)
JUSO_API_KEY=<팀장에게 받기>
DATA_GO_KR_SERVICE_KEY=<팀장에게 받기>
LAW_OC=msai09sa

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<리소스이름>.openai.azure.com/
AZURE_OPENAI_API_KEY=<Portal → Keys and Endpoint>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o                    # 본인이 만든 배포명
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small   # 본인이 만든 임베딩 배포명

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://<리소스이름>.search.windows.net
AZURE_SEARCH_API_KEY=<Portal → Keys → Admin key (Primary)>
```

---

## 4️⃣ 원샷 활성화 스크립트 실행 (10~15분)

```bash
python3 backend/scripts/activate_azure.py
```

이 스크립트가 자동으로:

| 단계 | 작업 | 예상 시간 |
|---|---|---|
| 1 | 환경변수 검증 | 즉시 |
| 2 | 임베딩 엔드포인트 스모크 (1건 호출) | 2초 |
| 3 | AI Search 인덱스 A/B 생성 | 10초 |
| 4 | Index A 1,950 조문 임베딩+업로드 | 3~5분 |
| 5 | Index B 200 청크 임베딩+업로드 | 30초 |
| 6 | Golden Query 30건 재평가 | 10초 |
| 7 | 헬스체크 `azure_ready=true` 확인 | 즉시 |

**성공 시**: `🎉 Azure 활성화 완료!` 메시지와 함께 `evaluation_report.json` 생성

**실패 시 트러블슈팅**: [AZURE_ACTIVATION.md](./AZURE_ACTIVATION.md) 참고

---

## 5️⃣ 백엔드 검증 (5분)

```bash
# 로컬 백엔드 재시작 (lru_cache 초기화 필요)
pkill -f "uvicorn backend.app.main"
python3 -m uvicorn backend.app.main:app --port 8765 --reload &

# 헬스체크
curl http://127.0.0.1:8765/
# → "azure_ready":true 로 바뀌어야 함

# 스모크 테스트
python3 backend/scripts/smoke_test.py
# → 5/5 passed
```

---

## 6️⃣ Render 배포 반영 (10~15분)

팀 공용 Render 배포에도 Azure 키 주입해서 앱에서 접속 가능하게:

1. Render 대시보드 → `movewise` 서비스 → **Environment** 탭
2. **Add Environment Variable** 로 `.env` 에 넣은 값 그대로 8개 추가
3. **Save Changes** → 자동 재배포 시작
4. 배포 완료 후:
   ```bash
   curl https://movewise-jf1s.onrender.com/
   # → "azure_ready":true
   ```

---

## 7️⃣ 프론트엔드 확인 (5분)

시뮬레이터 또는 Expo Go 로:

- **MY 탭** 상단 배지: `🔧 Local fallback 모드` → `🧠 Azure LLM 모드` 로 변경
- **체크리스트 탭**: 새 체크리스트 생성 시 `warning` 메시지 사라짐
- **계약 전 체크 탭**: 위험 분석 시 LLM 이 동적으로 다른 법 조항 인용

---

## 📚 관련 문서

| 파일 | 내용 |
|---|---|
| [README.md](./README.md) | 프로젝트 전체 개요 |
| [AZURE_ACTIVATION.md](./AZURE_ACTIVATION.md) | 트러블슈팅 상세 |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Render/Azure/Fly 배포 옵션 |
| [기반_기획서.md](./기반_기획서.md) | 원본 PRD |

---

## 🆘 막히면

- **리소스 그룹 생성 권한 없음**: 학원 운영자에게 문의 (학생 계정은 RG 생성 불가)
- **GPT-4o quota 거부**: East US 2 → East US → Sweden Central 순으로 시도
- **Free tier AI Search 선택 불가**: Standard S1 필수 (벡터 검색 때문)
- **activate_azure.py 중간 실패**: `--skip-embeddings` 옵션으로 인덱스만 먼저 만들고 재시도
- **프론트에서 Azure 모드 안 뜸**: 백엔드 `lru_cache` 때문. uvicorn 프로세스 완전히 죽이고 재시작

---

## 🎯 완료 기준

- [ ] `curl http://127.0.0.1:8765/` 에서 `azure_ready:true`
- [ ] `curl https://movewise-jf1s.onrender.com/` 에서 `azure_ready:true`
- [ ] `python3 backend/scripts/smoke_test.py` 5/5 passed
- [ ] Expo 앱 MY 탭에 **🧠 Azure LLM 모드** 배지 노출
- [ ] 체크리스트 생성 시 `used_queries` 가 LLM 이 만든 자연어 쿼리 (하드코딩 아님)

4개 다 체크되면 기획서 메인 경로는 완성입니다.
