# Backend Tests

pytest 기반 단위·통합 테스트.

## 실행

```bash
cd backend

# 전체
pytest

# 조용히 (실패만 출력)
pytest -q

# 특정 파일
pytest tests/test_safecontract_service.py

# 특정 이름 매칭 (regex)
pytest -k "compute_ratios"

# verbose + 실패 위치 상세
pytest -v --tb=short
```

## 테스트 파일

| 파일 | 범위 |
|------|------|
| `test_checklist_service.py` | `/checklist` 파이프라인 — 쿼리 생성·구조화·region enrich |
| `test_safecontract_service.py` | `_compute_ratios` / `_parse_korean_amount` / `_parse_region_from_address` / risk 판정 |
| `test_date_utils.py` | `compute_start_date` / `next_business_day` / 공휴일 반영 |
| `test_local_search.py` | Azure 미연결 시 로컬 키워드 검색 폴백 |
| `test_ingest_laws_filter.py` | 법령 수집 필터링 로직 |
| `test_unified_index.py` | 통합 인덱스 스키마·source_type 필터 |
| `conftest.py` | 공용 fixture (샘플 request·extraction 등) |

## 원칙

- **Azure 호출 X** — 테스트는 Azure 키 없이 돌려도 OK
- 외부 API 는 `monkeypatch` 로 mock
- 실제 데이터 파일은 `tests/fixtures/` 에 미니 샘플 (대용량 금지)
- 새 기능 추가 시 최소 happy path + 에러 케이스 1개씩
