# DEVLOG — experiment/schema-refactor

이사이상무 2차 프로젝트 스키마 리팩토링 실험 브랜치의 방법론과 원칙.

---

## 배경

- **소속**: Microsoft AI School 9기 4팀
- **프로젝트**: 이사이상무 — AI 기반 이사 도우미 앱
- **기간**: 2026.04.13 ~ 2026.04.26
- **기술 스택**: FastAPI + React Native + Azure OpenAI + Azure AI Search + Document Intelligence

## 브랜치 구조

```
wes0031-rgb/isa-isangmu (upstream)          ← 팀 원본, 건드리지 않음
   └── liminal-cipher/isa-isangmu (origin)  ← 내 fork
         ├── main                            ← 팀 main과 sync 유지
         └── experiment/schema-refactor      ← 이 실험 브랜치
```

## 실험 목적

1. **3-index 분리 아키텍처 검증**: 팀의 unified 인덱스 vs law/guide/video 분리 인덱스 비교
2. **Azure AI Search Indexer 파이프라인 시연**: MS AI School 클라우드 역량 평가 포인트
3. **데이터 품질 정비**: 재현 가능한 ingest 파이프라인 구축

## 방법론 원칙

### 1. 데이터 품질 먼저, Azure는 나중

정제되지 않은 데이터를 Azure에 올려도 의미 없음. 순서:

1. 로컬에서 스키마 확정
2. 재현 가능한 ingest 스크립트 작성
3. 검증된 데이터로 Azure 업로드
4. 쿼리 품질 검증

### 2. 최소 변경 원칙 (팀 보호)

- 팀 upstream main 영향 0
- Fork 브랜치에서만 작업
- PR 열기 전까진 팀에 영향 없음
- 팀 합의 전엔 upstream 건드리지 않음

### 3. 재현 가능성

- 모든 데이터는 스크립트로 재생성 가능해야 함
- 수동 편집 금지
- 파일명 ASCII-safe (영문 slug)
- 경로 크로스플랫폼 (`Path(__file__).resolve().parent...`)

### 4. 필드 정당화 원칙 ⭐

모든 스키마 필드는 **"왜 필요한지" 명확한 이유**가 있어야 함.

- 이유 불명 필드 → 일단 제거
- 필요성 증명되면 재추가
- 유지보수 비용보다 가치가 커야 포함

※ 필드 **최소화**가 목적이 아니라, 필드마다 **책임 있는 설계**가 목적.

예시:

- `penalties` 제거: 팀 커밋 bb59244 준수 (활용도 0.9%)
- `keywords` 유지 결정: 이전 세션(4/18)에서 제거 검토됐으나 팀 회의 후 유지.
  자동 추출 키워드 → 검색 부스팅 효과 입증됨
- `related_videos` 유지: 하드코딩 매핑 근거 명확 (law → video 큐레이션)
- `last_updated` Azure 미반영: `fetched_at`과 중복이라 Azure 스키마에서 제외.
  로컬 JSONL에는 유지 (소스 원형 보존)

### 5. 소스 원형 보존 + Azure 변환 (Indexer 파이프라인)

**핵심 결정: 로컬 JSONL은 수집 원형 그대로 유지. 모든 스키마 변환은 Azure Indexer 단계에서.**

- 소스 JSONL: 🔴 필수 + 🟡 유지 + 🟢 삭제 OK 필드 전부 포함
- Azure 인덱스: 🔴 필수 + 🟡 유지 필드만 포함 (🟢 제외)
- 이름 변경(`doc_title`→`title` 등): Indexer `fieldMappings`로 처리

**이유**:

- 재인덱싱 유연성 최대화 (소스 망가지면 복구 어려움)
- 소스에 메타데이터 풍부하게 남겨 디버깅 용이
- Azure 스키마 변경 시 소스 재수집 불필요

### 6. 확장 가능성 아키텍처 (Indexer 중심)

**Direct Push가 아닌 Azure Indexer 파이프라인 채택**:

```
Blob Storage → Datasource → Skillset → Indexer → Index
```

- 증분 업데이트 자동화
- 임베딩 스킬셋으로 관리 부담 ↓
- 추가 법률 소스(판례, 자치법규 등) 확장 용이

MS AI School 평가 포인트: 클라우드 플랫폼 역량 시연.

## 평가 기준

실험 비교 시 측정할 것:

