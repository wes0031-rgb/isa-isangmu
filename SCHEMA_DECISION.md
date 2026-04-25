# SCHEMA_DECISION

3-index 의 각 필드별 설계 근거 기록. "왜 이 필드가 존재/제거됐는가?"의 영구 답변.

**현재 구성**: 3-index — `law-index`, `guide-index`, `mapping-index`. Video 인덱스는 저작권 우려로 2026-04-23 제거됨 (commit `5cb0ec1`).

---

## 원칙

모든 필드는 다음 중 하나의 질문에 답할 수 있어야 함:

1. **검색 용도**: 이 필드로 어떤 쿼리를 받을 수 있는가?
2. **필터 용도**: 이 필드로 어떤 결과를 좁힐 수 있는가?
3. **표시 용도**: UI 에서 어떻게 사용자에게 보여주는가?
4. **추적 용도**: 데이터 품질·신선도를 어떻게 검증하는가?

답할 수 없는 필드는 제거 대상.

---

## 소스 JSONL vs Azure 인덱스 스키마

팀 회의(4/19)에서 스키마를 네 레벨로 분류:

| 분류         | 의미                   | 소스 JSONL               | Azure 인덱스 |
| ------------ | ---------------------- | ------------------------ | ------------ |
| 🔴 필수      | 항상 있어야            | ✅ 포함                  | ✅ 포함      |
| 🟡 유지      | 유용함, 일단 유지      | ✅ 포함                  | ✅ 포함      |
| 🟢 삭제 OK   | Azure 에 안 올려도 됨  | ✅ 포함 (소스 원형 보존) | ❌ 제외      |
| ⚪ 이미 삭제 | 스크래핑/청킹에서 제외 | ❌ 제외                  | ❌ 제외      |

### 이름 변경 처리 (Indexer fieldMappings)

일부 필드는 소스 이름과 Azure 이름이 다름:

| 소스 필드   | Azure 필드 | 인덱스 |
| ----------- | ---------- | ------ |
| `doc_title` | `title`    | Guide  |

**처리 방법**: Azure Indexer 의 `fieldMappings` 선언.

```json
"fieldMappings": [
  {
    "sourceFieldName": "doc_title",
    "targetFieldName": "title"
  }
]
```

**소스 JSONL 은 수정 불필요.** Indexer 가 읽을 때 매핑.

### 🟢 필드 제외 방법

Azure 인덱스 스키마에서 해당 필드를 **선언하지 않으면** Indexer 가 자동 무시. 별도 drop 처리 불필요.

### 로컬 파일 수정이 필요한 경우

현재 수집된 데이터는 **그대로 유지**. 다음 경우에만 로컬 수정:

1. Python 코드(예: `unify_indexes.py`)가 JSONL 읽어 필드 참조할 때
2. 스키마 검증 테스트를 로컬에서 돌릴 때

**원칙**: Azure 로 넘기기 전까지 소스 원형 보존 → 재인덱싱 유연성 최대화.

---

## Index A — Law (법령 조문)

**Azure 인덱스명**: `law-index`
**소스 필드 수**: 12 개
**Azure 업로드 필드 수**: 12 개
**청크 수**: 1,635 (2026-04-19 기준)
**입력 파일**: `backend/data/law/*.json` (8 개 법령)
**청크 파일**: `backend/data/indexes/law_chunks.jsonl`

### 확정 필드 (12 개)

| 필드                 | 분류          | 역할                                 | 근거                          |
| -------------------- | ------------- | ------------------------------------ | ----------------------------- |
| `id`                 | 🔴 필수       | 청크 고유 키 (Azure key)             | ASCII-only, document key 제약 |
| `title`              | 🔴 필수       | 조문 제목 · semantic 최우선          | 예: "대항력 등"               |
| `content`            | 🔴 필수       | 조문 본문                            | 주 검색 대상, 벡터 임베딩     |
| `source_url`         | 🔴 필수       | law.go.kr 원문 링크                  | Citation 클릭 시 이동         |
| `law_name`           | 🔴 필수       | "주택임대차보호법"                   | Semantic keywords             |
| `article`            | 🔴 필수       | "제3조의2"                           | Citation 표시                 |
| `category`           | 🔴 필수       | 분류 태그                            | filter/facet                  |
| `keywords`           | 🔴 필수       | 자동 추출 키워드                     | 검색 부스팅                   |
| `deadlines`          | 🟡 유지       | "14일 이내"                          | D-day 계산 근거               |
| `related_procedures` | 🟡 유지       | 법 ↔ 절차 크로스 링크                | guide 청크와 연결             |
| `related_videos`     | ⚠️ orphan     | 영상 인덱스 제거됨, 데이터엔 잔존    | 다음 재생성 시 제거 권장      |
| `fetched_at`         | 🟡 유지       | 수집 일자 · 신선도                   | `last_updated` 는 미사용      |
| `penalties`          | ⚪ 이미 삭제  | 활용도 0.9%                          | -                             |

**스크립트 현황**:

