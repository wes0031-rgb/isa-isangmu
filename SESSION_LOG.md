# SESSION_LOG

세션별 진행 기록. 매 세션 끝에 업데이트.

---

## 최신 상태 (2026-04-20)

### 브랜치

- 현재: `feat/3-index-rag-transition` (구 `experiment/schema-refactor`, 세션 5에서 rename)
- Fork: `liminal-cipher/isa-isangmu`
- Upstream: `wes0031-rgb/isa-isangmu` (건드리지 않음)
- 최신 커밋: `7e125e0 feat(chat): switch /chat to 3-index parallel hybrid search`

### 브랜치 커밋 히스토리

```
7e125e0 feat(chat): switch /chat to 3-index parallel hybrid search
07fe9bd feat(search): add 3-index hybrid search service layer
80ec60a fix(ingest_laws): replace residual INDEX_A_PATH with LAW_CHUNKS_PATH
eae077c refactor: rename JSONL files for naming consistency (law/guide/video)
f022400 docs: update SESSION_LOG with session 3
94a40a8 feat(ingest): add keywords extraction + chunk_easylaw cross-platform path
```

### 동작 상태

- **`/chat` 엔드포인트**: 3-index 하이브리드 전환 완료, Expo Go E2E 검증 완료 (폰 → 로컬 FastAPI → Azure → 답변 렌더링)
- **`/checklist` 엔드포인트**: 아직 팀 unified 호출 → Azure 실패 → local fallback → **hallucination 발생** (세션 5에서 실증)
- **`/safecontract` 엔드포인트**: 동일하게 미전환, law 검색 실패 상태

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
- 재청킹 결과: **340 청크, 평균 580자** (`index_b_chunks.jsonl`, 세션 4에서 `easylaw_chunks.jsonl`로 rename)
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

### 2026-04-19 세션 4 (커밋 eae077c, 80ec60a)

**성과**: Azure AI Search에 3-index 파이프라인 구축 완료. 1,635 + 340 + 147 = **총 2,122 청크** 인덱싱 + 하이브리드 검색 검증.

#### JSONL 파일명 일관화

기존 네이밍(`index_a_`, `index_b_`, `index_c_youtube_`)이 비대칭적이고 내용 타입 표현 불명확 → 리소스·Blob 경로와 일치하는 내용 기반 이름으로 통일:

- `index_a_chunks.jsonl` → `law_chunks.jsonl`
- `index_b_chunks.jsonl` → `easylaw_chunks.jsonl`
- `index_b_summary.json` → `easylaw_summary.json`
- `index_c_youtube_chunks.jsonl` → `video_chunks.jsonl`

스크립트 output 경로도 함께 수정:

- `ingest_laws.py`: `INDEX_A_PATH` 상수 값 `law_chunks.jsonl`로
- `chunk_easylaw.py`: output 파일명 2개 수정

#### Azure 리소스 프로비저닝 (Portal)

**공용 리소스**:

- Azure AI Search: `iim-ai-search` (기존)
- Azure OpenAI: `iim-openai` (신규 생성, Foundry 방식, `cognitiveservices.azure.com` 엔드포인트)
  - Embedding 배포: `text-embedding-3-small`, 1536 dim
  - Chat 배포: `gpt-4o` (세션 5에서 확인)
- Storage Account: `isaisangmustorage` (기존)
- Blob Container: `iim-rag-source` (기존)

**네이밍 결정**: Azure 리소스는 `iim-` prefix 유지, 인덱스 내부 리소스는 prefix 생략 (리소스 격리는 서비스 레벨에서 이미 담보됨, 중복 방지).

#### 3-index 파이프라인 구성

**Blob Storage 구조**:

