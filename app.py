"""
app.py — 부산 공공기관 커리어 로드맵 내비게이터
================================================
1~3학년 학생을 위한 데이터 기반 직렬 사전설계 도구.
부산교통공사·부산도시공사 공공데이터(채용 경쟁률·합격선·신규채용) 위에서
직렬 적합도와 준비 로드맵을 제시한다.

실행:  streamlit run app.py
배포:  GitHub push → Streamlit Cloud (Secrets에 GEMINI_API_KEY)
"""
import streamlit as st
import plotly.graph_objects as go

import busan_data as bd
import recommender as rc
import gemini_advisor as ai

# ───────────────────────── 페이지 설정 ─────────────────────────
st.set_page_config(page_title="부산 공공기관 커리어 로드맵",
                   page_icon="🧭", layout="wide")

INK, PRIMARY, ACCENT = "#0f2438", "#0e7c86", "#f06543"
GOOD, WARN, BAD, MUTED = "#2e9e6b", "#e0a800", "#d9534f", "#5b7185"

st.markdown(f"""
<style>
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
  html, body, [class*="css"] {{ font-family:'Pretendard',sans-serif; }}
  .main {{ background:#f7f9fb; }}
  .hero {{ border-left:5px solid {ACCENT}; padding:.2rem 0 .2rem 1rem; margin:.2rem 0 1rem; }}
  .hero h1 {{ color:{INK}; font-size:1.7rem; font-weight:800; margin:0; letter-spacing:-.02em; }}
  .hero p  {{ color:{MUTED}; margin:.35rem 0 0; font-size:.98rem; }}
  .reccard {{ background:#fff; border:1px solid #e6edf3; border-radius:14px;
             padding:1.1rem 1.2rem; margin-bottom:.8rem;
             box-shadow:0 1px 3px rgba(15,36,56,.05); }}
  .reccard .rank {{ font-size:.78rem; color:{MUTED}; font-weight:600; }}
  .reccard .track {{ font-size:1.25rem; font-weight:800; color:{INK}; }}
  .scorepill {{ float:right; background:{INK}; color:#fff; font-weight:800;
               border-radius:10px; padding:.25rem .7rem; font-size:1.05rem; }}
  .barwrap {{ background:#eef3f7; border-radius:6px; height:7px; margin:3px 0 9px; }}
  .bar {{ height:7px; border-radius:6px; background:{PRIMARY}; }}
  .tag {{ display:inline-block; font-size:.74rem; font-weight:700; padding:.12rem .5rem;
          border-radius:6px; margin-right:.3rem; }}
  .src {{ color:{MUTED}; font-size:.8rem; }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="hero">
  <h1>🧭 부산 공공기관 커리어 로드맵</h1>
  <p>아직 직렬·자격을 정하기 전, 부산교통공사·부산도시공사 5년 채용데이터로
     <b>나에게 데이터상 유리한 직렬과 준비 순서</b>를 미리 설계합니다.</p>
</div>
""", unsafe_allow_html=True)


@st.cache_data
def get_dataset():
    return bd.build_dataset()

@st.cache_data
def get_profiles():
    return rc.build_track_profiles()

ds = get_dataset()

# ───────────────────────── 사이드바: 학생 프로필 ─────────────────────────
with st.sidebar:
    st.subheader("내 프로필")
    grade = st.select_slider("학년", options=[1, 2, 3, 4], value=2)
    major = st.selectbox("전공계열", list(rc.MAJOR_FIT.keys()))
    certs = st.multiselect(
        "보유 자격증",
        ["전기기사", "전기산업기사", "일반기계기사", "공조냉동기계기사", "토목기사",
         "건축기사", "정보통신기사", "전자기사", "정보처리기사", "SQLD",
         "컴퓨터활용능력1급", "한국사1급"])
    toeic = st.number_input("토익(없으면 0)", 0, 990, 0, step=10)
    social = st.checkbox("사회배려(장애·취업지원·보훈) 대상")
    st.caption("입력은 저장되지 않습니다. 추천은 과거 5년 공시데이터 기반 구조적 경향입니다.")

student = dict(학년=grade, 전공계열=major, 보유자격=certs,
               어학={"토익": toeic or None}, 사회배려=social)
recs = rc.recommend(student)

tab1, tab2, tab3 = st.tabs(["🎯 내 직렬 로드맵", "📊 부산 채용 미스매치 진단", "💬 AI 커리어 상담"])

# ───────────────────────── 탭 1: 로드맵 ─────────────────────────
def class_color(c):
    return {"과경쟁": BAD, "미달위험": WARN, "적정": GOOD}.get(c, MUTED)

