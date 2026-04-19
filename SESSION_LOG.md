# SESSION_LOG

세션별 진행 기록. 매 세션 끝에 업데이트.

---

## 최신 상태 (2026-04-19)

### 브랜치

- 현재: `experiment/schema-refactor`
- Fork: `liminal-cipher/isa-isangmu`
- Upstream: `wes0031-rgb/isa-isangmu`
- 최신 커밋: `94a40a8 feat(ingest): add keywords extraction + chunk_easylaw cross-platform path`
- **세션 4 변경사항은 미커밋 상태** (파일 rename + 스크립트 output 경로 수정)

### 브랜치 커밋 히스토리

```
94a40a8 feat(ingest): add keywords extraction + chunk_easylaw cross-platform path
a60332e docs: refresh _source_metadata via annotate_sources.py
33a31c8 refactor: improve easylaw scraper + regenerate corpus
21d830e data: regenerate law corpus with ASCII-safe schema
30015f5 (main) docs(backend): 팀원 온보딩용 README·가이드 4종 + .env.example 신규 작성
```

---

## 완료한 작업

### 2026-04-18/19 세션 1~2

#### Law 데이터 정비 (커밋 21d830e)

- `ingest_laws.py` 전면 재작성
  - LAWS 튜플에 영문 slug 추가 (ASCII-safe 파일명/ID)
  - LAW_TO_VIDEOS 하드코딩 매핑 (법별 영상 큐레이션)
  - `article_to_ascii()` 함수: "제3조의2" → "art3_2"
  - `penalties` 필드 제거 (커밋 bb59244 준수)
  - `keywords` 필드: 이전 세션에선 제거 방향이었으나 팀 회의 후 유지 결정
    (자동 추출 키워드로 검색 부스팅 효과)
  - `fetched_at` 필드명 통일
  - `encoding="utf-8"` (Windows 호환)
- 오염된 법령 파일 2개 복구
  - `주택임대차보호법시행령.json` (조세특례제한법 내용으로 오염됐었음)
  - `주민등록법시행령.json` (빈 파일이었음)
- 파일명 한글 → 영문 slug 전환 (8개)
- 1,635 청크 생성 → `index_a_chunks.jsonl` (세션 4에서 `law_chunks.jsonl`로 rename)

#### Easylaw 스크래퍼 개선 (커밋 33a31c8)

- `ingest_easylaw.py` 전면 재설계
  - `ingest_easylaw_lease.py`와 통합 (--only 플래그로 카테고리 선택)
  - 하드코딩 Mac 경로 제거 → ROOT 기반 크로스플랫폼
  - 본문 추출 타이트하게: `#contents` 통째 → `#ovDiv .ovDivbox`
  - UI 노이즈 selector 대폭 확장 (공유/저장/인쇄/탭 UI)
  - 접근성 라벨 제거 (인쇄체크, 주소복사, 즐겨찾기에추가, 새창으로 열림)
  - `extract_breadcrumb`: `div.location div.fL` 타겟팅
  - `extract_title`: `<title>` 태그 파싱 (| → > → (본문) 제거)
- 53개 JSON 재생성 (22 이사 + 31 주택임대차)
- 검증: 7개 UI 노이즈 키워드 전부 0 매칭
- `ingest_easylaw_lease.py` 삭제

#### 메타데이터 카탈로그 갱신 (커밋 a60332e)

- `annotate_sources.py` 실행
- `_source_metadata` 필드를 모든 데이터 파일에 주입
- `DATA_SOURCES.md` 카탈로그 재생성

### 세션 1~2 주요 결정

- 팀의 "이사 스크래퍼 + 임대차 스크래퍼 분리"는 바이브 코딩 결과였음 → 통합이 맞음
- 필드 정당화 원칙 확립 ("모든 필드는 이유가 있어야")
- Indexer 파이프라인이 원래 계획, 발표 후 Direct Push에서 전환이 아님 (확장성 어필 포인트)
- 폴더명 리팩토링은 발표 후로 (영향 범위 때문)
- **팀 회의(4/19) 스키마 확정**:
  - Law 13 필드 (`keywords` 유지 재결정)
  - Guide 19 필드
  - Video 18 필드
  - 소스 JSONL은 전부 유지, Azure 업로드 시 🟢 필드 제외
  - 이름 변경은 Indexer `fieldMappings`로 처리

