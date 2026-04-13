"""local_search — BM25-lite 키워드 스코어링과 법률 인덱스 조회."""
from backend.app.local_search import (
    find_law_article,
    get_article_text,
    load_chunks,
    load_laws,
    score_chunk,
    search,
    search_laws,
)


def test_load_chunks_non_empty():
    """Index B 큐레이션 청크가 로드되어야 함."""
    chunks = load_chunks()
    assert len(chunks) >= 100


def test_load_laws_non_empty():
    """Index A 법률 청크가 로드되어야 함."""
    laws = load_laws()
    assert len(laws) >= 500


def test_score_chunk_matches_tokens():
    """쿼리 토큰이 chunk haystack에 등장하면 양수 스코어."""
    fake = {
        "content": "전입신고는 이사한 날부터 14일 이내에 해야 합니다",
        "category": ["전입신고"],
    }
    s = score_chunk(fake, ["전입신고"])
    assert s > 0


def test_search_returns_results_for_common_query():
    """일반 쿼리 검색 시 결과가 나와야 함."""
    results = search(["전입신고"], top_k_per_query=3)
    assert len(results) > 0
    # 모든 결과에 _local_score 필드 존재
    for r in results:
        assert "_local_score" in r


def test_search_empty_query_returns_nothing():
    results = search([""], top_k_per_query=3)
    assert results == []


def test_find_law_article_exact_match():
    """주민등록법 제16조는 Index A 에 반드시 존재."""
    found = find_law_article("주민등록법", "제16조")
    assert found is not None
    assert "전입" in (found.get("content") or "")


def test_find_law_article_whitespace_tolerant():
    """공백 차이 무시 — '주택임대차보호법 시행령' vs '주택임대차보호법시행령'."""
    with_space = find_law_article("주택임대차보호법 시행령", "제1조")
    without_space = find_law_article("주택임대차보호법시행령", "제1조")
    # 둘 중 하나라도 있으면 됨 — 둘 다 같은 결과 반환
    if with_space or without_space:
        assert with_space == without_space


def test_find_law_article_not_found():
    """존재하지 않는 법령은 None."""
    assert find_law_article("가짜법", "제999조") is None


def test_get_article_text_truncates():
    """긴 조문은 max_chars 로 잘림."""
    # 주민등록법 제16조 — 길지 않을 수 있으니 짧은 max_chars 로 테스트
    text = get_article_text("주민등록법", "제16조", max_chars=50)
    if text:
        assert len(text) <= 51  # "…" 1자 포함


def test_search_laws_returns_law_chunks():
    """법률 키워드 검색 → law_name 포함된 chunk 반환."""
    results = search_laws(["임대차 대항력"], top_k_per_query=3)
    assert len(results) > 0
    # 주택임대차보호법 류가 상위에 있어야 함
    assert any("임대차" in (r.get("law_name") or "") for r in results)