- `ingest_laws.py` 가 `keywords` 자동 추출 (DOMAIN_KEYWORDS ~60 개 whitelist)
- `fetched_at` 만 생성 (`last_updated` 는 제거됨)

### 청크 ID 형식

```
law_{slug}_art{N}[_{sub}]

예시:
  law_housing_lease_protection_art1
  law_housing_lease_protection_art3_2  (제3조의2)
  law_civil_code_art618
```

**이유**: Azure Search document key 는 letters/digits/underscores/dashes/equals 만 허용.

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
- Stub: content 길이 40 자 미만

### Azure Field Mapping

특별한 매핑 없음 (소스 필드명 = Azure 필드명).

---

## Index B — Guide (생활법령 해설)

**Azure 인덱스명**: `guide-index`
**소스 필드 수**: 19 개
**Azure 업로드 필드 수**: 15 개 (🟢 3 개 제외 + `doc_title`→`title` 매핑)
**청크 수**: 340 (raw, 큐레이션 단계 제거됨)
**입력 파일**: `backend/data/guide/*.json` (53 개)
**청크 파일**: `backend/data/indexes/guide_chunks.jsonl`

> **큐레이션 제거 (commit `4d0a66c`)**: `curate_chunks.py` 가 EXCLUDE_DOCS 정리 후 pass-through 가 되어 chatbot 용도엔 scope filter 가 불필요. `index_b_chunks_curated.jsonl` 도 함께 제거.

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

### 청킹 후 스키마 (19 필드)

`chunk_easylaw.py` 출력. 청크 단위로 메타데이터 재계산/추가:

| 필드             | 분류          | 역할                                       |
| ---------------- | ------------- | ------------------------------------------ |
| `id`             | 🔴 필수       | 청크 고유 키                               |
| `doc_title`      | 🔴 필수       | 문서 제목 · **Azure 에선 `title` 로 매핑** |
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
| `penalties`      | 🟡 유지       | 위반 시 효과 (데이터엔 살아있음)           |
| `source`         | 🟢 Azure 제외 | 상수 "easylaw". `parent_doc` 으로 식별 가능 |
| `category_root`  | 🟢 Azure 제외 | `breadcrumb` 첫 segment 로 복원 가능       |
| `content_length` | 🟢 Azure 제외 | 디버깅용. `len(content)` 로 즉석 계산      |

### Azure Field Mapping

```json
"fieldMappings": [
  {
    "sourceFieldName": "doc_title",
    "targetFieldName": "title"
  }
]
```

소스 19 필드 → Azure 15 필드 (🟢 3 개 제외 + `doc_title`→`title` 매핑).

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

**검증**: 7 개 노이즈 키워드 grep 전부 0 매칭

---

## Index C — Mapping (기관·실무 정보)

**Azure 인덱스명**: `mapping-index`
**소스 필드 수**: 16 개
**Azure 업로드 필드 수**: 16 개
**청크 수**: 122 (2026-04-21 기준)
**입력 파일**: `backend/data/mapping/*.json` (31 개)
**청크 파일**: `backend/data/indexes/mapping_chunks.jsonl`
**정규화 스크립트**: `backend/scripts/normalize_mapping_for_rag.py` (994 줄)

> **이 인덱스만 정규화가 필수인 이유**: law/guide 와 달리 **다출처** (한전·수도사업소·도시가스·통신사·HUG·등기소·주민센터·법무부 양식 등) 데이터를 한 인덱스에 담기 때문에, 출처마다 다른 필드 형식을 공통 스키마로 맞추는 정규화 단계가 반드시 필요.

### 9 개 패턴별 핸들러

`normalize_mapping_for_rag.py` 가 입력 파일의 구조를 보고 9 개 패턴 중 하나로 분기:

| 패턴            | 청크 수 | 예시 파일                                                          |
| --------------- | ------- | ------------------------------------------------------------------ |
| simple          | 18      | hometax_nts, nhis_health_insurance, nps_national_pension 등 (1:1) |
| regional        | 36      | kepco_electricity (18) · water_region_office (18)                  |
| mapping_table   | 18      | (지역 ↔ 사업자 매핑류)                                              |
| multi_level     | 21      | school_transfer (초·중·고 + 시도교육청)                              |
| multi_provider  | 4       | telecom_internet (KT/SK/LGU+)                                      |
| categorized_sub | 7       | gov24_services                                                     |
| guide_phases    | 8       | moveout_timeline                                                   |
| guide_stages    | 6       | moveout_deposit_return                                              |
| guide_generic   | 4       | moveout_restoration · waste_disposal · management_refund · termination_notice |

### 확정 필드 (16 개)

