# SCHEMA_DECISION

3-index의 각 필드별 설계 근거 기록. "왜 이 필드가 존재/제거됐는가?"의 영구 답변.

---

## 원칙

모든 필드는 다음 중 하나의 질문에 답할 수 있어야 함:

1. **검색 용도**: 이 필드로 어떤 쿼리를 받을 수 있는가?
2. **필터 용도**: 이 필드로 어떤 결과를 좁힐 수 있는가?
3. **표시 용도**: UI에서 어떻게 사용자에게 보여주는가?
4. **추적 용도**: 데이터 품질·신선도를 어떻게 검증하는가?

답할 수 없는 필드는 제거 대상.

---

## 소스 JSONL vs Azure 인덱스 스키마

팀 회의(4/19)에서 스키마를 네 레벨로 분류:

| 분류         | 의미                   | 소스 JSONL               | Azure 인덱스 |
| ------------ | ---------------------- | ------------------------ | ------------ |
| 🔴 필수      | 항상 있어야            | ✅ 포함                  | ✅ 포함      |
| 🟡 유지      | 유용함, 일단 유지      | ✅ 포함                  | ✅ 포함      |
| 🟢 삭제 OK   | Azure에 안 올려도 됨   | ✅ 포함 (소스 원형 보존) | ❌ 제외      |
| ⚪ 이미 삭제 | 스크래핑/청킹에서 제외 | ❌ 제외                  | ❌ 제외      |

### 이름 변경 처리 (Indexer fieldMappings)

일부 필드는 소스 이름과 Azure 이름이 다름:

| 소스 필드     | Azure 필드 | 인덱스 |
| ------------- | ---------- | ------ |
| `doc_title`   | `title`    | Guide  |
| `video_title` | `title`    | Video  |

**처리 방법**: Azure Indexer의 `fieldMappings` 선언.

```json
"fieldMappings": [
  {
    "sourceFieldName": "doc_title",
    "targetFieldName": "title"
  }
]
```

**소스 JSONL은 수정 불필요.** Indexer가 읽을 때 매핑.

### 🟢 필드 제외 방법

Azure 인덱스 스키마에서 해당 필드를 **선언하지 않으면** Indexer가 자동 무시. 별도 drop 처리 불필요.

### 로컬 파일 수정이 필요한 경우

현재 수집된 데이터는 **그대로 유지**. 다음 경우에만 로컬 수정:

1. Python 코드(예: `unify_indexes.py`)가 JSONL 읽어 필드 참조할 때
2. 스키마 검증 테스트를 로컬에서 돌릴 때

**원칙**: Azure로 넘기기 전까지 소스 원형 보존 → 재인덱싱 유연성 최대화.

---

## Index A — Law (법령 조문)

**Azure 인덱스명**: `law-index`  
**소스 필드 수**: 12개  
**Azure 업로드 필드 수**: 12개 (`fetched_at` 으로 통일, `last_updated` 는 미사용)  
**청크 수**: 1,635 (2026-04-19 기준)  
**입력 파일**: `backend/data/laws/*.json` (8개 법령)  
**청크 파일**: `backend/data/indexes/law_chunks.jsonl`

### 팀 회의 확정 필드 (12개)

| 필드                 | 분류          | 역할                            | 근거                                 |
| -------------------- | ------------- | ------------------------------- | ------------------------------------ |
| `id`                 | 🔴 필수       | 청크 고유 키 (Azure key)        | ASCII-only, document key 제약        |
| `title`              | 🔴 필수       | 조문 제목 · semantic 최우선     | 예: "대항력 등"                      |
| `content`            | 🔴 필수       | 조문 본문                       | 주 검색 대상, 벡터 임베딩            |
| `source_url`         | 🔴 필수       | law.go.kr 원문 링크             | Citation 클릭 시 이동                |
| `law_name`           | 🔴 필수       | "주택임대차보호법"              | Semantic keywords                    |
| `article`            | 🔴 필수       | "제3조의2"                      | Citation 표시                        |
| `category`           | 🔴 필수       | 분류 태그                       | filter/facet                         |
| `keywords`           | 🔴 필수       | 자동 추출 키워드                | 검색 부스팅 (4/19 회의 후 유지 결정) |
| `deadlines`          | 🟡 유지       | "14일 이내"                     | D-day 계산 근거                      |
| `related_procedures` | 🟡 유지       | 법 ↔ 절차 크로스 링크           | Phase 2 vector similarity            |
| `related_videos`     | 🟡 유지       | 법 ↔ 영상 크로스 링크           | 법 단위 하드코딩 큐레이션            |
| `fetched_at`         | 🟡 유지       | 수집 일자 · 신선도              | `last_updated` 는 제거·미사용        |
| `penalties`          | ⚪ 이미 삭제  | 활용도 0.9%                     | 커밋 bb59244                         |

