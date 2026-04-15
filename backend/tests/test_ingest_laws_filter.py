"""ingest_laws — RAG 품질 필터 회귀 테스트.

Index A (법률 청크) 생성 시 제외해야 하는 유형:
  1) 폐지된 조문 ("제N조 삭제 <date>", "제N조의M 삭제 <date>")
  2) 장·절·관·편 헤더 ("제1장 총칙", "제2절 ...")
  3) 40자 미만의 의미 없는 stub
"""
import sys
from pathlib import Path

# backend/scripts 경로 추가 (ingest_laws 는 module 아닌 script 로 작성됨)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ingest_laws import should_skip_article, is_deleted_article  # noqa: E402


# ===== 폐지 조문 =====


def test_skip_basic_deleted_article():
    assert should_skip_article("제5조 삭제 <1989.12.30>")


def test_skip_deleted_with_subarticle():
    """제N조의M 삭제 형태도 필터링 (이전 regex 에서 놓치던 케이스)."""
    assert should_skip_article("제36조의2 삭제 <2020.6.9>")


def test_skip_deleted_various_dates():
    assert should_skip_article("제112조 삭제 <2017.10.13>")
    assert should_skip_article("제52조 삭제 <2009.8.13>")


# ===== 구조 헤더 =====


def test_skip_chapter_header():
    assert should_skip_article("제1장 총칙")
    assert should_skip_article("제2장 동물복지종합계획의 수립 등")


def test_skip_section_header():
    assert should_skip_article("제1절 동물의 보호 등")
    assert should_skip_article("제3절 반려동물행동지도사")


def test_skip_pyeon_header():
    assert should_skip_article("제1편 민법총칙")


# ===== Stub (너무 짧음) =====


def test_skip_stub_article_number_only():
    """'제2조의2' 처럼 번호만 있는 stub (5자)."""
    assert should_skip_article("제2조의2")


def test_skip_empty_content():
    assert should_skip_article("")
    assert should_skip_article("   \n   ")


def test_skip_under_40_chars():
    """40자 미만은 의미 없는 토막으로 간주."""
    assert should_skip_article("정의: 이 법에서 사용하는 용어는")  # 21자


# ===== 정상 조문은 통과 =====


def test_keep_normal_article_with_paragraphs():
    content = (
        "제3조(대항력 등) ① 임대차는 그 등기가 없는 경우에도 임차인이 "
        "주택의 인도와 주민등록을 마친 때에는 그 다음 날부터 제3자에 대하여 "
        "효력이 생긴다."
    )
    assert not should_skip_article(content)


def test_keep_short_but_valid_article():
    """40자 이상이면 정의 조문 같은 짧은 것도 통과."""
    content = "제1조(목적) 이 법은 주거용 건물의 임대차에 관하여 「민법」의 특례를 규정함을 목적으로 한다."
    assert len(content) >= 40
    assert not should_skip_article(content)


def test_keep_article_mentioning_삭제_in_body():
    """본문에 '삭제' 단어가 있어도 폐지 조문 패턴이 아니면 유지 (false positive 방지)."""
    content = "제29조(열람 또는 등ㆍ초본의 교부) 주민등록표를 열람하거나 삭제 신청을 하려는 자는 수수료를 내고 신청해야 한다."
    assert not should_skip_article(content)


# ===== 이전 API 호환 =====


def test_is_deleted_article_backward_compat():
    """Deprecated 함수도 기본 동작 유지."""
    assert is_deleted_article("제5조 삭제 <1989.12.30>")
    assert is_deleted_article("제36조의2 삭제 <2020.6.9>")
    assert not is_deleted_article("제3조(대항력 등) 임대차는 등기가 없어도...")
