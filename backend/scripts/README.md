# Backend Scripts

데이터 수집·전처리·인덱스 빌드·유틸리티 스크립트 모음.  
운영 코드(`app/`)가 아니라 **일회성 파이프라인** — 초기 세팅 또는 데이터 갱신 때만 실행.

---

## 카테고리별 분류

### 1. Ingest — 원본 데이터 수집

공공 API·공개 데이터셋에서 원본 수집 → `backend/data/` 저장.

| 스크립트 | 출력 | 설명 |
|---------|------|------|
| `ingest_laws.py` | `data/law/*.json` | 국가법령정보 Open API (주택임대차보호법 등 핵심 법령) |
| `ingest_easylaw.py` | `data/guide/easylaw-*.json` (53개) | 찾기쉬운 생활법령정보 "이사" + "주택임대차" 카테고리 크롤링 (v2에서 lease 스크립트 통합) |
| `ingest_moveout.py` | `data/procedures/moveout_*.json` | 이사 관련 행정 절차 통합 수집 |
| `ingest_services.py` | `data/mapping/*.json` | 지역별 서비스 (수도·가스·전기·통신·우편 등) |
| `ingest_services_v2.py` | `data/mapping/*_v2.json` | services v2 개선본 (구버전 대체) |
| `ingest_water.py` | `data/mapping/water_region_office.json` | 전국 수도사업소 세분화 |
| `ingest_citygas.py` | `data/mapping/gas_region_company.json` | 도시가스 회사 지역 매핑 |
| `ingest_youtube.py` | `data/raw/youtube_transcripts/*.json` | 유튜브 이사 팁 영상 자막 |
| `ingest_holidays.py` | `data/raw/holidays_2026.json` | 공공데이터 공휴일 (D-day 계산용) |

> NOTE: `ingest_youtube.py` 와 `data/raw/youtube_transcripts/*.json` 은 저작권 우려로
> 2026-04-23 제거됨. 챗봇은 law + guide 2개 인덱스만 사용.

### 2. Preprocess — 청킹·메타 주입

수집한 raw JSON 을 AI Search 에 넣기 좋은 청크로 가공.

| 스크립트 | 설명 |
|---------|------|
| `chunk_easylaw.py` | guide JSON → 700자 목표 청크 (`guide_chunks.jsonl`) |
| `annotate_sources.py` | 모든 JSON 에 `_source_metadata` 필드 주입 + DATA_SOURCES.md 카탈로그 생성 |

### 3. Index — 통합 인덱스 빌드·업로드

청크 파일을 Azure AI Search 업로드.

| 스크립트 | 설명 |
|---------|------|
| `unify_indexes.py` | law + procedure + video 청크 → 단일 `index_unified.jsonl` (source_type 필드 포함) |
| `upload_to_search.py` | unified JSONL + 임베딩 → Azure AI Search 인덱스에 업로드 |

### 4. Util — 관리·평가·검증

| 스크립트 | 설명 |
|---------|------|
| `activate_azure.py` | Azure 연결 상태 확인 (키·엔드포인트·인덱스 존재) |
| `smoke_test.py` | 배포 후 핵심 엔드포인트 동작 확인 (health, checklist 샘플) |
| `evaluate_checklist.py` | Golden 쿼리 기반 체크리스트 품질 평가 (`data/indexes/evaluation_report.json` 생성) |

---

## 실행 순서 (전체 재빌드 시)

기존 인덱스가 있다면 평소엔 재실행 불필요. 아래는 **처음부터 다시 만들 때**.

```
1) Ingest (원본 수집, 수분~수십분)
   python scripts/ingest_laws.py
   python scripts/ingest_easylaw.py
   python scripts/ingest_moveout.py
   python scripts/ingest_services_v2.py
   python scripts/ingest_water.py
   python scripts/ingest_citygas.py
   python scripts/ingest_youtube.py
   python scripts/ingest_holidays.py

2) Preprocess (청킹·큐레이션, 수분)
   python scripts/chunk_easylaw.py
   python scripts/curate_chunks.py
   python scripts/annotate_sources.py

3) Index (통합·업로드, ~10분)
   python scripts/unify_indexes.py
   python scripts/upload_to_search.py

4) Verify (배포 후)
   python scripts/activate_azure.py
   python scripts/smoke_test.py
   python scripts/evaluate_checklist.py
```

---

## 개별 갱신 케이스

| 상황 | 실행할 것 |
|------|-----------|
| 새 법령 추가 | `ingest_laws.py` → `unify_indexes.py` → `upload_to_search.py` |
| 지역 매핑 보강 (새 시·군) | `ingest_services_v2.py` 수정·재실행 (인덱스 업로드 불필요) |
| 유튜브 영상 추가 | `ingest_youtube.py` → `unify_indexes.py` → `upload_to_search.py` |
| 새 공휴일 연도 | `ingest_holidays.py` → 백엔드 재시작 (인덱스 업로드 불필요) |

---

## 주의사항

- 모든 스크립트는 **프로젝트 루트에서 실행** 기준: `cd backend && python scripts/xxx.py`
- `upload_to_search.py` 는 **Azure 요금 발생** (OpenAI 임베딩 API 호출)
- 대용량 파일(`index_unified_embeddings.jsonl` 65MB)은 git 비추적 (`.gitignore` 권장)
- 실행 전 `.env` 필수 (관련 키 없으면 fail-fast)
