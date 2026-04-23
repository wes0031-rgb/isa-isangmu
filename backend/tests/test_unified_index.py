"""통합 인덱스(`index_unified.jsonl`) 회귀 테스트.

검증 항목:
  1. 총 개수 = A + B (영상 인덱스 C 는 2026-04-23 저작권 우려로 제거)
  2. source_type 분포 일치
  3. ID 중복 없음 (Azure Search key 규칙)
  4. ID 형식 안전성 (영숫자/언더스코어만)
  5. 필드 매핑 정확성 (샘플 확인)
  6. 크로스 링크 무결성 (related_procedures 가 실제 존재하는 ID)
  7. 타입별 필수 필드 존재 (law → law_name/article, procedure → parent_doc)
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
# 3-index 전환 후 파일명 변경됨 — 호환 위해 둘 다 후보로 두고 첫 번째 존재하는 것 사용
SRC_A = next(
    p for p in (INDEX_DIR / "law_chunks.jsonl", INDEX_DIR / "index_a_chunks.jsonl") if p.exists()
)
SRC_B = INDEX_DIR / "index_b_chunks_curated.jsonl"


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
    }


# ===== 개수 =====


def test_total_count_matches_sources(unified, source_counts):
    """통합 인덱스 총 개수 = A + B."""
    expected = source_counts["A"] + source_counts["B"]
    assert len(unified) == expected, f"expected {expected}, got {len(unified)}"


def test_source_type_distribution(unified, source_counts):
    """source_type 별 개수가 원본과 일치 (video 제거됨)."""
    by_type = {"law": 0, "procedure": 0}
    for u in unified:
        st = u["source_type"]
        assert st in by_type, f"unexpected source_type: {st!r}"
        by_type[st] += 1
    assert by_type["law"] == source_counts["A"]
    assert by_type["procedure"] == source_counts["B"]


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
        expected_prefix = {"law": "law_", "procedure": "proc_"}[u["source_type"]]
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


def test_procedure_chunks_have_required_fields(unified):
    """행정절차 청크는 parent_doc 필수."""
    procs = [u for u in unified if u["source_type"] == "procedure"]
    for u in procs[:20]:
        assert u.get("parent_doc"), f"missing parent_doc: {u['source_id']}"
        assert u.get("law_name") is None, "procedure chunks must not have law_name"


def test_no_video_chunks_remain(unified):
    """영상 인덱스 제거 후 video source_type 청크가 남아있지 않은지."""
    vids = [u for u in unified if u["source_type"] == "video"]
    assert not vids, f"{len(vids)} video chunks should have been removed"


# ===== 크로스 링크 무결성 =====


def test_cross_links_reference_valid_ids(unified):
    """related_procedures 에 있는 ID 가 실제 존재하는지 (related_videos 는 dead 링크
    가능 — 영상 제거됨, 검사에서 제외)."""
    all_ids = {u["id"] for u in unified}
    dangling = []
    for u in unified:
        for pid in u.get("related_procedures") or []:
            if pid not in all_ids:
                dangling.append(("proc", u["source_id"], pid))
    assert not dangling, f"dangling cross-links (first 5): {dangling[:5]}"


# ===== 유저 프로필 필터 =====


def test_all_chunks_have_user_profile_fields(unified):
    """applicable_to / contract_type / region 은 전부 채워져 있어야 함."""
    for u in unified[:100]:
        assert u.get("applicable_to"), f"missing applicable_to: {u['source_id']}"
        assert u.get("contract_type"), f"missing contract_type: {u['source_id']}"
        assert u.get("region"), f"missing region: {u['source_id']}"