| 필드               | 분류    | 역할                                      |
| ------------------ | ------- | ----------------------------------------- |
| `id`               | 🔴 필수 | 청크 고유 키 (Azure document key)         |
| `source_id`        | 🔴 필수 | 사람이 읽는 원본 ID (디버깅·매핑용)       |
| `title`            | 🔴 필수 | 서비스/항목명 · semantic 최우선           |
| `content`          | 🔴 필수 | 본문 (벡터 임베딩 대상)                   |
| `authority`        | 🔴 필수 | 담당 기관 (한전/수도사업소/주민센터 등)   |
| `service_category` | 🔴 필수 | 분류 태그 (utility/registry/welfare 등)   |
| `fetched_at`       | 🔴 필수 | 수집 일자 · 신선도                        |
| `region`           | 🟡 유지 | 관할 지역 (전국/서울/경기 등)             |
| `region_aliases`   | 🟡 유지 | 지역명 별칭 (검색 매칭용)                 |
| `phones`           | 🟡 유지 | 연락처 배열 (대표번호·지점별)             |
| `websites`         | 🟡 유지 | URL 배열 (홈/신청 페이지 등)              |
| `process_steps`    | 🟡 유지 | 단계별 안내 (체크리스트 항목 분배)        |
| `deadline_days`    | 🟡 유지 | 기한 (일 단위) · D-day 계산               |
| `penalty_text`     | 🟡 유지 | 위반 시 효과 (과태료·계약 해지 등)        |
| `legal_basis`      | 🟡 유지 | 근거 법령 (법 ↔ 매핑 크로스 링크)          |
| `tips`             | 🟡 유지 | 추가 안내·주의사항                        |

### Azure document key 처리

한글 `source_id` (예: `kepco_electricity__seoul`) 는 그대로 사용 가능하나, 한글이 섞이는 케이스는 `slugify()` + `REGION_SLUG` / `LEVEL_SLUG` 로 ASCII 변환. ID 중복·non-ASCII 검증 로직이 정규화 스크립트에 내장.

### Azure Field Mapping

특별한 매핑 없음 (소스 필드명 = Azure 필드명).

---

## 크로스-인덱스 관계

### law ↔ guide

- `related_laws` 필드(guide) 가 법령 참조 → Azure Search lookup 쿼리로 law 인덱스 조회
- `related_procedures` 필드(law) → guide 청크와의 역방향 연결

### law ↔ mapping

- `legal_basis` 필드(mapping) → 근거 법령 인용으로 law 인덱스 조회 가능
- 예: `moveout_termination_notice` 의 `legal_basis` → 주택임대차보호법 제6조의2

### guide ↔ mapping

- 현재 직접 관계 없음
- 필요 시 vector similarity 로 자동 매핑 가능

---

## 필드 결정 히스토리

### 2026-04-18 (세션 1)

- Law 스키마 초기 버전: 11 필드 (`keywords` 제거 방향이었음)
- `penalties`, `keywords`, `law_slug` 제거 결정 (잠정)
- `related_videos` 검증: 환각 아니라 수동 큐레이션 확인

### 2026-04-19 (세션 2) — 팀 회의

- Law 12 필드 확정 (`keywords` 유지 재결정)
- Guide 19 필드 확정
- Video 18 필드 확정 (이후 제거)
- 🔴🟡🟢⚪ 분류 체계 도입
- 소스 JSONL vs Azure 인덱스 스키마 분리 원칙
- Indexer fieldMappings 방식 채택 (로컬 JSONL 수정 회피)

### 2026-04-21 (세션 3) — Mapping 인덱스 신설 (commit `089055e`)

- 31 개 매핑 파일을 9 개 패턴별 핸들러로 정규화 → 122 청크
- Mapping 전용 16 필드 스키마 확정
- `parent_service` 필드 제거 (`source_id` 와 중복)
- ID 중복/non-ASCII 검증 로직 추가
- Azure 리소스 5종 JSON (index/datasource/skillset/indexer + semantic) 정의

### 2026-04-23 — Video 인덱스 제거 (commit `5cb0ec1`)

- 저작권 우려로 유튜브 자막 인덱스 전면 제거
- Law 의 `related_videos` 필드는 데이터에 잔존 (orphan, 다음 재생성 시 제거 권장)

### 2026-04-24 — 큐레이션 단계 제거 (commit `4d0a66c`)

- `curate_chunks.py` 가 EXCLUDE_DOCS 정리 후 pass-through 화 → 삭제
- `index_b_chunks_curated.jsonl` (200 청크) 도 함께 제거
- 이후 Guide 인덱스는 raw 청크 340 개를 그대로 사용

---

## Azure Search 설정 (확정)

### Vector search

- Algorithm: HNSW
- Dimensions: 1536 (text-embedding-3-small)
- Similarity: cosine

### Semantic search

각 인덱스별 semantic config:

| 인덱스        | Title field | Content field | Keywords fields                  |
| ------------- | ----------- | ------------- | -------------------------------- |
| law-index     | `title`     | `content`     | `keywords`, `category`, `law_name` |
| guide-index   | `title` (← `doc_title` mapped) | `content`, `breadcrumb` | `category` |
| mapping-index | `title`     | `content`     | `service_category`, `authority`, `region` |

### Analyzer

- Language: `ko.microsoft` (한국어 최적)
- 모든 searchable 한글 필드에 적용

### 리소스 정의

각 인덱스의 Azure 리소스 JSON (datasource/index/skillset/indexer + semantic) 은 `feat/3-index-rag-transition` 브랜치 (commit `089055e`) 에서 관리.