**스크립트 현황 (2026-04-20)**:

- `ingest_laws.py` 는 `keywords` 자동 추출 완료 (세션 3, DOMAIN_KEYWORDS ~60개 whitelist)
- `fetched_at` 만 생성 (`last_updated` 는 제거됨)

### 청크 ID 형식

```
law_{slug}_art{N}[_{sub}]

예시:
  law_housing_lease_protection_art1
  law_housing_lease_protection_art3_2  (제3조의2)
  law_civil_code_art618
```

**이유**: Azure Search document key는 letters/digits/underscores/dashes/equals만 허용.

### 카테고리 결정 로직

- 일반 법령: LAWS 튜플의 `note` 필드 사용
  - 예: 주택임대차보호법 → "임대차 대항력·확정일자·우선변제권"
- 민법: 조문 번호로 서브카테고리 분류
  - 제1~184조: "민법 총칙"
  - 제185~372조: "민법 물권"
  - 제373~617조: "민법 채권 총칙"
  - 제618~654조: "민법 채권 — 임대차"
  - 제655~766조: "민법 채권 — 기타 전형계약"
  - 제767~996조: "민법 친족"
  - 제997조~: "민법 상속"

### RAG 품질 필터

다음 조문은 청크 생성에서 제외:

- 삭제된 조문: `^제\d+조(?:의\d+)?\s*삭제\s*<`
- 구조 헤더: `^제\d+\s*[편장절관]\s`
- Stub: content 길이 40자 미만

### Azure Field Mapping

특별한 매핑 없음 (소스 필드명 = Azure 필드명).

---

## Index B — Guide (생활법령 해설)

**Azure 인덱스명**: `guide-index`  
**소스 필드 수**: 19개  
**Azure 업로드 필드 수**: 15개 (🟢 3개 제외 + doc_title→title 매핑)  
**청크 수**: 200 (큐레이션 후, 재청킹 필요)  
**입력 파일**: `backend/data/procedures/easylaw/*.json` (53개)  
**청크 파일**: `backend/data/indexes/index_b_chunks_curated.jsonl`

### 스크래퍼 출력 (원본 JSON, 10 필드)

`ingest_easylaw.py` 출력:

| 필드             | 타입     | 역할                                   |
| ---------------- | -------- | -------------------------------------- |
| `id`             | string   | 문서 ID (예: easylaw-629-2-1-1)        |
| `source`         | string   | 출처 ("easylaw.go.kr")                 |
| `category_root`  | string   | 루트 카테고리 ("이사" or "주택임대차") |
| `breadcrumb`     | string   | 경로 ("홈 > 책자형 > 주택임대차")      |
| `title`          | string   | 페이지 제목 (`<title>` 태그에서 파싱)  |
| `url`            | string   | 원본 URL                               |
| `content`        | string   | 본문 (UI 노이즈 제거됨)                |
| `content_length` | int      | 본문 길이                              |
| `law_citations`  | string[] | 법령 인용 (정규식 추출)                |
| `fetched_at`     | string   | 수집 날짜                              |

### 청킹 후 스키마 (19 필드, 팀 결정)

`chunk_easylaw.py` 출력. 청크 단위로 메타데이터 재계산/추가:

| 필드             | 분류          | 역할                                       |
| ---------------- | ------------- | ------------------------------------------ |
| `id`             | 🔴 필수       | 청크 고유 키                               |
| `doc_title`      | 🔴 필수       | 문서 제목 · **Azure에선 `title`로 매핑**   |
| `content`        | 🔴 필수       | 청크 본문                                  |
| `source_url`     | 🔴 필수       | easylaw 원문 링크                          |
| `parent_doc`     | 🔴 필수       | 원본 문서 ID (테스트 강제 필수, 중복 제거) |
| `category`       | 🔴 필수       | 분류 태그 (체크리스트 항목 분배)           |
| `breadcrumb`     | 🔴 필수       | 경로 (semantic config 포함)                |
| `related_laws`   | 🔴 필수       | 체크리스트 citation 연결                   |
| `applicable_to`  | 🟡 유지       | 자취/신혼/가족 필터                        |
| `contract_type`  | 🟡 유지       | 전세/월세/자가 필터                        |
| `region`         | 🟡 유지       | 전국/서울 등 지역 필터                     |
| `deadlines`      | 🟡 유지       | "14일 이내" · D-day                        |
| `fetched_at`     | 🟡 유지       | 수집 일자 · 신선도                         |
| `chunk_index`    | 🟡 유지       | 청크 순번                                  |
| `chunk_total`    | 🟡 유지       | 전체 청크 수                               |
| `source`         | 🟢 Azure 제외 | 상수 "easylaw". parent_doc으로 식별 가능   |
| `category_root`  | 🟢 Azure 제외 | breadcrumb 첫 segment로 복원 가능          |
| `content_length` | 🟢 Azure 제외 | 디버깅용. `len(content)`로 즉석 계산       |
| `penalties`      | ⚪ 이미 삭제  | 활용도 0.9% (커밋 bb59244)                 |

