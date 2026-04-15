"""이사이상무 Streamlit demo UI — calls FastAPI backend.

Run:
  cd 2차프로젝트
  streamlit run frontend/streamlit_app.py -- --api http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

import httpx
import streamlit as st

# ---------- Config ----------
DEFAULT_API = os.environ.get("MOVEWISE_API", "http://127.0.0.1:8765")

st.set_page_config(
    page_title="이사이상무",
    page_icon="🏠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------- Styling ----------
st.markdown(
    """
    <style>
    .main > div { max-width: 480px; }
    .stApp { background: #F5F7FB; }
    h1 { color: #003A75; font-size: 28px !important; }
    h2 { color: #1F6FD0; }
    .item-card {
        background: white;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 10px;
        border-left: 4px solid #1F6FD0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .item-card.legal { border-left-color: #E67E22; }
    .citation { color: #666; font-size: 12px; }
    .d-day-badge {
        display: inline-block;
        background: #1F6FD0;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: bold;
    }
    .d-day-badge.legal { background: #E67E22; }
    </style>
    """,
    unsafe_allow_html=True,
)


def call_api(path: str, payload: dict) -> dict | None:
    api = st.session_state.get("api_base", DEFAULT_API)
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{api}{path}", json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        st.error(f"API 호출 실패: {exc}")
        return None


def health_check() -> dict | None:
    api = st.session_state.get("api_base", DEFAULT_API)
    try:
        with httpx.Client(timeout=5) as c:
            r = c.get(f"{api}/")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError:
        return None


# ---------- Sidebar ----------
with st.sidebar:
    st.title("⚙️ 설정")
    st.session_state.setdefault("api_base", DEFAULT_API)
    st.session_state["api_base"] = st.text_input("Backend URL", st.session_state["api_base"])
    health = health_check()
    if health:
        st.success(f"✅ {health['service']} v{health['version']}")
        if health.get("azure_ready"):
            st.info("🧠 Azure LLM 모드")
        else:
            st.warning("🔧 Local fallback 모드")
    else:
        st.error("❌ 백엔드 연결 실패 — uvicorn 실행 확인")

# ---------- Main ----------
st.title("🏠 이사이상무")
st.caption("이사 여정 가이드 — 체크리스트 + SafeContract")

tab_checklist, tab_safe = st.tabs(["📋 이사 체크리스트", "📄 SafeContract"])

# ========== Checklist tab ==========
CONCERN_PRESETS = {
    "임대차 분쟁": ["보증금 반환 우려", "임차권등기", "월세 인상", "갱신요구권"],
    "비용 정산": ["장기수선충당금", "관리비예치금", "공과금 정산"],
    "하자·수리": ["하자 분쟁", "수선 요청"],
    "기타": ["이사업체 분쟁", "전세사기 의심"],
}

with tab_checklist:
    with st.form("checklist_form"):
        col1, col2 = st.columns(2)
        with col1:
            household = st.selectbox("세대 유형", ["자취", "신혼", "가족"])
            contracts = st.multiselect(
                "계약 유형 (중복 선택 가능)",
                ["월세", "전세", "자가"],
                default=["월세"],
            )
        with col2:
            region = st.text_input("지역", "경기도 성남시 분당구")
            move_date = st.date_input("이사 예정일", date.today() + timedelta(days=14))

        st.divider()
        col3, col4, col5, col6 = st.columns(4)
        with col3:
            has_pet = st.checkbox("🐕 반려동물")
        with col4:
            has_car = st.checkbox("🚗 자동차")
        with col5:
            has_children = st.checkbox("👶 자녀")
        with col6:
            is_foreigner = st.checkbox("🌐 외국인")

        school_level = None
        if has_children:
            school_level = st.selectbox("자녀 학교급", ["초등", "중등", "고등"])

        st.markdown("**특이 상황** (해당하는 항목 다중 선택)")
        selected_concerns: list[str] = []
        for group_name, options in CONCERN_PRESETS.items():
            picked = st.multiselect(group_name, options, key=f"concern_{group_name}")
            selected_concerns.extend(picked)

        submitted = st.form_submit_button("체크리스트 생성", type="primary", use_container_width=True)

    if submitted:
        if not contracts:
            st.error("계약 유형을 하나 이상 선택하세요")
            st.stop()
        payload = {
            "household": household,
            "contract": contracts[0],
            "contracts": contracts,
            "region": region,
            "move_date": move_date.isoformat(),
            "has_pet": has_pet,
            "has_car": has_car,
            "has_children": has_children,
            "children_school_level": school_level,
            "is_foreigner": is_foreigner,
            "special_concerns": selected_concerns,
        }
        with st.spinner("체크리스트 생성 중..."):
            data = call_api("/checklist", payload)
        if data:
            st.success(f"✅ {data['total_items']}개 항목 생성")
            if data.get("warning"):
                st.info(data["warning"])

            with st.expander("🔍 LLM이 생성한 검색 쿼리"):
                for q in data["used_queries"]:
                    st.write(f"- {q}")

            st.subheader("📅 타임라인 체크리스트")
            for it in data["items"]:
                legal_cls = "legal" if it["has_legal_deadline"] else ""
                d_day = f"D{it['d_day_offset']:+d}"
                deadline_str = (
                    f"⚠️ 마감 {it['deadline_date']} ({it['deadline_days']}일 기한)"
                    if it.get("deadline_date")
                    else ""
                )
                st.markdown(
                    f"""
                    <div class="item-card {legal_cls}">
                      <span class="d-day-badge {legal_cls}">{d_day}</span>
                      <strong>&nbsp;{it['title']}</strong><br>
                      <span style="color:#666;font-size:13px;">{it['start_date']}</span><br>
                      <span>{it['description'] or ''}</span><br>
                      {f'<span style="color:#E67E22;font-size:12px;">{deadline_str}</span>' if deadline_str else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                for c in it.get("citations", []):
                    label = f"📖 {c['law_name']} {c['article']}"
                    if c.get("article_title"):
                        label += f" — {c['article_title']}"
                    if c.get("article_text"):
                        with st.expander(label):
                            st.write(c["article_text"])
                    else:
                        st.caption(label)

# ========== SafeContract tab ==========
with tab_safe:
    st.caption("⚠️ 이 서비스는 법률 자문이 아닌 참고용 도구입니다.")

    with st.form("safe_form"):
        text = st.text_area(
            "등기부등본 텍스트 붙여넣기 (갑구/을구)",
            height=200,
            placeholder=(
                "예)\n"
                "[갑구]\n"
                "1. 2020.05.12 소유권이전 김철수\n"
                "2. 2024.11.02 임의경매개시결정\n\n"
                "[을구]\n"
                "1. 2021.03.05 근저당권설정 채권최고액 금 2억4천만원 하나은행\n"
                "2. 2023.08.10 가압류 금 5천만원 홍길동"
            ),
        )
        col_a, col_b = st.columns(2)
        with col_a:
            deposit = st.number_input(
                "보증금 (원)", min_value=0, value=100_000_000, step=10_000_000
            )
        with col_b:
            market = st.number_input(
                "예상 시세 (원)", min_value=0, value=300_000_000, step=10_000_000
            )
        submit_safe = st.form_submit_button("분석하기", type="primary", use_container_width=True)

    if submit_safe and text:
        with st.spinner("분석 중..."):
            data = call_api(
                "/safecontract",
                {
                    "text": text,
                    "deposit_krw": deposit,
                    "expected_market_price_krw": market,
                },
            )
        if data:
            jeontse = data["jeontse_ratio"]
            mortgage = data.get("mortgage_ratio", 0.0)
            risk_level = data.get("risk_level", "green")
            jeontse_pct = min(jeontse * 100, 999)
            mortgage_pct = min(mortgage * 100, 999)
            color = {"red": "red", "yellow": "orange", "green": "green"}[risk_level]
            st.markdown(
                f"### 전세가율 <span style='color:{color};'>{jeontse_pct:.1f}%</span>",
                unsafe_allow_html=True,
            )
            if mortgage > 0:
                st.caption(f"근저당비율 {mortgage_pct:.1f}%")
            st.info(data["summary"])

            st.subheader("🚨 위험 항목")
            for r in data["risks"]:
                emoji = {"red": "🔴", "yellow": "🟡", "green": "🟢"}[r["severity"]]
                with st.expander(f"{emoji} {r['label']}", expanded=r["severity"] == "red"):
                    st.write(r["explanation_plain"])
                    for c in r.get("related_laws", []):
                        title = f"📖 {c['law_name']} {c['article']}"
                        if c.get("article_title"):
                            title += f" — {c['article_title']}"
                        st.markdown(f"**{title}**")
                        if c.get("article_text"):
                            st.caption(c["article_text"])

            st.subheader("🔗 다음에 확인하세요")
            for rf in data["referrals"]:
                st.markdown(
                    f"**{rf['icon']} [{rf['name']}]({rf['url']})** — {rf['description']}"
                )

            st.divider()
            st.caption(data["disclaimer"])
