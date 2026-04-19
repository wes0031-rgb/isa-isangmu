# SESSION_LOG

세션별 진행 기록. 매 세션 끝에 업데이트.

---

## 최신 상태 (2026-04-19)

### 브랜치

- 현재: `experiment/schema-refactor`
- Fork: `liminal-cipher/isa-isangmu`
- Upstream: `wes0031-rgb/isa-isangmu`
- 최신 커밋: `a60332e docs: refresh _source_metadata via annotate_sources.py`

### 브랜치 커밋 히스토리

```
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

**⚠️ 스크립트에 남은 작업**:

- `keywords` 자동 추출 로직 추가 (다음 세션)

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

## 진행 중

- 없음 (모든 작업 커밋됨)

---

## 다음 세션 우선순위

### 필수 (중간 발표 4/26 전)

1. **`chunk_easylaw.py` 정비 + 재청킹**
   - Mac 하드코딩 경로 수정
   - easylaw 재수집 데이터 기반 재청킹
   - 출력: 새 `index_b_chunks.jsonl`

2. **`curate_chunks.py` 정비 + 재큐레이션**
   - Mac 하드코딩 경로 수정
   - EXCLUDE_DOCS 재검토 (666/629 out-of-scope 목록)
   - 출력: 새 `index_b_chunks_curated.jsonl`

3. **`ingest_laws.py` 보강**
   - `keywords` 자동 추출 로직 추가 (한국어 키워드 extraction)
   - 법 조문에서 핵심어 뽑아 필드에 주입

4. **`ingest_youtube.py` 확인**
   - Mac 하드코딩 경로 체크
   - 필드 구성 확인 (18 필드 전부 생성하는지)
   - `index_c_youtube_chunks.jsonl` 현재 품질 검증

5. **3-index 스키마 JSON 작성**
   - `schemas/iim-law-index.json` — Azure 인덱스 스키마 (12 필드, last_updated 제외)
   - `schemas/iim-guide-index.json` — Azure 인덱스 스키마 (15 필드, 🟢 3개 제외)
   - `schemas/iim-video-index.json` — Azure 인덱스 스키마 (16 필드, 🟢 2개 제외)

6. **Azure Indexer 파이프라인 구성**
   - Blob Storage 컨테이너 생성 (JSONL 업로드)
   - Datasource 3개 생성
   - Skillset 3개 (embedding skill)
   - Indexer 3개 + `fieldMappings` (이름 변경 처리)
     - `doc_title` → `title` (guide)
     - `video_title` → `title` (video)

7. **검증 쿼리**
   - Golden query 30건 실행
   - 팀 unified vs 내 3-index 결과 비교
   - 성능 지표 기록

### 선택 (시간 되면)

8. `ingest_services_v2.py` 상태 파악 (내용 확인 후 rename/삭제 결정)
9. `.env` vs `backend/.env` 이원화 정리

### Phase 2 (중간 발표 후)

- 폴더 구조 리팩토링 (`procedures/` → `guides/` 등)
- `related_procedures` vector similarity로 채우기
- 개인화 DB 분리 (`applicable_to` 등을 user profile로)
- SETUP.md의 `msai09sa` 노출 팀에 PR

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

### 현재 세션 종료 시점

- [x] 모든 작업 커밋됨
- [x] origin/experiment/schema-refactor에 push 완료
- [ ] Fork main에 merge (Project sync 위해)
- [ ] Claude Project sync 완료

### 다음 세션 시작 시

- [ ] `experiment/schema-refactor` 브랜치에서 시작
- [ ] `git pull origin experiment/schema-refactor` (원격 최신 반영)
- [ ] DEVLOG.md, SESSION_LOG.md 재확인

---

## 커밋 히스토리 요약

```
a60332e  2026-04-19  docs: refresh _source_metadata
33a31c8  2026-04-19  refactor: improve easylaw scraper + regenerate corpus
21d830e  2026-04-18  data: regenerate law corpus with ASCII-safe schema
```

이번 세션에 추가될 커밋:

```
(다음)   2026-04-19  docs: add DEVLOG, SESSION_LOG, SCHEMA_DECISION
```