with tab1:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("##### 데이터가 추천하는 직렬 (전공 자격 범위 내)")
        if not recs:
            st.info("선택한 전공계열에 매칭되는 직렬 데이터가 없습니다.")
        for i, r in enumerate(recs, 1):
            comp = r["구성"]
            social_tag = (f'<span class="tag" style="background:#fde8e1;color:{ACCENT}">사회배려 전형 반영</span>'
                          if r["사회배려적용"] else "")
            st.markdown(f"""
            <div class="reccard">
              <span class="scorepill">{r['적합도']}</span>
              <div class="rank">{i}순위 · 적합도</div>
              <div class="track">{r['직렬군']}</div>
              {social_tag}
              <div style="margin-top:.6rem;font-size:.82rem;color:{MUTED}">전공적합 {int(comp['전공적합']*100)}%</div>
              <div class="barwrap"><div class="bar" style="width:{int(comp['전공적합']*100)}%"></div></div>
              <div style="font-size:.82rem;color:{MUTED}">경쟁여유 {int(comp['경쟁여유']*100)}% · 5년평균 {r['데이터']['평균경쟁률']}:1</div>
              <div class="barwrap"><div class="bar" style="width:{int(comp['경쟁여유']*100)}%;background:{ACCENT}"></div></div>
              <div style="font-size:.85rem;color:{INK};margin-top:.5rem">
                📌 {r['로드맵']['필기목표']}<br>
                🎓 취득권장: {', '.join(r['로드맵']['취득권장자격'])}<br>
                📈 채용추세: <b style="color:{class_color('적정' if r['데이터']['추세']!='감소' else '과경쟁')}">{r['데이터']['추세']}</b>
                {('· ' + r['로드맵']['어학']) if r['로드맵']['어학'] else ''}
              </div>
              {f'<div style="font-size:.8rem;color:{ACCENT};margin-top:.4rem">★ {r["로드맵"]["사회배려안내"]}</div>' if r['로드맵']['사회배려안내'] else ''}
            </div>
            """, unsafe_allow_html=True)
    with c2:
        st.markdown("##### AI 맞춤 로드맵")
        with st.spinner("데이터 기반 로드맵 생성 중…"):
            st.info(ai.narrate_roadmap(student, recs))
        st.caption("AI는 위 공공데이터 수치에만 근거해 서술하도록 제한되어 있습니다.")

# ───────────────────────── 탭 2: 미스매치 진단 ─────────────────────────
with tab2:
    mm = [m for m in ds["mismatch"] if m["평균경쟁률"]]
    mm.sort(key=lambda m: m["평균경쟁률"])
    fig = go.Figure(go.Bar(
        x=[m["평균경쟁률"] for m in mm],
        y=[m["직렬군"] for m in mm], orientation="h",
        marker_color=[class_color(m["분류"]) for m in mm],
        text=[f"{m['평균경쟁률']}:1" for m in mm], textposition="outside",
    ))
    fig.update_layout(
        title="직렬군별 5년 평균 경쟁률 — 빨강=과경쟁, 노랑=미달위험, 초록=적정",
        height=420, margin=dict(l=10, r=40, t=50, b=10),
        plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(fig, width='stretch')

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("경쟁률 레코드", f"{ds['meta']['경쟁률레코드']}건")
    k2.metric("합격선 예측 검증(MAE)", f"{ds['backtest']['MAE']}점",
              help=f"2020–23 학습 → 2024 검증, 합격선 범위 {ds['backtest']['합격선범위']}")
    k3.metric("사회배려 전형 평균경쟁률", f"{ds['esg']['평균경쟁률']}:1")
    k4.metric("사회배려 미달·위험", f"{ds['esg']['미달건수']} · {ds['esg']['미달위험건수']}건")

    st.markdown("##### 신규채용 추세 (정규직 일반)")
    tfig = go.Figure()
    for inst, rows in ds["hire_trend"].items():
        tfig.add_trace(go.Scatter(x=[r["연도"] for r in rows],
                                  y=[r["정규직일반"] for r in rows],
                                  mode="lines+markers", name=inst))
    tfig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                       plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(tfig, width='stretch')
    st.caption("출처: data.go.kr — 부산교통공사 채용경쟁률·신규채용현황(15145399·15145396), "
               "부산도시공사 채용경쟁률·신규채용현황. 데이터는 5년 누적 구조 경향이며 "
               "당해연도 채용규모 변동은 각 기관 공고로 재확인이 필요합니다.")

# ───────────────────────── 탭 3: AI 상담 ─────────────────────────
with tab3:
    st.markdown("##### 무엇이든 물어보세요 (데이터 근거로 답합니다)")
    st.caption('예: "전기직이랑 신호직 중 뭐가 더 붙기 쉬워?" / "사무직은 토익 몇 점 필요해?"')
    if "chat" not in st.session_state:
        st.session_state.chat = []
    for role, msg in st.session_state.chat:
        with st.chat_message(role):
            st.write(msg)
    if q := st.chat_input("질문 입력"):
        st.session_state.chat.append(("user", q))
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            with st.spinner("…"):
                a = ai.chat(student, recs, q)
            st.write(a)
        st.session_state.chat.append(("assistant", a))