---

### 2026-04-19 세션 3 (커밋 94a40a8)

#### `chunk_easylaw.py` 크로스플랫폼 리팩토링

- Mac 하드코딩 경로 (`/Users/sa/Desktop/2차프로젝트/...`) 제거
- `ROOT = Path(__file__).resolve().parent.parent.parent` 방식 (ingest_laws.py, ingest_easylaw.py 와 동일 패턴)
- `from collections import Counter` 상단 import로 이동
- 빈 입력 디렉토리 guard 추가
- 필드 구조 19개 그대로 유지 (Guide 스키마 일치)
- 재청킹 결과: **340 청크, 평균 580자** (`index_b_chunks.jsonl`, 세션 4에서 `guide_chunks.jsonl`로 rename)
  - law citation 커버리지 230/340 (68%)
  - deadline 27건, penalty 10건 추출

#### `ingest_laws.py` keywords 자동 추출 추가

팀 4/19 회의에서 `keywords` 유지 재결정 → 추출 로직 구현.

- **DOMAIN_KEYWORDS** frozenset (~60개): 법률·이사 도메인 핵심 용어
  - 카테고리: 임대차 권리 / 계약 / 등기·담보 / 경매·매매 / 행정 신고 / 반려동물 / 공동주택 관리 / 벌칙 / 민법 기본
  - 팀원이 주석 보며 직접 편집 가능하도록 설계
- **`_strip_postposition()`**: 한국어 조사 후치 제거 ("등록대상동물의" → "등록대상동물")
  - 긴 조사 (`으로`, `에서` 등) 먼저 시도 → 짧은 조사 (`의`, `을`, `이` 등)
  - 결과가 2자 이상일 때만 제거 (과도한 절단 방지)
- **`extract_keywords(title, content, law_name)`**: 3단계 하이브리드
  1. 조문 제목 파싱 (괄호 유무 무관, 공백/중점 split, 조사 제거, stopwords 필터)
  2. DOMAIN_KEYWORDS 본문 매칭 (짧은 조문 1회 / 긴 조문 2회 이상)
  3. 법 이름 (공백 제거) 추가
  - 최대 12개, 정렬 출력
- **설계 철학**: Precision-first (Whitelist 방식)
  - 팀원의 Blacklist 방식 대비 noise 0 ("관하여" 같은 법조문 상투어 차단)
  - Azure Semantic ranker `keywordsFields` 힌트로 쓸 때 품질 보장
  - 단점 (새 용어 수동 추가)은 팀원 편집 가능한 사전으로 완화
- **의존성 0**: konlpy 등 JVM 기반 NLP 미사용 → 팀원 Windows 온보딩 부담 없음

#### 재생성 결과

- **Law chunks**: 1,635 청크 (회귀 0)
  - 민법 1,094 / 부동산등기법 118 / 공동주택관리법 104 / 동물보호법 102 / 주민등록법 시행령 86 / 주민등록법 55 / 주택임대차보호법 41 / 주택임대차보호법 시행령 35
  - keywords: **평균 3.9개/청크, 1,635/1,635 커버리지 100%**
  - 육안 샘플 검증 OK — "관하여", "관한" 등 상투어 0건
- **Guide chunks**: 340 청크, 평균 580자

#### 회귀 테스트

- `pytest tests/test_ingest_laws_filter.py -v` → **13/13 PASS**
- `should_skip_article`, `is_deleted_article` API 보존됨

#### 세션 3 주요 결정

- **keywords 전략**: Whitelist precision-first, 추출 개선은 Phase 2
  - 중간 발표 없고 4/26이 final → 최적화는 premature
  - 검색 품질 A/B는 query-time `searchFields` 토글로 측정 (인덱스 재빌드 불필요)
- **통계 기반 불용어 사전 구축**은 Phase 2로 연기
  - 필요시 `Counter(re.findall(r"[가-힣]{2,}", content))` 상위 200개 수동 검토 워크플로우 정리 완료

