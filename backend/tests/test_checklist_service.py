"""checklist_service — fallback 경로의 계약별·조건별 분기 동작."""
from datetime import date

from backend.app.checklist_service import generate_checklist
from backend.app.models import ChecklistRequest


def _req(**overrides) -> ChecklistRequest:
    base = {
        "household": "자취",
        "contract": "월세",
        "region": "서울특별시 강남구",
        "move_date": date(2026, 5, 1),
        "has_pet": False,
        "has_car": False,
        "has_children": False,
    }
    base.update(overrides)
    return ChecklistRequest(**base)


def _categories(resp) -> set[str]:
    return {it.category for it in resp.items}


def test_monthly_rent_has_lease_items():
    """월세는 확정일자/대항력 포함."""
    resp = generate_checklist(_req(contract="월세"))
    cats = _categories(resp)
    assert any("확정일자" in c or "임차권" in c for c in cats)
    assert any("대항력" in c for c in cats)


def test_owner_excludes_lease_items():
    """자가는 확정일자/대항력 제외."""
    resp = generate_checklist(_req(contract="자가"))
    cats = _categories(resp)
    assert not any("확정일자" in c for c in cats)
    assert not any("대항력" in c for c in cats)


def test_pet_adds_pet_category():
    """반려동물 보유 → 동물 주소변경 항목 포함."""
    resp = generate_checklist(_req(has_pet=True))
    cats = _categories(resp)
    assert any("반려동물" in c or "동물" in c for c in cats)


def test_pet_absent_excludes_pet_category():
    resp = generate_checklist(_req(has_pet=False))
    cats = _categories(resp)
    assert not any("반려동물" in c for c in cats)


def test_car_adds_car_category():
    resp = generate_checklist(_req(has_car=True))
    cats = _categories(resp)
    assert any("자동차" in c for c in cats)


def test_foreigner_adds_foreigner_category():
    resp = generate_checklist(_req(is_foreigner=True))
    cats = _categories(resp)
    assert any("외국인" in c for c in cats)


def test_children_adds_school_category():
    resp = generate_checklist(
        _req(has_children=True, children_school_level="초등"),
    )
    cats = _categories(resp)
    assert any("전학" in c for c in cats)


def test_multi_contracts_includes_all():
    """contracts=[전세, 자가] 지정 시 전세 기반 lease 항목이 포함되어야."""
    resp = generate_checklist(
        _req(contract="전세", contracts=["전세", "자가"]),
    )
    cats = _categories(resp)
    assert any("확정일자" in c or "임차권" in c for c in cats)


def test_default_items_present():
    """모든 응답에 기본 절차(전입신고, 전기, 우편물)는 포함."""
    resp = generate_checklist(_req())
    cats = _categories(resp)
    assert any("전입신고" in c for c in cats)
    assert any("전기" in c for c in cats)
    assert any("우편" in c for c in cats)


def test_citations_have_article_text_when_in_index_a():
    """Index A 통합이 적용되어 실제 법조문 텍스트가 붙어야 함."""
    resp = generate_checklist(_req(contract="월세"))
    has_any_text = False
    for item in resp.items:
        for cite in item.citations:
            if cite.article_text:
                has_any_text = True
                break
        if has_any_text:
            break
    assert has_any_text, "No citation had article_text — Index A enrichment not applied"


def test_sorted_by_d_day_offset():
    """결과는 d_day_offset 오름차순 정렬."""
    resp = generate_checklist(_req(has_pet=True, has_car=True))
    offsets = [it.d_day_offset for it in resp.items]
    assert offsets == sorted(offsets)


def test_items_have_start_date():
    """모든 항목에 start_date 존재."""
    resp = generate_checklist(_req())
    for item in resp.items:
        assert item.start_date is not None


def test_concerns_trigger_additional_items():
    """특이사항 키워드가 추가 항목을 트리거."""
    resp = generate_checklist(
        _req(special_concerns=["갱신요구권"]),
    )
    cats = _categories(resp)
    assert any("갱신" in c for c in cats)