### Azure Field Mapping

```json
"fieldMappings": [
  {
    "sourceFieldName": "doc_title",
    "targetFieldName": "title"
  }
]
```

소스 19 필드 → Azure 15 필드 (🟢 3개 제외 + `doc_title`→`title` 매핑).

### 스크래퍼 품질 이슈 해결 (2026-04-19)

**문제**: 팀원 스크래퍼가 HTML `#contents` 통째로 추출 → UI 노이즈 혼입

- 카카오톡/페이스북/트위터 공유 버튼
- 저장/인쇄/즐겨찾기 버튼
- 탭 메뉴 (본문/판례/관련법령)
- 검색박스
- 접근성 라벨 ("인쇄체크", "주소복사", "새창으로 열림")

**해결**: 스크래퍼 로직 개선 (필드 유지, 추출 정확도 향상)

- 본문 컨테이너 타이트하게: `#ovDiv .ovDivbox`
- NOISE_SELECTORS 대폭 확장
- 접근성 텍스트 제거
- breadcrumb/title 추출 개선

**검증**: 7개 노이즈 키워드 grep 전부 0 매칭

---

## Index C — Video (유튜브 자막)

**Azure 인덱스명**: `video-index`  
**소스 필드 수**: 18개  
**Azure 업로드 필드 수**: 16개 (🟢 2개 제외 + video_title→title 매핑)  
**청크 수**: 147 (재검증 필요)  
**입력 파일**: `backend/data/raw/youtube_transcripts/*.json` (12개)  
**청크 파일**: `backend/data/indexes/index_c_youtube_chunks.jsonl`

### 팀 회의 확정 필드 (18개)

| 필드            | 분류          | 역할                  | 근거                             |
| --------------- | ------------- | --------------------- | -------------------------------- |
| `id`            | 🔴 필수       | 청크 고유 키          | Azure document key               |
| `video_id`      | 🔴 필수       | YouTube 영상 고유 ID  | 영상 식별자                      |
| `video_title`   | 🔴 필수       | 영상 제목             | **Azure에선 `title`로 매핑**     |
| `content`       | 🔴 필수       | 자막 텍스트           | 주 검색 대상                     |
| `source_url`    | 🔴 필수       | YouTube 영상 기본 URL | Citation 링크                    |
| `channel`       | 🔴 필수       | 채널명                | Semantic keywords                |
| `deep_link`     | 🔴 필수       | 타임스탬프 포함 URL   | 클릭 시 정확 시점 재생           |
| `category`      | 🔴 필수       | 분류 태그             | filter/facet                     |
| `start_seconds` | 🟡 유지       | 시작 시점 (초)        | "11분 55초부터" 자연어 표시      |
| `end_seconds`   | 🟡 유지       | 종료 시점 (초)        | 클립 끝 시간                     |
| `timecode`      | 🟡 유지       | "11:55-14:23"         | 표시용                           |
| `applicable_to` | 🟡 유지       | 자취/신혼/가족        | 사용자 프로필 필터               |
| `contract_type` | 🟡 유지       | 전세/월세/자가        | 계약 유형 필터                   |
| `region`        | 🟡 유지       | 전국/서울 등          | 지역 필터                        |
| `related_laws`  | 🟡 유지       | 영상 ↔ 법 연결        | 크로스 링크                      |
| `fetched_at`    | 🟡 유지       | 수집 일자             | 신선도                           |
| `channel_url`   | 🟢 Azure 제외 | 채널 홈 URL           | `video_id`로 역추적 가능         |
| `source_type`   | 🟢 Azure 제외 | 상수 "video"          | Azure unify 시 재설정되므로 중복 |

### Azure Field Mapping

```json
"fieldMappings": [
  {
    "sourceFieldName": "video_title",
    "targetFieldName": "title"
  }
]
```

소스 18 필드 → Azure 16 필드 (🟢 2개 제외 + `video_title`→`title` 매핑).

### 청킹 전략