---

### 2026-04-19 세션 4 (미커밋)

**성과**: Azure AI Search에 3-index 파이프라인 구축 완료. 1,635 + 340 + 147 = **총 2,122 청크** 인덱싱 + 하이브리드 검색 검증.

#### JSONL 파일명 일관화

기존 네이밍(`index_a_`, `index_b_`, `index_c_youtube_`)이 비대칭적이고 내용 타입 표현 불명확 → 리소스·Blob 경로와 일치하는 내용 기반 이름으로 통일:

- `index_a_chunks.jsonl` → `law_chunks.jsonl`
- `index_b_chunks.jsonl` → `guide_chunks.jsonl`
- `index_b_summary.json` → `guide_summary.json`
- `index_c_youtube_chunks.jsonl` → `video_chunks.jsonl`

스크립트 output 경로도 함께 수정:

- `ingest_laws.py`: `INDEX_A_PATH` 상수 값 `law_chunks.jsonl`로
- `chunk_easylaw.py`: output 파일명 2개 수정

**미커밋 상태** — 다음 세션 시작 시 커밋 필요.

#### Azure 리소스 프로비저닝 (Portal)

**공용 리소스**:

- Azure AI Search: `iim-ai-search` (기존)
- Azure OpenAI: `iim-openai` (신규 생성, Foundry 방식, `cognitiveservices.azure.com` 엔드포인트)
  - Embedding 배포: `text-embedding-3-small`, 1536 dim
- Storage Account: `isaisangmustorage` (기존)
- Blob Container: `iim-rag-source` (기존)

**네이밍 결정**: Azure 리소스는 `iim-` prefix 유지, 인덱스 내부 리소스는 prefix 생략 (리소스 격리는 서비스 레벨에서 이미 담보됨, 중복 방지).

#### 3-index 파이프라인 구성

**Blob Storage 구조**:

```
iim-rag-source/
├── law/law_chunks.jsonl       (1,635 청크)
├── guide/guide_chunks.jsonl   (340 청크)
└── video/video_chunks.jsonl   (147 청크)
```

**Azure AI Search 리소스** (Portal → Add (JSON) 방식으로 복붙 생성):

| 리소스 유형     | Law                   | Guide                   | Video                   |
| --------------- | --------------------- | ----------------------- | ----------------------- |
| Index           | `law-index`           | `guide-index`           | `video-index`           |
| Datasource      | `law-datasource`      | `guide-datasource`      | `video-datasource`      |
| Skillset        | `law-skillset`        | `guide-skillset`        | `video-skillset`        |
| Indexer         | `law-indexer`         | `guide-indexer`         | `video-indexer`         |
| Semantic config | `law-semantic-config` | `guide-semantic-config` | `video-semantic-config` |
| Vector profile  | `law-vector-profile`  | `guide-vector-profile`  | `video-vector-profile`  |

**공통 설정**:

- Vector: 1536 dim, HNSW, cosine
- Analyzer: `ko.microsoft` (한국어 searchable 필드 전부)
- Indexer parsing mode: `jsonLines`
- Embedding: Azure OpenAI `text-embedding-3-small` skill
- CORS: `allowedOrigins: ["*"]` (개발용)

**Field Mappings**:

- Guide: `doc_title` → `title`
- Video: `video_title` → `title`
- Law: identity mapping (소스명 = 타겟명)

**Azure 업로드 필드 수** (소스 JSONL 필드 중 🟢 제외 + content_vector 파생):

- Law: 12 소스 + content_vector = 13
- Guide: 15 소스 (source/category_root/content_length/penalties 제외) + content_vector = 16
- Video: 16 소스 (channel_url/source_type 제외) + content_vector = 17

#### 인덱싱 결과

- `law-index`: **1,635 docs** (maxFailedItems 사용 0)
- `guide-index`: **340 docs** (maxFailedItems 사용 0)
- `video-index`: **147 docs** (maxFailedItems 사용 0)

데이터 손실 전혀 없음. 임베딩 생성 비용 ~$0.05 미만.

#### 검증 쿼리 결과

**Law 인덱스** — Search Explorer에서 3개 쿼리 실행:

