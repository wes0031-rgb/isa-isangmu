# SESSION_LOG

세션별 진행 기록. 매 세션 끝에 업데이트.

---

## 최신 상태 (2026-04-19)

### 브랜치

- 현재: `experiment/schema-refactor`
- Fork: `liminal-cipher/isa-isangmu`
- Upstream: `wes0031-rgb/isa-isangmu`
- 최신 커밋: `94a40a8 feat(ingest): add keywords extraction + chunk_easylaw cross-platform path`

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
- 1,635 청크 생성 → `index_a_chunks.jsonl`

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
- 재청킹 결과: **340 청크, 평균 580자** (`index_b_chunks.jsonl`)
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

- **Index A (Law)**: 1,635 청크 (회귀 0)
  - 민법 1,094 / 부동산등기법 118 / 공동주택관리법 104 / 동물보호법 102 / 주민등록법 시행령 86 / 주민등록법 55 / 주택임대차보호법 41 / 주택임대차보호법 시행령 35
  - keywords: **평균 3.9개/청크, 1,635/1,635 커버리지 100%**
  - 육안 샘플 검증 OK — "관하여", "관한" 등 상투어 0건
- **Index B (Guide)**: 340 청크, 평균 580자

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

## 진행 중

- 없음 (모든 작업 커밋됨)

---

## 다음 세션 우선순위 (6일 남음, 최종 발표 4/26)

### 필수

1. **`curate_chunks.py` 정비 + 재큐레이션**
   - Mac 하드코딩 경로 수정
   - EXCLUDE_DOCS 재검토 (666/629 out-of-scope 목록)
   - 출력: 새 `index_b_chunks_curated.jsonl`

2. **`ingest_youtube.py` 확인**
   - Mac 하드코딩 경로 체크
   - 필드 구성 확인 (18 필드 전부 생성하는지)
   - `index_c_youtube_chunks.jsonl` 현재 품질 검증

3. **3-index 스키마 JSON 작성**
   - `schemas/iim-law-index.json` — Azure 인덱스 스키마 (12 필드)
   - `schemas/iim-guide-index.json` — Azure 인덱스 스키마 (15 필드)
   - `schemas/iim-video-index.json` — Azure 인덱스 스키마 (16 필드)

4. **Azure Indexer 파이프라인 구성** ⭐ 최대 블로커
   - Blob Storage 컨테이너 생성 (JSONL 업로드)
   - Datasource 3개 생성
   - Skillset 3개 (embedding skill)
   - Indexer 3개 + `fieldMappings`
     - `doc_title` → `title` (guide)
     - `video_title` → `title` (video)

5. **백엔드 코드 3-index 쿼리로 전환**
   - `chat_service.py`, `checklist_service.py` 등 기존 unified 인덱스 참조 교체
   - `source_type` 필터 대신 인덱스 이름으로 분기

6. **Azure App Service 배포**
   - 퍼블릭 URL 확보
   - Expo 앱에서 배포 URL 호출 확인

7. **검증 쿼리 + 발표 자료**
   - Golden query 30건 실행
   - 팀 unified vs 내 3-index 결과 비교
   - 아키텍처 다이어그램, 성능 지표

### 선택 (시간 되면)

8. `ingest_services_v2.py` 상태 파악 (내용 확인 후 rename/삭제 결정)
9. `.env` vs `backend/.env` 이원화 정리

### Phase 2 (발표 후)

- 폴더 구조 리팩토링 (`procedures/` → `guides/` 등)
- `related_procedures` vector similarity로 채우기
- 개인화 DB 분리 (`applicable_to` 등을 user profile로)
- SETUP.md의 `msai09sa` 노출 팀에 PR
- keywords 추출 A/B 실험 (whitelist vs blacklist+auto-stopwords)
- 통계 기반 불용어 사전 구축 (상위 200개 수동 검토)

---

## 미해결 이슈

### 환경

- `.env` vs `backend/.env` 중복 — config.py가 어디 보는지 확인 후 통합
- Python 3.13에서 잘 동작하나 3.12 호환성 검증 안 됨

### 데이터

- `raw/youtube_transcripts/` 12개 파일 품질 미검증
- `mapping/` 30+ 파일은 인덱스에 안 올리지만, 스키마 정리 필요 여부 미확인

### 팀 관계

- SETUP.md에 `msai09sa` 팀 ID 노출
- 팀의 현재 unified index 쿼리 품질 베이스라인 기록 필요 (비교 기준)

---

## 환경 체크리스트

### 현재 세션 종료 시점 (2026-04-19 세션 3)

- [x] 모든 작업 커밋됨 (94a40a8)
- [x] origin/experiment/schema-refactor에 push 완료
- [ ] Fork main에 merge (Project sync 위해) ← 다음 세션 시작 전

### 다음 세션 시작 시

- [ ] `experiment/schema-refactor` 브랜치에서 시작
- [ ] `git pull origin experiment/schema-refactor` (원격 최신 반영)
- [ ] DEVLOG.md, SESSION_LOG.md 재확인