- 목표 청크 크기: 600자
- 시간 기반 묶음 (자막 세그먼트 연속)
- `deep_link` 자동 생성: `https://www.youtube.com/watch?v={video_id}&t={start_seconds}s`

### 다음 세션 검증 필요

- `ingest_youtube.py`에 Mac 하드코딩 경로 있는지
- 기존 `index_c_youtube_chunks.jsonl`이 18 필드 전부 포함하는지
- 없다면 스크립트 보강 후 재생성

---

## 크로스-인덱스 관계

### law ↔ guide

- `related_laws` 필드(guide)가 법령 참조 → Azure Search lookup 쿼리로 law 인덱스 조회 가능
- Phase 2: guide 청크의 `related_laws` 필드에 law id 역주입

### law ↔ video

- `related_videos` 필드(law) 하드코딩 매핑 — 법 단위로 영상 3~4개 큐레이션
- LAW_TO_VIDEOS 딕셔너리 (`ingest_laws.py`)

### video ↔ law

- `related_laws` 필드(video) — 영상이 어떤 법을 다루는지
- 현재 수동 큐레이션 추정 (다음 세션 검증)

### guide ↔ video

- 현재 직접 관계 없음
- Phase 2: vector similarity로 자동 매핑 고려

---

## 필드 결정 히스토리

### 2026-04-18 (세션 1)

- Law 스키마 초기 버전: 11 필드 (`keywords` 제거 방향이었음)
- `penalties`, `keywords`, `law_slug` 제거 결정 (잠정)
- `related_videos` 검증: 환각 아니라 수동 큐레이션 확인

### 2026-04-19 (세션 2)

- **팀 회의 결과 반영**:
  - Law 13 필드 확정 (`keywords` 유지 재결정)
  - Guide 19 필드 확정
  - Video 18 필드 확정
  - 🔴🟡🟢⚪ 분류 체계 도입
  - 소스 JSONL vs Azure 인덱스 스키마 분리 원칙
- Guide 스크래퍼 품질 개선 (필드 불변, 추출 로직만)
- Indexer fieldMappings 방식 채택 (로컬 JSONL 수정 회피)

---

## Azure Search 설정 (다음 세션 확정)

### Vector search

- Algorithm: HNSW (기본)
- Dimensions: 1536 (text-embedding-3-small)
- Similarity: cosine

### Semantic search

- Config name: `iim-{index}-semantic-config`
- Title field: `title` (law) / `title` (guide, after mapping) / `title` (video, after mapping)
- Content fields: `content`
- Keywords fields:
  - Law: `keywords`, `category`, `law_name`
  - Guide: `category`, `breadcrumb`
  - Video: `category`, `channel`

### Analyzer

- Language: `ko.microsoft` (한국어 최적)
- 모든 searchable 한글 필드에 적용

### Indexer 파이프라인 (다음 세션)

```
┌─────────────────────────────────────────────────────────────┐
│ Azure Blob Storage                                          │
│  └─ iim-data-container/                                     │
│      ├─ law/index_a_chunks.jsonl                            │
│      ├─ guide/index_b_chunks_curated.jsonl                  │
│      └─ video/index_c_youtube_chunks.jsonl                  │
└───────────────┬─────────────────────────────────────────────┘
                │
        ┌───────┴────────┬──────────────┐
        ▼                ▼              ▼
    ┌────────┐      ┌────────┐     ┌────────┐
    │Datasrc │      │Datasrc │     │Datasrc │
    │ (law)  │      │(guide) │     │(video) │
    └───┬────┘      └───┬────┘     └───┬────┘
        │               │              │
        ▼               ▼              ▼
    ┌────────┐      ┌────────┐     ┌────────┐
    │Skillset│      │Skillset│     │Skillset│
    │(embed) │      │(embed) │     │(embed) │
    └───┬────┘      └───┬────┘     └───┬────┘
        │               │              │
        ▼               ▼              ▼
    ┌────────┐      ┌────────┐     ┌────────┐
    │Indexer │      │Indexer │     │Indexer │
    │+mappings│      │+mappings│    │+mappings│
    └───┬────┘      └───┬────┘     └───┬────┘
        │               │              │
        ▼               ▼              ▼
    ┌────────┐      ┌────────┐     ┌────────┐
    │iim-law │      │iim-    │     │iim-    │
    │-index  │      │guide-  │     │video-  │
    │        │      │index   │     │index   │
    └────────┘      └────────┘     └────────┘
```

각 Indexer에는 `fieldMappings` 선언:

- Guide: `doc_title` → `title`
- Video: `video_title` → `title`
- Law: 없음 (이름 일치)