1. **단순 키워드** (`"전입신고"`): ✅ BM25 정상 작동. 주민등록법 전입신고 관련 조항 top 5 노출.
2. **Semantic ranker** (`"전입신고 기한은 언제까지인가요"`): ✅ 주민등록법 제16조 (거주지의 이동, 14일 이내) top 1. `@search.answers` 추출 성공 (score 0.994, "14일 이내" 정확히 하이라이트).
3. **하이브리드 벡터** (`"확정일자를 받으면 무슨 효력이 생기나요"`): ✅ 주택임대차보호법 제3조의6 (확정일자 부여) top 4에 포함. `keywords` 필드 retrieve 정상 (세션 3에서 추출한 용어 그대로 살아있음). 일부 relevance tuning 여지 있으나 LLM이 top 5 context로 답 생성할 수준은 충분.

**Guide 인덱스** — 하이브리드 쿼리 (`"전입신고를 어떻게 하나요"`): ✅ "전입신고하기" 문서 청크 top 4 차지. `related_laws`에 `주민등록법 제16조·17조·40조·시행령 제23조` 정확 파싱됨. Guide↔Law 크로스 링크 재료 확보.

**Video 인덱스** — 하이브리드 쿼리 (`"이사할 때 빼먹으면 안 되는 것"`): ✅ "[5분 순삭] 이사 6가지" 영상 top 1 (timecode 00:00). **`deep_link` 타임스탬프 URL 정상 작동** (`&t=187s` 등) — 발표 데모에서 "영상의 특정 구간 점프" 어필 포인트.

#### 세션 4 주요 결정

- **파일명 일관화**를 발표 전에 처리 (미루면 정리 비용 커짐)
- **Azure 리소스 JSON은 repo에 저장하지 않고 Portal에서 직접 관리** — 발표 후 Phase 2에서 `backend/schemas/` 디렉토리에 정리본 커밋 예정
- **Guide `related_laws` 파싱**: `chunk_easylaw.py`의 citation regex가 "주민등록법 제16조 제1항" 등 조·항 수준까지 정확 추출 확인 → Phase 2에서 law-index에 역링크 쿼리로 활용 가능
- **Video `deep_link`**: 영상 타임스탬프 URL 자동 생성 확인, 챗봇 citation에 바로 사용 가능한 상태

---

## 진행 중

- **미커밋 변경사항 (세션 4)**:
  - JSONL 파일 3개 rename (`law_chunks.jsonl`, `guide_chunks.jsonl`, `video_chunks.jsonl`)
  - `guide_summary.json` rename
  - `ingest_laws.py` INDEX_A_PATH 값 변경
  - `chunk_easylaw.py` 출력 파일명 2개 변경
  - 다음 세션 시작 시 1개 커밋으로 묶어서 푸시

---

## 다음 세션 우선순위 (6일 남음, 최종 발표 4/26)

### 필수

1. **세션 4 변경사항 커밋 + 푸시**
   - 커밋 메시지 예시: `refactor: rename JSONL files for naming consistency (law/guide/video)`
   - Fork main sync

2. **백엔드 코드 3-index 쿼리로 전환** ⭐ 최우선
   - `chat_service.py`: 기존 unified 인덱스 호출 → `law-index`, `guide-index`, `video-index` 3곳 병렬 쿼리 후 병합
   - `checklist_service.py`: 동일 패턴
   - `source_type` 필터 대신 인덱스 이름으로 분기
   - 검증: `/health`, `/chat`, `/checklist` 엔드포인트 로컬 동작 확인

3. **Azure App Service 배포**
   - FastAPI 앱 배포 → 퍼블릭 URL 확보
   - Expo 앱에서 배포 URL 호출 확인
   - MS AI School 평가 포인트 (클라우드 배포 역량)

4. **골든 쿼리 30건 검증 + 비교**
   - 팀 unified index vs 내 3-index 결과 비교
   - nDCG@5, MRR 등 간단한 지표 기록
   - 발표 자료의 "숫자" 확보