```
iim-rag-source/
├── law/law_chunks.jsonl       (1,635 청크)
├── guide/easylaw_chunks.jsonl   (340 청크)
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

#### 검증 쿼리 결과 (Search Explorer)

**Law 인덱스**:

1. **단순 키워드** (`"전입신고"`): ✅ BM25 정상 작동. 주민등록법 전입신고 관련 조항 top 5 노출.
2. **Semantic ranker** (`"전입신고 기한은 언제까지인가요"`): ✅ 주민등록법 제16조 top 1. `@search.answers` 추출 성공 (score 0.994, "14일 이내" 정확히 하이라이트).
3. **하이브리드 벡터** (`"확정일자를 받으면 무슨 효력이 생기나요"`): ✅ 주택임대차보호법 제3조의6 top 4 포함. `keywords` 필드 retrieve 정상.

**Guide 인덱스** — 하이브리드 (`"전입신고를 어떻게 하나요"`): ✅ "전입신고하기" top 4 차지. `related_laws` 정확 파싱.

**Video 인덱스** — 하이브리드 (`"이사할 때 빼먹으면 안 되는 것"`): ✅ "[5분 순삭] 이사 6가지" top 1. **`deep_link` 타임스탬프 URL 정상 작동**.

#### 세션 4 주요 결정

- **파일명 일관화**를 발표 전에 처리 (미루면 정리 비용 커짐)
- **Azure 리소스 JSON은 repo에 저장하지 않고 Portal에서 직접 관리** — 발표 후 Phase 2에서 `backend/schemas/` 디렉토리에 정리본 커밋 예정
- **Guide `related_laws` 파싱 확인**: Phase 2에서 law-index 역링크 쿼리로 활용 가능
- **Video `deep_link` 확인**: 챗봇 citation에 바로 사용 가능

---

### 2026-04-20 세션 5 (커밋 07fe9bd, 7e125e0) — **백엔드 3-index 전환 1단계**

**성과**: `/chat` 엔드포인트를 팀 unified 호출에서 내 3-index 병렬 하이브리드로 전환 완료. 폰 Expo Go E2E 검증까지 성공.

**시간**: 2026-04-19 밤 23시 ~ 2026-04-20 새벽 03시 30분.

#### 브랜치 이름 변경

기존 `experiment/schema-refactor`는 세션 1~3의 스키마/데이터 정비 맥락이 붙은 이름이었으나, 세션 4 이후부턴 RAG 아키텍처 전환이 주 작업 → `feat/3-index-rag-transition`으로 rename.

```bash
git branch -m experiment/schema-refactor feat/3-index-rag-transition
git push origin -u feat/3-index-rag-transition
git push origin --delete experiment/schema-refactor
```

**원칙**: 브랜치 이름은 작업의 현재 성격을 반영해야. 이름-작업 불일치는 리뷰·커뮤니케이션 비용.

#### `backend/app/config.py` 확장

**추가된 필드 6개**:

- `azure_search_law_index` (기본값 `law-index`)
- `azure_search_guide_index` (기본값 `guide-index`)
- `azure_search_video_index` (기본값 `video-index`)
- `azure_search_law_semantic_config` (기본값 `law-semantic-config`)
- `azure_search_guide_semantic_config` (기본값 `guide-semantic-config`)
- `azure_search_video_semantic_config` (기본값 `video-semantic-config`)

**추가된 필드 1개 (Document Intelligence 확장 대비)**:

- `azure_docintel_model_id` (기본값 `prebuilt-layout`) — 팀 회의 후 Custom Neural 결정되면 값만 교체 가능

**제거된 필드 1개**:

- `azure_search_procedure_index` — 레거시 unified 패턴 삭제. `extra="ignore"` 덕에 기존 `.env`에 남아있어도 에러 없음.

#### `backend/app/azure_clients.py` 확장

**신설된 팩토리 함수 2개**:

- `get_search_client_guide()` — guide-index용
- `get_search_client_video()` — video-index용

**공통 로직 추출**:

- `_build_search_client(index_name)` 헬퍼로 3개 팩토리 공통 로직 격리

**하위 호환**:

- `get_search_client_procedure()` 는 유지하되 `get_search_client_guide()` 로 alias (레거시 safecontract_service 등 호출부 보호)
- 차후 커밋에서 모든 호출부가 guide로 교체되면 제거 예정

#### `backend/app/search_service.py` 신규 모듈 **(핵심 작업)**

설계 철학: **"Azure Search에 어떻게 쿼리 던지는가"를 서비스 레이어에서 격리**. chat / checklist / safecontract 세 서비스가 공통으로 쓰는 인프라 계층. 단일 책임 원칙.

**공개 함수 5개**:

1. `embed_query(text) -> list[float] | None`
   - text-embedding-3-small 단일 호출
   - 실패 시 None → 호출자는 semantic-only로 graceful fallback

2. `hybrid_search(client, query, top, semantic_config, embedding) -> list[dict]`
   - 단일 인덱스 semantic + vector 하이브리드
   - VectorizedQuery(k_nearest_neighbors=50) + semantic_configuration_name 동시 전달
   - embedding=None 이면 semantic-only로 자동 축소
   - top<=0 또는 client=None 이면 조기 return (방어)

3. `parallel_search(query, targets) -> dict[str, list[dict]]`
   - **범용 병렬 엔진**. targets dict로 임의의 인덱스 조합 받음
   - 예: `{"law": (client, 6, config), "guide": (client, 4, config)}`
   - 임베딩 1회 호출 후 모든 타겟에 재사용
   - ThreadPoolExecutor 병렬 실행

4. `parallel_search_3(query, top_law=6, top_guide=4, top_video=3)` — **챗봇용 wrapper**
   - 반환: `(law_hits, guide_hits, video_hits)` tuple
   - 기존 `_search_unified()` 시그니처와 동일 → 호출부 변경 불필요

5. `parallel_search_law_guide(query, top_law=3, top_guide=3)` — **체크리스트용 wrapper**
   - 반환: `(law_hits, guide_hits)` tuple
   - 체크리스트 citation 이 법정 기한·과태료 조문을 정확히 인용하려면 law 필수 (hallucination 방어)

**상수 설계**:

- `VECTOR_K_NEIGHBORS = 50`: 벡터 raw 후보 수. Azure 권장값.
- `PARALLEL_TIMEOUT_SEC = 30.0`: cold start 대응. 처음엔 5.0으로 설정했다가 초기 호출 시 4~5초대 latency로 timeout 발생 → 30초로 상향.
- `DEFAULT_TOP_LAW_CHAT = 6`, `DEFAULT_TOP_GUIDE_CHAT = 4`, `DEFAULT_TOP_VIDEO_CHAT = 3`: 챗봇 컨텍스트 배분 (법률 정보 비중 최대)
- `DEFAULT_TOP_LAW_CHECKLIST = 3`, `DEFAULT_TOP_GUIDE_CHECKLIST = 3`: 체크리스트는 쿼리 수가 많으므로 쿼리당 작게

#### `backend/app/chat_service.py` 리팩토링

**변경 2곳** (최소 diff):

1. Import 블록: `get_search_client_procedure` 제거, `from .search_service import parallel_search_3` 추가
2. `_search_unified()` 함수 내부를 `return parallel_search_3(query)` 한 줄로 교체

함수 이름 `_search_unified`는 유지 — 호출부 (`generate_chat_reply`) 의 `law_hits, proc_hits, yt_hits = _search_unified(query_joined)` 줄이 그대로 동작. 레거시 이름이지만 반환 시그니처 호환성 때문에 의도적 유지.

#### 스모크 테스트 결과

**1단계 — 설정 로드**:

```
ready: True
law: law-index
guide: guide-index
video: video-index
endpoint: https://iim-ai-search.search.windows.net
```

**2단계 — 3-index 병렬 쿼리** (`전입신고는 언제까지 해야 해요`):

- Run 1 (cold): 17.38초 — law=6 guide=4 video=3, 임베딩 on
- Run 2 (warm): 1.61초 — 동일 결과
- Top 1 law: "거주지의 이동" (주민등록법 제16조)
- Top 1 guide: "대항력 및 우선변제권 취득"
- Top 1 video: "국토교통부 - 전세 계약 전/중/후 유의사항"

**3단계 — 2-index 체크리스트 패턴** (`전입신고 방법`):

- law=3 guide=3
- Top 1 law: 주민등록법 시행령 제23조
- Top 1 guide: "전입신고하기"

**4단계 — FastAPI end-to-end** (Swagger UI `/chat`):

- mode: `"azure"` (fallback 아님)
- 답변에 "14일 이내" 정확 포함, 주민등록법 제16조 인용
- 과태료 5만원 언급 (법률 조문 기반)
- 영상 deep_link 타임스탬프 정확 (`08:56부터`, `&t=536s`)
- citations 9개 (law 3 + procedure 3 + youtube 3)

#### Expo Go 폰 E2E 검증

**설정**:

- 노트북 IP 확보 (ipconfig → IPv4 주소)
- uvicorn `--host 0.0.0.0` 으로 외부 접속 허용
- `frontend/movewise-app/lib/api.ts`의 `DEFAULT_API_URL` 을 임시로 노트북 IP로 변경
- 같은 Wi-Fi에서 폰 Expo Go로 QR 스캔

**결과**:

- 폰 → 노트북 FastAPI 호출 성공 (uvicorn 로그에 `192.168.45.239` 클라이언트 IP 찍힘)
- 챗봇 탭에서 질문 입력 → 답변 + citation 폰 화면 렌더링 확인
- Warm latency 3~4초 (실사용 체감)

**api.ts 변경사항은 커밋 안 함** — 로컬 테스트용. 확인 후 `git checkout`으로 원복.

#### /checklist hallucination 실증

세션 5에서 `/checklist` 를 샘플 데이터로 Swagger 호출 → **결과에서 명백한 hallucination 발견**:

**입력**: `has_car: false`, `children_school_level: "초등"` (자녀는 있으나 입력 모순)

**응답 items에 포함된 자동차 항목**:

```json
{
  "title": "자동차 주소지 변경등록",
  "description": "자동차 소유자는 이사 후 30일 이내에...",
  "citations": [
    {
      "law_name": "자동차관리법",
      "article": "제11조",
      "source_url": null,
      "article_text": null
    }
  ]
}
```

**문제점**:

1. `has_car: false` 인데 자동차 항목 생성됨. `build_queries_rule_based()` 는 `if req.has_car:` 가드가 있으므로 자동차 쿼리 자체가 생성 안 됐어야 함. `used_queries` 에도 자동차 관련 0개 — LLM이 상상으로 추가한 것.
2. 자동차관리법 제11조 = 가짜. 실제 주소 변경 근거는 **제6조 (변경등록)**, 기한은 **15일 이내** (30일 아님).
3. `source_url`, `article_text` null — 로컬 JSON enrichment 실패 → 애초에 존재하지 않는 조항이라 매칭 안 됨.

**전입신고 항목의 source_url 이상**:

```
https://www.law.go.kr/DRF/lawService.do?OC=msai09sa&...
```

`OC=msai09sa` = **팀 LAW_OC**. 내 `.env`는 `LAW_OC=ajourney` 인데 이 URL이 박혀있음 = `local_search.find_law_article()` 이 팀이 수집한 로컬 JSON에서 찾아 붙인 증거. 즉 Azure Search가 아닌 로컬 폴백으로 동작 중.

**원인 진단**:

1. `checklist_service.search_procedures()` 가 `moving-unified-index` 를 `iim-ai-search` 에 요청
2. 그 인덱스 없음 → 에러 로그 찍힘
3. `local_search.search()` 로 폴백 → 로컬 guide JSON만 키워드 매칭
4. LLM 이 받은 실제 context: guide 청크 몇 개뿐 (law 0건)
5. LLM 이 "이사"라는 도메인 맥락에서 자기 지식으로 자동차 조항 환각

**교훈**: 체크리스트도 **law-index 병렬 쿼리 필수**. 단순히 guide 검색 결과만으로는 citation 정확도 보장 안 됨. 이게 `parallel_search_law_guide()` wrapper를 만든 이유.

#### 세션 5 주요 결정

- **브랜치 리네임**: `experiment/schema-refactor` → `feat/3-index-rag-transition`. 이름이 작업 성격 반영.
- **search_service.py 신규 레이어**: 단일 책임 원칙. chat / checklist / safecontract 공통 검색 로직 격리. 중복 110줄 방지.
- **하이브리드 = semantic + vector 기본**: 팀 unified는 semantic only 패턴이었음. 내 버전은 벡터 하이브리드 — 발표 차별화 포인트.
- **ThreadPoolExecutor 채택**: asyncio 리팩토링 (FastAPI 핸들러·chat 함수 체인 전부 async화) 리스크 회피. 시간 제약 상 sync 구조 유지 + 3개 쿼리만 병렬화로 충분.
- **Azure App Service 배포 후순위**: 매니저 방침 "시연영상 제출만으로 평가". 배포 투자 시간을 기능 완성도로.
- **Custom Neural Document Intelligence 보류**: Studio 학습 완료 상태이나 safecontract_service 통합 = 큰 리팩토링 (`extract_text_from_pdf` → `extract_fields_from_pdf` 재작성 + `RegistryExtraction` 매핑 변경). 팀 회의에서 결정 후 진행 여부 판단.
- **체크리스트 law 병렬 필요성 실증**: hallucination 현상으로 "law 없이 guide만으론 citation 부정확" 증명. 내일 리팩토링 최우선.
- **`.env` 세팅**: 루트 `.env`에 내 `iim-*` 리소스 키 전체 주입. `backend/.env` (팀 키) 는 그대로 두되 config.py 가 루트만 읽으므로 참조되지 않음. 점검 결과 `load_dotenv` 호출 백엔드 코드 내 0건.

---

## 다음 세션 우선순위 (발표 4/26까지 6일)

### 🔴 필수

1. **`checklist_service.py` 리팩토링** ⭐ 최우선 (hallucination 해결)
   - `search_procedures()` → `parallel_search_law_guide()` 호출
   - 쿼리 루프: 각 쿼리마다 law 3 + guide 3 병렬, id 기반 dedupe
   - `structure_checklist_llm` 프롬프트에 law / guide 컨텍스트 분리 명시
   - 안티-hallucination 규칙 추가: "검색 결과에 없는 law 조항은 절대 citation으로 쓰지 말 것"
   - 검증: 재테스트 시 `has_car=false` 입력에 자동차 항목 나오지 않아야 함

2. **`safecontract_service._search_law_context` 전환** (간단, 20분)
   - `get_search_client_law()` + `hybrid_search()` 직접 호출
   - 기존 로직의 `source_type eq 'law'` 필터 제거

3. **골든 쿼리 30건 비교 평가**
   - 팀 unified (Render URL 직접 호출) vs 내 3-index 결과 비교
   - 간단 지표: top-k recall, citation 정확도 (수동 검토)
   - 발표 자료의 "숫자" 확보

4. **시연영상 촬영** (Azure App Service 배포 대체)
   - 로컬 FastAPI + Expo Go 폰 화면 녹화
   - 시나리오: 챗봇 질문 → citation 표시 → 영상 deep_link 클릭 → YouTube 특정 구간 재생
   - 체크리스트 생성 → law 인용 정확성
   - SafeContract PDF 업로드 → 위험 분석 (전환 후)

5. **발표 자료 준비**
   - 아키텍처 다이어그램 (Blob → Indexer × 3 → Index × 3 → FastAPI → Expo)
   - 핵심 숫자 (2,122 청크, warm latency ~3-4초, hallucination 감소)
   - 팀 unified vs 내 3-index 비교 차트

### 🟡 선택 (시간 되면)

6. **Custom Neural Document Intelligence 통합** (팀 회의 후 결정)
   - Studio에서 학습 완료 상태
   - 통합 시: `extract_text_from_pdf` → `extract_fields_from_pdf` 재작성
   - `RegistryExtraction` Pydantic 모델에 매핑
   - Neural은 `result.documents[0].fields` 에서 구조화 dict 반환 (prebuilt-layout처럼 `result.content` 평문 아님)
   - 리스크: safecontract 엔드포인트 전체 리팩토링, 발표 데모 깨질 가능성
   - 대안: 학습 완료 사실만 슬라이드에 언급, Phase 2에서 통합

7. **Azure App Service 배포** (시연영상이 대체하므로 후순위)
   - MS AI School 평가 포인트 추가 확보용
   - 주말 여유 있으면 2~3시간 투자

8. **`curate_chunks.py` 정비 + 재큐레이션**
   - Mac 하드코딩 경로 수정
   - 출력: `easylaw_chunks_curated.jsonl`
   - Guide 인덱스 재인덱싱 여부는 품질 차이 측정 후 결정

9. **`ingest_youtube.py` Mac 경로 확인** (video-index 인덱싱 성공으로 1차 검증됨)

10. **Azure 리소스 정의 JSON을 repo에 커밋**
    - `backend/schemas/law-index.json`, `guide-index.json`, `video-index.json`
    - Phase 2에서 재현성 확보용

### Phase 2 (발표 후)

- 폴더 구조 리팩토링 (`procedures/` → `guides/` 등)
- `related_procedures` vector similarity로 채우기
- 개인화 DB 분리 (`applicable_to` 등을 user profile로)
- SETUP.md의 `msai09sa` 노출 팀에 PR
- keywords 추출 A/B 실험 (whitelist vs blacklist+auto-stopwords)
- 통계 기반 불용어 사전 구축 (상위 200개 수동 검토)
- Guide↔Law 크로스 링크 (`related_laws` → law-index lookup)
- `get_search_client_procedure()` alias 완전 제거 (guide로 통일)
- checklist 리팩토링 시 발견한 로직 이슈 정리

---

## 미해결 이슈

### 환경

- `.env` vs `backend/.env` 중복 — 세션 5에서 확인: `config.py`는 루트 `.env`만 참조. `backend/.env`는 팀 키 보존용으로 두고 기능상 영향 없음. 내 실험 환경은 루트 `.env` 기반.
- Python 3.13에서 잘 동작하나 3.12 호환성 검증 안 됨

### 데이터

- `raw/youtube_transcripts/` 12개 파일 품질 미검증 (video-index 인덱싱 성공으로 최소 스키마는 OK)
- `mapping/` 30+ 파일은 인덱스에 안 올리지만, 스키마 정리 필요 여부 미확인
- `curate_chunks.py` 아직 정비 안 됨 (현재 guide-index는 큐레이션 전 원본 340 청크 사용)

### 코드

- `checklist_service.py`, `safecontract_service.py` 3-index 미전환 → 현재 local fallback 모드로 동작 + hallucination 위험
- `get_search_client_procedure()` 레거시 alias 남음 → safecontract 전환 후 제거
- `_search_unified` 함수명이 이제 3-index 호출이지만 이름은 unified 유지 (호출부 호환성)

### 문서 동기화

- `SCHEMA_DECISION.md`의 필드 이름 `last_updated` → 실제 JSONL·Azure 스키마엔 `fetched_at`만 존재 (정정 필요)
- Azure 인덱스 이름 `iim-law-index` (SCHEMA_DECISION 문서) vs 실제 `law-index` (Portal에서 생성한 이름) — 문서 업데이트 필요
- `backend/schemas/` 디렉토리에 인덱스 정의 JSON 미커밋 (Portal에서만 존재)
- DEVLOG의 브랜치 구조 다이어그램에 `experiment/schema-refactor` → `feat/3-index-rag-transition` 업데이트 필요

### 팀 관계

- SETUP.md에 `msai09sa` 팀 ID 노출
- 팀의 현재 unified index 쿼리 품질 베이스라인 기록 필요 (비교 기준)
- Custom Neural 통합 방향성 회의 결정 필요

---

## 환경 체크리스트

### 현재 세션 종료 시점 (2026-04-20 세션 5 종료, 새벽 03:30)

- [x] 세션 3 작업 커밋됨 (94a40a8)
- [x] origin 에 push 완료 (세션 5까지)
- [x] Azure 3-index 파이프라인 구축 완료 (law-index, guide-index, video-index)
- [x] 인덱싱 완료: 1,635 + 340 + 147 = 2,122 docs
- [x] Search Explorer 하이브리드 검색 검증 (세션 4)
- [x] 세션 4 파일 rename 커밋 완료 (eae077c)
- [x] 세션 4 fix 커밋 완료 (80ec60a)
- [x] 브랜치 이름 변경: `experiment/schema-refactor` → `feat/3-index-rag-transition`
- [x] `config.py` / `azure_clients.py` 3-index 확장 완료
- [x] `search_service.py` 신규 모듈 작성 완료 (5개 공개 함수)
- [x] `chat_service.py` 리팩토링 완료 (`_search_unified` → `parallel_search_3`)
- [x] `/chat` 엔드포인트 로컬 스모크 통과 (Swagger UI)
- [x] Expo Go 폰 E2E 검증 완료
- [x] `api.ts` 임시 변경 원복 확인
- [x] 두 커밋 (07fe9bd, 7e125e0) origin push 완료
- [ ] `/checklist` 엔드포인트 3-index 전환 ← 다음 세션
- [ ] `/safecontract` 엔드포인트 3-index 전환 ← 다음 세션
- [ ] Golden query 30건 평가 ← 다음 세션 이후
- [ ] 시연영상 촬영 ← 발표 직전

### 다음 세션 시작 시

- [ ] `feat/3-index-rag-transition` 브랜치에서 시작
- [ ] `git pull origin feat/3-index-rag-transition` (혹시 원격 변경 있나)
- [ ] SESSION_LOG.md, DEVLOG.md 재확인
- [ ] 팀원에게 세션 5 결과 브리핑 (약속했으면)
- [ ] 팀 회의에서 Custom Neural 통합 방향 결정 확인
- [ ] `checklist_service.py` 리팩토링 diff 적용 → 로컬 검증 → 커밋