- 쿼리 recall/precision (golden query 30건 기준)
- 특정 법령 필터링 정확도
- 단일 semantic ranking vs 3-index re-rank
- 유지보수성 (코드 라인 수, 수정 파급 범위)
- 확장성 (새 법률 소스 추가 시 작업량)

## 주요 아키텍처 결정

### ✅ 확정

- **3-index 분리**: `iim-law-index`, `iim-guide-index`, `iim-video-index`
- **임베딩 모델**: text-embedding-3-small (1536 dim)
- **파일명**: 영문 slug (ASCII only)
- **청크 ID**: ASCII-safe (Azure Search document key 제약)
- **경로 처리**: `Path(__file__).resolve().parent.parent.parent` 기반 (크로스플랫폼)
- **파이프라인**: Indexer 기반 (Blob → Datasource → Skillset → Indexer → Index)
- **스키마 변환**: Azure `fieldMappings`로 처리 (로컬 JSONL 불변)

### 🟡 검토 중

- **폴더 구조 리팩토링**: `procedures/` → `guides/`, `raw/youtube_transcripts/` → `videos/`, `mapping/` → `lookups/`
- **Skillset 구성**: Azure OpenAI embedding skill + SplitSkill 조합 vs 수동 청킹 사용

### ❌ 제거 확정

- `penalties` 필드 (커밋 bb59244 준수)
- `content_vector` 수동 null 값 (Indexer skillset이 주입)
- 파일명 한글 (ASCII slug로 전환 완료)

### 🟢 Azure 업로드 시 제외 (소스엔 유지)

로컬 JSONL엔 있지만 Azure 인덱스 스키마에서는 선언 안 함 (indexer가 자동 무시):

- **Law**: `last_updated` (`fetched_at`와 중복)
- **Guide**: `source`, `category_root`, `content_length`
- **Video**: `channel_url`, `source_type`

### 🟡 팀 회의 확정 유지 필드

이전 세션에서 제거 검토됐으나 회의 후 유지 결정:

- `keywords` (law): 자동 추출 키워드, 검색 부스팅 효과 입증 → Azure semantic config의 keywords_fields로 활용
- `applicable_to`/`contract_type`/`region` (guide/video): 현재 하드코딩이나 Phase 2에서 사용자 프로필 DB와 연동 예정

## 데이터 소스

### Law (법령 원본)

- **출처**: 법제처 국가법령정보 Open API (DRF)
- **인증**: LAW_OC (개인 발급)
- **수집 스크립트**: `backend/scripts/ingest_laws.py`
- **대상 법령**: 8개 (주택임대차보호법 및 시행령, 민법, 부동산등기법, 주민등록법 및 시행령, 공동주택관리법, 동물보호법)

### Guide (생활법령 해설)

- **출처**: 법제처 찾기쉬운 생활법령정보 (easylaw.go.kr)
- **수집 방식**: HTML 크롤링 (공식 API 없음)
- **수집 스크립트**: `backend/scripts/ingest_easylaw.py`
- **카테고리**:
  - csmSeq=666: 이사 (22개 페이지)
  - csmSeq=629: 주택임대차 (31개 페이지)

### Video (유튜브 자막)

- **출처**: YouTube (youtube-transcript-api)
- **수집 스크립트**: `backend/scripts/ingest_youtube.py`
- **대상**: 이사·전세 관련 채널 영상 (큐레이션)

## 환경

- **OS**: Windows (Git Bash)
- **Python**: 3.13
- **Azure 리소스**: Portal에서 팀 리소스 그룹 내 생성 완료
- **Azure 키 상태**: `.env`에 설정됨, 인덱스는 미생성 (데이터 정비 후 업로드 예정)
- **`.env` 위치**: 프로젝트 루트 (`backend/.env`와 중복, 정리 필요)

## 팀 관계

- 팀 앱은 **unified index**로 Render에 배포 중 (https://movewise-jf1s.onrender.com)
- 내 실험은 **별도 3-index**로 비교 설계
- 스키마는 팀 회의에서 논의된 구성을 따름 (🔴🟡🟢 분류)
- 팀 운영에 영향 없음

## 참조 문서

- `SESSION_LOG.md`: 세션별 진행 기록
- `SCHEMA_DECISION.md`: 필드별 설계 근거
- `backend/README.md`: 팀 공용 백엔드 가이드
- `backend/data/DATA_SOURCES.md`: 데이터 소스 카탈로그