5. **발표 자료 준비**
   - 아키텍처 다이어그램 (Blob → Indexer → 3-index → FastAPI → Expo)
   - 핵심 숫자 (2,122 청크, 커버리지, keywords 통계, query latency)
   - 데모 시나리오 (챗봇 질문 → 3-index 하이브리드 → citation with video timestamp)

### 선택 (시간 되면)

6. **`curate_chunks.py` 정비 + 재큐레이션**
   - Mac 하드코딩 경로 수정
   - EXCLUDE_DOCS 재검토 (666/629 out-of-scope 목록)
   - 출력: `guide_chunks_curated.jsonl`
   - Guide 인덱스 재인덱싱 여부는 품질 차이 측정 후 결정

7. **`ingest_youtube.py` 확인**
   - Mac 하드코딩 경로 체크
   - 필드 구성 검증 (video-index 인덱싱 성공으로 1차 검증됨)

8. **Azure 리소스 정의 JSON을 repo에 커밋**
   - `backend/schemas/law-index.json`, `guide-index.json`, `video-index.json` 등
   - 재현성 확보 (Portal 없이 스크립트로 재생성 가능하게)

9. `ingest_services_v2.py` 상태 파악 (내용 확인 후 rename/삭제 결정)

10. `.env` vs `backend/.env` 이원화 정리

### Phase 2 (발표 후)

- 폴더 구조 리팩토링 (`procedures/` → `guides/` 등)
- `related_procedures` vector similarity로 채우기
- 개인화 DB 분리 (`applicable_to` 등을 user profile로)
- SETUP.md의 `msai09sa` 노출 팀에 PR
- keywords 추출 A/B 실험 (whitelist vs blacklist+auto-stopwords)
- 통계 기반 불용어 사전 구축 (상위 200개 수동 검토)
- Guide↔Law 크로스 링크 (`related_laws` → law-index lookup)

---

## 미해결 이슈

### 환경

- `.env` vs `backend/.env` 중복 — config.py가 어디 보는지 확인 후 통합
- Python 3.13에서 잘 동작하나 3.12 호환성 검증 안 됨

### 데이터

- `raw/youtube_transcripts/` 12개 파일 품질 미검증 (video-index 인덱싱 성공으로 최소 스키마는 OK)
- `mapping/` 30+ 파일은 인덱스에 안 올리지만, 스키마 정리 필요 여부 미확인
- `curate_chunks.py` 아직 정비 안 됨 (현재 guide-index는 큐레이션 전 원본 340 청크 사용)

### 문서 동기화

- `SCHEMA_DECISION.md`의 필드 이름 `last_updated` → 실제 JSONL·Azure 스키마엔 `fetched_at`만 존재 (정정 필요)
- Azure 인덱스 이름 `iim-law-index` (SCHEMA_DECISION 문서) vs 실제 `law-index` (Portal에서 생성한 이름) — 문서 업데이트 필요
- `backend/schemas/` 디렉토리에 인덱스 정의 JSON 미커밋 (Portal에서만 존재)

### 팀 관계

- SETUP.md에 `msai09sa` 팀 ID 노출
- 팀의 현재 unified index 쿼리 품질 베이스라인 기록 필요 (비교 기준)

---

## 환경 체크리스트

### 현재 세션 종료 시점 (2026-04-19 세션 4)

- [x] 세션 3 작업 커밋됨 (94a40a8)
- [x] origin/experiment/schema-refactor에 push 완료 (세션 3까지)
- [x] Azure 3-index 파이프라인 구축 완료 (law-index, guide-index, video-index)
- [x] 인덱싱 완료: 1,635 + 340 + 147 = 2,122 docs
- [x] 하이브리드 검색 검증 (Law 3건, Guide 1건, Video 1건)
- [ ] 세션 4 파일 rename + 스크립트 수정 미커밋 ← 다음 세션 시작 시
- [ ] Fork main에 merge ← 다음 세션 시작 전

### 다음 세션 시작 시

- [ ] `experiment/schema-refactor` 브랜치에서 시작
- [ ] 세션 4 미커밋 변경사항 먼저 커밋
- [ ] `git pull origin experiment/schema-refactor` (원격 최신 반영)
- [ ] DEVLOG.md, SESSION_LOG.md 재확인
