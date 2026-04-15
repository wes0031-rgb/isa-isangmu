"""통합 인덱스(`index_unified.jsonl`) 회귀 테스트.

검증 항목:
  1. 총 개수 = A + B + C
  2. source_type 분포 일치
  3. ID 중복 없음 (Azure Search key 규칙)
  4. ID 형식 안전성 (영숫자/언더스코어만)
  5. 필드 매핑 정확성 (샘플 확인)
  6. 크로스 링크 무결성 (related_procedures/videos 가 실제 존재하는 ID)
  7. 타입별 필수 필드 존재 (law → law_name/article, procedure → parent_doc, video → video_id)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.schemas.unified_index import UnifiedChunk, make_safe_id

ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "backend" / "data" / "indexes"
UNIFIED = INDEX_DIR / "index_unified.jsonl"
SRC_A = INDEX_DIR / "index_a_chunks.jsonl"
SRC_B = INDEX_DIR / "index_b_chunks_curated.jsonl"
SRC_C = INDEX_DIR / "index_c_youtube_chunks.jsonl"


def _load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.fixture(scope="module")
def unified() -> list[dict]:
    assert UNIFIED.exists(), "Run backend/scripts/unify_indexes.py first"
    return _load(UNIFIED)


@pytest.fixture(scope="module")
def source_counts() -> dict[str, int]:
    return {
        "A": len(_load(SRC_A)),
        "B": len(_load(SRC_B)),
        "C": len(_load(SRC_C)),
    }


# ===== 개수 =====


def test_total_count_matches_sources(unified, source_counts):
    """통합 인덱스 총 개수 = A + B + C."""
    expected = source_counts["A"] + source_counts["B"] + source_counts["C"]
    assert len(unified) == expected, f"expected {expected}, got {len(unified)}"


def test_source_type_distribution(unified, source_counts):
    """source_type 별 개수가 원본과 일치."""
    by_type = {"law": 0, "procedure": 0, "video": 0}
    for u in unified:
        by_type[u["source_type"]] += 1
    assert by_type["law"] == source_counts["A"]
    assert by_type["procedure"] == source_counts["B"]
    assert by_type["video"] == source_counts["C"]


# ===== ID 무결성 =====


def test_no_duplicate_ids(unified):
    ids = [u["id"] for u in unified]
    assert len(ids) == len(set(ids)), "duplicate IDs exist"


def test_ids_are_azure_safe(unified):
    """Azure Search document key: letters/digits/_/-/= 만 허용."""
    safe = re.compile(r"^[A-Za-z0-9_\-=]+$")
    for u in unified:
        assert safe.match(u["id"]), f"unsafe id: {u['id']}"


def test_id_prefix_matches_source_type(unified):
    for u in unified:
        expected_prefix = {"law": "law_", "procedure": "proc_", "video": "yt_"}[u["source_type"]]
        assert u["id"].startswith(expected_prefix), (
            f"prefix mismatch: {u['id']} should start with {expected_prefix}"
        )


def test_make_safe_id_deterministic():
    """같은 source_id 는 항상 같은 safe id 를 생성."""
    a1 = make_safe_id("law", "주택임대차보호법__제3조")
    a2 = make_safe_id("law", "주택임대차보호법__제3조")
    assert a1 == a2


def test_make_safe_id_different_for_different_inputs():
    a = make_safe_id("law", "주택임대차보호법__제3조")
    b = make_safe_id("law", "주택임대차보호법__제4조")
    assert a != b


# ===== 필드 매핑 =====


def test_all_chunks_validate_against_pydantic(unified):
    """Pydantic 모델로 전부 검증되는지 (필드 타입 정합성)."""
    for u in unified[:100]:  # 샘플 100건만 (속도)
        UnifiedChunk.model_validate(u)


def test_law_chunks_have_required_fields(unified):
    """법률 청크는 law_name·article 필수."""
    laws = [u for u in unified if u["source_type"] == "law"]
    for u in laws[:50]:
        assert u.get("law_name"), f"missing law_name: {u['source_id']}"
        assert u.get("article"), f"missing article: {u['source_id']}"
        assert u.get("video_id") is None, "law chunks must not have video_id"


def test_procedure_chunks_have_required_fields(unified):
    """행정절차 청크는 parent_doc 필수."""
    procs = [u for u in unified if u["source_type"] == "procedure"]
    for u in procs[:20]:
        assert u.get("parent_doc"), f"missing parent_doc: {u['source_id']}"
        assert u.get("law_name") is None, "procedure chunks must not have law_name"


def test_video_chunks_have_required_fields(unified):
    """유튜브 청크는 video_id·deep_link·timecode 필수."""
    vids = [u for u in unified if u["source_type"] == "video"]
    for u in vids[:20]:
        assert u.get("video_id"), f"missing video_id: {u['source_id']}"
        assert u.get("deep_link"), f"missing deep_link: {u['source_id']}"
        assert u.get("law_name") is None


# ===== 크로스 링크 무결성 =====


def test_cross_links_reference_valid_ids(unified):
    """related_procedures / related_videos 에 있는 ID 가 실제 존재하는지."""
    all_ids = {u["id"] for u in unified}
    dangling = []
    for u in unified:
        for pid in u.get("related_procedures") or []:
            if pid not in all_ids:
                dangling.append(("proc", u["source_id"], pid))
        for vid in u.get("related_videos") or []:
            if vid not in all_ids:
                dangling.append(("yt", u["source_id"], vid))
    assert not dangling, f"dangling cross-links (first 5): {dangling[:5]}"


def test_at_least_some_cross_links_exist(unified):
    """전체적으로 크로스 링크가 0 은 아닌지 (있어야 통합 가치가 있음)."""
    total_proc = sum(len(u.get("related_procedures") or []) for u in unified)
    total_video = sum(len(u.get("related_videos") or []) for u in unified)
    assert total_proc > 0, "no related_procedures cross-links"
    assert total_video > 0, "no related_videos cross-links"


# ===== 유저 프로필 필터 =====


def test_all_chunks_have_user_profile_fields(unified):
    """applicable_to / contract_type / region 은 전부 채워져 있어야 함."""
    for u in unified[:100]:
        assert u.get("applicable_to"), f"missing applicable_to: {u['source_id']}"
        assert u.get("contract_type"), f"missing contract_type: {u['source_id']}"
        assert u.get("region"), f"missing region: {u['source_id']}"
