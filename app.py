"""
app.py — 부산 공공기관 커리어 로드맵 내비게이터 (v4 · 미니멀 재디자인)
======================================================================
v3(3탭) → v4 변경
  [가독성] 탭1을 '한 화면=한 가지 일'로. 처음엔 추천 카드 3개 + 맨 위 한 줄 결론만
    보이고, 점수 산식·체크리스트·AI는 전부 접는다(expander). 곁가지가 핵심을
    가리던 산만함 제거.
  [카피] 전문용어를 일상어로. '데이터 유리도(시뮬)'→'준비 추천 점수',
    '가중경쟁률 70.3:1'→'평균 70명 중 1명', '필기 기준선+버퍼'→'필기 68점 목표'.
    설명 캡션은 길게 깔지 않고 한 줄로 줄이거나 접는다.
  [디자인] 차분/모던. 메인 1색(딥틸) + 신호등 3색(여유/보통/치열)만 사용.
    강조 주황색 제거, 카드 그림자·테두리 최소화, 여백을 넉넉히. 신호등이 시그니처.

설계 의도는 유지(v3): 본체=탭1 로드맵, 탭2=근거·품질(심사 방어),
탭3=부가도구. AI는 동의 버튼을 눌렀을 때만 외부 전송(고지=동작 일치).

실행:  streamlit run app.py
배포:  GitHub push → Streamlit Cloud (Secrets에 GEMINI_API_KEY)
"""
import streamlit as st
import plotly.graph_objects as go

import busan_data as bd
import recommender as rc
import gemini_advisor as ai
import scoring as sc

st.set_page_config(page_title="PassNavi · 부산 공공기관 커리어 내비",
                   page_icon="🧭", layout="wide")

# ── 디자인 토큰 (차분/모던: 메인 1색 + 신호등) ──
INK   = "#15212e"   # 본문 글자
TEAL  = "#13606b"   # 메인 1색 (딥 틸)
PAPER = "#fbfcfd"   # 배경
LINE  = "#eaeef2"   # 가는 테두리
MUTED = "#6b7a89"   # 보조 글자
GOOD, WARN, BAD = "#2e9e6b", "#e0a800", "#d9534f"   # 신호등: 여유/보통/치열

st.markdown(f"""
<style>
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
  html, body, [class*="css"] {{ font-family:'Pretendard',sans-serif; color:{INK}; }}
  .main {{ background:{PAPER}; }}
  .block-container {{ padding-top:2.2rem; max-width:1100px; }}

  /* 헤더 — PassNavi 브랜드 */
  .hd {{ display:flex; align-items:center; gap:.6rem; margin-bottom:.2rem; }}
  .hd .logo {{ font-size:1.9rem; line-height:1; }}
  .hd .brand {{ font-size:1.7rem; font-weight:800; letter-spacing:-.02em;
                background:linear-gradient(90deg,{TEAL},#1b8a99);
                -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                background-clip:text; }}
  .hd .tag {{ font-size:.82rem; font-weight:700; color:{TEAL}; background:#eef5f6;
              padding:.2rem .55rem; border-radius:999px; align-self:center; }}
  .hd-sub {{ color:{MUTED}; margin:.1rem 0 0; font-size:.95rem; }}

  /* 서비스 설명 배너 (자소설닷컴식 깔끔 카드) */
  .intro {{ background:#fff; border:1px solid {LINE}; border-left:4px solid {TEAL};
            border-radius:14px; padding:1rem 1.2rem; margin:1rem 0 .4rem; }}
  .intro .t {{ font-weight:800; font-size:1rem; margin-bottom:.45rem; }}
  .intro .d {{ color:{INK}; font-size:.9rem; line-height:1.75; }}
  .intro .d b {{ color:{TEAL}; }}
  .intro .steps {{ display:flex; gap:.5rem; flex-wrap:wrap; margin-top:.7rem; }}
  .intro .step {{ flex:1; min-width:150px; background:{PAPER}; border:1px solid {LINE};
                  border-radius:10px; padding:.6rem .8rem; font-size:.84rem; }}
  .intro .step b {{ color:{TEAL}; display:block; margin-bottom:.15rem; }}

  /* 한 줄 결론 배너 */
  .verdict {{ background:{TEAL}; color:#fff; border-radius:14px;
              padding:1.1rem 1.3rem; margin:1.3rem 0 1.6rem; }}
  .verdict .lbl {{ font-size:.78rem; opacity:.8; font-weight:600; letter-spacing:.02em; }}
  .verdict .big {{ font-size:1.35rem; font-weight:800; margin-top:.2rem; line-height:1.35; }}
  .verdict .sub {{ font-size:.86rem; opacity:.85; margin-top:.45rem; }}

  /* 추천 카드 — 그림자/테두리 최소화, 여백 넉넉 */
  .card {{ background:#fff; border:1px solid {LINE}; border-radius:16px;
           padding:1.3rem 1.5rem; margin-bottom:1rem; }}
  .card .rk {{ font-size:.76rem; color:{MUTED}; font-weight:700; letter-spacing:.03em; }}
  .card .nm {{ font-size:1.4rem; font-weight:800; margin:.15rem 0 .1rem; }}
  .card .sc {{ float:right; text-align:center; }}
  .card .sc .v {{ font-size:2rem; font-weight:800; color:{TEAL}; line-height:1; }}
  .card .sc .u {{ font-size:.7rem; color:{MUTED}; font-weight:600; }}

  /* 신호등 — 이 페이지의 시그니처 */
  .signal {{ display:inline-flex; align-items:center; gap:.4rem; font-size:.9rem;
             font-weight:700; padding:.3rem .7rem; border-radius:999px; margin-top:.5rem; }}
  .sig-여유 {{ background:#e9f6ef; color:{GOOD}; }}
  .sig-보통 {{ background:#fdf4e0; color:#a9810a; }}
  .sig-치열 {{ background:#fcebeb; color:{BAD}; }}
  .dot {{ width:.6rem; height:.6rem; border-radius:50%; display:inline-block; }}

  .pill {{ display:inline-block; font-size:.74rem; font-weight:700; padding:.15rem .55rem;
           border-radius:7px; margin:.5rem .3rem 0 0; background:#eef5f6; color:{TEAL}; }}
  .facts {{ color:{INK}; font-size:.9rem; line-height:1.7; margin-top:.7rem; }}
  .facts b {{ font-weight:700; }}
  .muted {{ color:{MUTED}; font-size:.85rem; }}
  .sect {{ font-size:1.08rem; font-weight:800; margin:.3rem 0 .2rem; }}

  /* Streamlit 기본 요소 톤 정리 */
  .stTabs [data-baseweb="tab-list"] {{ gap:.3rem; }}
  .stTabs [data-baseweb="tab"] {{ font-weight:700; }}
  div[data-testid="stExpander"] {{ border:1px solid {LINE}; border-radius:12px; }}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hd">
  <span class="logo">🧭</span>
  <span class="brand">PassNavi</span>
  <span class="tag">패스나비 · 부산 공공기관</span>
</div>
<div class="hd-sub">합격까지 가는 길을 데이터로 안내하는 커리어 내비게이터</div>
""", unsafe_allow_html=True)

with st.container():
    st.markdown("""
    <div class="intro">
      <div class="t">🧭 PassNavi는 어떤 서비스인가요?</div>
      <div class="d">
        부산 공공기관(교통·도시·관광공사 등)의 <b>공개 채용데이터</b>를 모아,
        직무를 아직 못 정한 학생에게 <b>데이터상 덜 치열한 직무</b>와
        <b>졸업까지의 준비 순서</b>를 안내해요. 합격을 예측하는 게 아니라,
        과거 채용데이터로 정리한 <b>준비 우선순위</b>를 보여줘요.
      </div>
      <div class="steps">
        <div class="step"><b>1. 내 정보 입력</b>왼쪽에서 학년·전공·자격증을 넣고 '추천 받기'</div>
        <div class="step"><b>2. 데이터 추천</b>경쟁률·신뢰도 기반 직무 순위와 우회 경로 확인</div>
        <div class="step"><b>3. 근거 확인</b>'근거·데이터' 탭에서 출처와 비환각 검증까지</div>
      </div>
    </div>
    """, unsafe_allow_html=True)



@st.cache_data(show_spinner=False)
def get_dataset():
    return bd.build_dataset()

ds = get_dataset()


# ── 신호등: 경쟁률을 '여유/보통/치열'로 ──
def signal(ratio):
    """경쟁률 → (라벨, 색, 쉬운 설명). 'N:1'과 'N명 중 1명'을 같이 보여준다."""
    if not ratio:
        return ("데이터 적음", MUTED, "표본이 적어요")
    r = round(ratio)
    desc = f"경쟁률 {r}:1 (약 {r}명 중 1명 합격)"
    if ratio <= 15:
        return ("여유", GOOD, desc)
    if ratio <= 50:
        return ("보통", WARN, desc)
    return ("치열", BAD, desc)


def short_target(roadmap_target: str) -> str:
    """'필기 기준선 66점 + 버퍼 2점 → 68점 목표' → '필기시험 68점 목표(100점 만점)'."""
    import re
    m = re.search(r"(\d+)점 목표", roadmap_target)
    return f"필기시험 {m.group(1)}점 목표 (100점 만점)" if m else roadmap_target


def short_lang(lang_msg) -> str:
    """'공고상 토익 최저 700점 사례 확인됨 (현재 800 — 충족)'
       → '토익 700 이상 필요 · ✅ 내 점수로 충족'."""
    if not lang_msg:
        return ""
    import re
    m = re.search(r"토익 최저 (\d+)", lang_msg)
    base = f"토익 {m.group(1)}점 이상 필요" if m else "어학 요건 있음"
    if "충족" in lang_msg and "부족" not in lang_msg:
        return base + " · ✅ 내 점수로 충족"
    if "부족" in lang_msg:
        g = re.search(r"(\d+)점 부족", lang_msg)
        return base + (f" · ⚠️ {g.group(1)}점 부족" if g else " · ⚠️ 부족")
    return base + " (내 어학 점수 입력하면 충족 여부 표시)"


def _fmt_req(req: dict) -> str:
    if not req:
        return "별도 어학요건 없음"
    parts = []
    for k, lbl in [("TOEIC","TOEIC"),("TOEFL_iBT","TOEFL"),("TEPS_new","New TEPS"),
                   ("TOEIC_S","TOEIC S"),("OPIc","OPIc")]:
        if req.get(k):
            parts.append(f"{lbl} {req[k]}")
    return " / ".join(parts) + " 중 1개" if parts else "별도 어학요건 없음"


# ───────────────────── 사이드바: 프로필 ─────────────────────
with st.sidebar:
    st.subheader("내 정보")
    st.caption("입력하고 ‘추천 받기’를 누르세요.")
    with st.form("profile"):
        grade = st.select_slider("학년", options=[1, 2, 3, 4], value=2)
        major = st.selectbox("전공", list(rc.MAJOR_FIT.keys()),
                             index=len(rc.MAJOR_FIT) - 1)
        certs = st.multiselect("가진 자격증 (없으면 비워두기)", sc.CERT_MASTER)

        st.markdown("**어학 점수** (있는 것만, 없으면 비워두기)")
        st.caption("토익은 숫자만, 오픽은 등급을 골라요. 여러 개 넣어도 돼요.")
        toeic_in = st.number_input("토익(TOEIC) 점수", min_value=0, max_value=990,
                                   value=0, step=5, help="0이면 미입력으로 처리해요.")
        opic_in = st.selectbox("오픽(OPIc) 등급",
                               ["없음", "IL", "IM1", "IM2", "IM3", "IH", "AL"])
        with st.expander("토플·텝스도 있으면"):
            toefl_in = st.number_input("토플(TOEFL iBT)", min_value=0, max_value=120,
                                       value=0, step=1)
            teps_in = st.number_input("텝스(New TEPS)", min_value=0, max_value=600,
                                      value=0, step=1)

        region = st.selectbox("사는 곳 (주민등록)", sc.RESIDENCY_REGIONS)

        with st.expander("취업지원·장애 전형 해당자만"):
            social_v = st.selectbox("취업지원대상자 가점", [0, 5, 10],
                                    help="국가보훈부 증명서 비율(없으면 0)")
            disabled = st.checkbox("장애인 등록")

        with st.expander("추천 기준 직접 바꾸기 (안 건드려도 됨)"):
            st.caption("기본값을 권장해요.")
            w_fit = st.slider("전공 맞춤", 0.0, 1.0, 0.45, 0.05)
            w_comp = st.slider("경쟁 여유", 0.0, 1.0, 0.35, 0.05)
            w_size = st.slider("데이터 충분한 정도", 0.0, 1.0, 0.20, 0.05)

        submitted = st.form_submit_button("추천 받기", width="stretch")
    st.caption("🔒 입력값은 추천 계산 때 외부로 안 나가요. ‘AI 요약’ 버튼을 직접 "
               "누를 때만 외부 AI로 전송됩니다.")

if submitted or "student" not in st.session_state:
    tot = (w_fit + w_comp + w_size) or 1.0
    weights = dict(fit=w_fit/tot, comp=w_comp/tot, size=w_size/tot)
    # [버그 수정] 과거엔 자유 텍스트 1칸을 그대로 점수로 썼다. 사용자가 placeholder
    # 예시("토익 780")를 따라 "토익 800"처럼 입력하면 int/float 파싱이 실패해 어학이
    # 통째로 None 처리됐고, 그래서 토익 800을 넣어도 '충족' 표시가 안 뜨고 관광공사
    # 체커가 '어학 미달'로 떴다. 이제 숫자/등급 전용 위젯에서만 값을 받아 조립한다.
    lang_scores = {}
    if toeic_in and toeic_in > 0:
        lang_scores["토익(TOEIC)"] = int(toeic_in)
    if opic_in and opic_in != "없음":
        lang_scores["오픽(OPIc)"] = opic_in
    if toefl_in and toefl_in > 0:
        lang_scores["토플(TOEFL iBT)"] = int(toefl_in)
    if teps_in and teps_in > 0:
        lang_scores["텝스(TEPS)"] = int(teps_in)
    lsum = sc.lang_summary(lang_scores)
    st.session_state.student = dict(
        학년=grade, 전공계열=major, 보유자격=certs,
        어학={"토익": lsum["토익등가"]},
        어학상세=lsum, 어학원본=lang_scores, 거주지=region,
        사회배려=bool(social_v or disabled),
        가산={"취업지원대상자": social_v, "장애인": disabled})
    st.session_state.weights = weights
    # ── 진행 표시 (버튼 눌렀을 때만, 첫 로드 때는 조용히 실행) ──
    if submitted:
        with st.sidebar:
            prog = st.progress(0, text="분석 중…")
        prog.progress(30, text="데이터 조회 중…")
        st.session_state.recs = rc.recommend(
            st.session_state.student, weights=weights, ds=ds)
        prog.progress(80, text="우회 경로 계산 중…")
        st.session_state.pop("ai_roadmap", None)
        prog.progress(100, text="완료!")
        import time; time.sleep(0.4)
        prog.empty()
        st.toast("✅ 추천 완료! 아래 결과를 확인하세요.", icon="🎯")
    else:
        st.session_state.recs = rc.recommend(
            st.session_state.student, weights=weights, ds=ds)
        st.session_state.pop("ai_roadmap", None)

student = st.session_state.student
recs = st.session_state.recs

tab1, tab2, tab3 = st.tabs(
    ["🎯 내 로드맵", "📊 근거·데이터", "🧰 더보기"])

# ════════════════════════ 탭 1: 내 로드맵 ════════════════════════
with tab1:
    # ── 맨 위: 한 줄 결론 ──
    if recs:
        top = recs[0]
        lbl, col, desc = signal(top["데이터"]["일반경쟁률"])
        st.markdown(f"""
        <div class="verdict">
          <div class="lbl">데이터가 추천하는 1순위</div>
          <div class="big">{top['직무']} — 경쟁 {lbl}</div>
          <div class="sub">{desc} · {major} {grade}학년 기준 · 다음 할 일: {short_target(top['로드맵']['필기목표'])}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("왼쪽에서 전공을 고르고 ‘추천 받기’를 눌러주세요.")

    st.markdown('<div class="muted">합격 예측이 아니라, 과거 채용데이터로 정리한 '
                '<b>준비 우선순위</b>예요.</div>', unsafe_allow_html=True)
    st.write("")

    # ── 추천 카드 3개 (이 화면의 주인공) ──
    for i, r in enumerate(recs, 1):
        comp, d = r["구성"], r["데이터"]
        lbl, col, desc = signal(d["일반경쟁률"])
        # 경쟁이 치열한데도 1순위면(전공 적합이 높아서) 이유를 한 줄로 알려줌
        why_high = ""
        if i == 1 and col == BAD and comp["전공적합"] >= 0.95:
            why_high = ('<div class="muted" style="margin-top:.45rem">'
                        '경쟁은 치열하지만, 내 전공이 가장 잘 맞아 1순위예요.</div>')
        tags = ""
        if r["블라인드"]:
            tags += '<span class="pill">전공 안 봄(블라인드)</span>'
        if r["사회배려적용"]:
            tags += '<span class="pill">사회배려 전형 반영</span>'
        certs_txt = ", ".join(r["로드맵"]["취득권장자격"])
        lang_txt = short_lang(r["로드맵"]["어학"])
        exam_compo = r["로드맵"].get("필기구성", "NCS + 직무 평가")
        conf = d.get("신뢰", {})
        conf_emoji = {"양호": "🟢", "보통": "🟡", "낮음": "🔴"}.get(conf.get("등급"), "")
        conf_line = (f'<div class="muted" style="margin-top:.4rem">'
                     f'데이터 신뢰도 {conf_emoji}{conf.get("등급","-")} '
                     f'· {conf.get("한줄","")}</div>') if conf else ""

        st.markdown(f"""
        <div class="card">
          <div class="sc"><div class="v">{r['적합도']}</div><div class="u">추천 점수</div></div>
          <div class="rk">{i}순위</div>
          <div class="nm">{r['직무']}</div>
          <span class="signal sig-{lbl}">
            <span class="dot" style="background:{col}"></span>{desc}</span>
          {conf_line}
          {why_high}
          <div>{tags}</div>
          <div class="facts">
            🎯 <b>{r['로드맵']['필기목표']}</b><br>
            <span class="muted">📝 필기 구성: {exam_compo}</span><br>
            🎓 먼저 딸 자격증: <b>{certs_txt}</b>
            {('<br>🗣 ' + lang_txt) if lang_txt else ''}
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(f"💡 추천 점수 {r['적합도']}점은 무슨 뜻인가요? · {i}순위 이유"):
            st.markdown(
                f"**추천 점수**는 합격 가능성이 아니에요. "
                f"'내 전공으로 지원 가능한지 + 경쟁이 덜한지 + 데이터가 믿을 만한지'를 "
                f"0~100으로 합친 **'데이터상 유리한 정도'**예요. 높을수록 데이터상 유리해요.")
            comp_r = round(d["일반경쟁률"]) if d["일반경쟁률"] else None
            bullets = []
            if r["블라인드"]:
                bullets.append("**전공 적합**: 이 직무는 전공을 안 보는 블라인드 채용이라 누구나 지원 가능")
            else:
                bullets.append(f"**전공 적합**: 내 전공({major})으로 지원하기 적합한 직무")
            if comp_r:
                bullets.append(f"**경쟁 여유**: 과거 평균 경쟁률 {comp_r}:1 "
                               f"({'덜 치열한 편' if d['일반경쟁률']<=50 else '치열한 편'})")
            conf = d.get("신뢰", {})
            if conf.get("한줄"):
                bullets.append(f"**데이터 신뢰도**: {conf.get('등급')} — {conf['한줄']}")
            st.markdown("\n".join(f"- {b}" for b in bullets))

            기관별 = r["로드맵"].get("필기기관별", [])
            if 기관별:
                st.markdown("**과거 합격자 필기 평균 점수** (100점 만점) — "
                            "지원할 기관 기준으로 보세요:")
                for t in 기관별:
                    st.markdown(
                        f"- **{t['기관'].replace('부산','')}**: 합격자 평균 "
                        f"**{t['합격선평균']}점** → 안전 버퍼 +{t['버퍼']}점 = "
                        f"**목표 {t['목표']}점** (표본 {t['표본']}건)")
                if len(기관별) > 1:
                    st.info("두 기관을 **하나의 평균으로 합치지 않았어요.** 교통공사·도시공사는 "
                            "필기 과목이 서로 달라(예: 운영직은 NCS+일반상식, 일부는 NCS+전공) "
                            "합치면 의미 없는 숫자가 돼요. **지원할 기관 줄만 보면 됩니다.**")
            else:
                st.caption("이 직무는 합격선이 공개되지 않아, 목표 점수는 공고·기출로 직접 "
                           "잡아야 해요. (공기업 필기는 보통 과목 40%+총점 60% 규정)")

            # ── 합격자 준비 현실(외부 취업정보 — 데이터와 분리, 출처 표기) ──
            guide = r["로드맵"].get("합격자가이드")
            if guide:
                st.markdown("---")
                st.markdown(f"**🧭 합격자들은 실제로 이만큼 준비해요**")
                st.markdown(f"> {guide['한줄']}")
                st.markdown("**실제 합격권 스펙:**")
                for sp in guide["합격자스펙"]:
                    st.markdown(f"- {sp}")
                st.warning(guide["현실"])
                st.caption(f"※ 위 '합격자 준비' 항목은 채용 데이터가 아니라 외부 취업정보 기반 "
                           f"참고 가이드예요(경쟁률·합격선 수치와 구분). 출처: {guide['출처']}.")

            if r["로드맵"]["블라인드안내"]:
                st.info(r["로드맵"]["블라인드안내"])
            if r["로드맵"].get("신뢰경고"):
                st.warning(r["로드맵"]["신뢰경고"])
            if r["로드맵"]["사회배려안내"]:
                st.warning(r["로드맵"]["사회배려안내"])

    if not recs:
        st.stop()

    st.write("")
    # ── 전략적 우회 경로 (독창성 핵심) ──
    detours = rc.find_detours(student, recs, ds)
    if detours["전형우회"] or detours["직렬우회"]:
        st.markdown('#### 🧭 전략적 우회 경로')
        st.caption("같은 자격으로 **데이터상 경쟁이 덜한 길**을 찾아줘요. "
                   "합격 확률이 아니라 **실제 경쟁률의 비율**입니다.")
        # 전형 우회 — 본인 해당 전형이 있을 때만(점수에 안 들어간 큰 격차)
        for d in detours["전형우회"]:
            note = (f"**{d['직무']}**: 일반 {d['일반경쟁률']}:1 → "
                    f"내가 해당하는 **{d['전형']} 전형 {d['전형경쟁률']}:1** "
                    f"— 경쟁률이 약 **{d['경쟁배수']}배 낮음**")
            if d["참고용"]:
                st.warning(note + f"  \n⚠️ 단, 이 전형은 표본 {d['표본n']}건(공고 1~2개)이라 "
                                  "**참고용**입니다. 반드시 공고로 응시자격·경쟁을 확인하세요.")
            else:
                st.success(note + f"  \n(표본 {d['표본n']}건) 전형별 응시자격·증빙은 공고에서 확인하세요.")
        # 직렬 우회 — 1순위가 과열일 때만 뜸
        for d in detours["직렬우회"]:
            certs = ", ".join(d["준비자격"])
            st.info(f"**{d['현재직무']}**({d['현재경쟁률']}:1)이 붐비면, 같은 전공으로 갈 수 있는 "
                    f"**{d['대안직무']}**({d['대안경쟁률']}:1)은 경쟁이 약 **{d['경쟁배수']}배 낮아요**. "
                    f"(데이터 신뢰도 {d['신뢰등급']})  \n→ 준비할 것: {certs}. "
                    "응시자격은 공고로 확인하세요.")
        st.write("")

    st.write("")
    # ── 다음 할 일 체크리스트 (접어둠) ──
    with st.expander("✅ 다음에 할 일 체크리스트 (1순위 기준)"):
        st.caption("체크는 이 화면에서만 기억돼요(새로고침하면 초기화).")
        rm0 = recs[0]["로드맵"]
        steps = []
        for c in rm0["취득권장자격"]:
            if "이미 보유" not in c:
                steps.append(("자격", f"{c} 취득"))
        if rm0["어학"]:
            steps.append(("어학", short_lang(rm0["어학"])))
        # 필기는 '구성 + 기관별 목표'를 그대로 노출(막연한 'NCS 공부' 금지)
        steps.append(("필기", f"{rm0['필기목표']} · 구성: {rm0.get('필기구성','')}"))

        if "progress" not in st.session_state:
            st.session_state.progress = {}
        done = 0
        for idx, (kind, label) in enumerate(steps):
            key = f"step_{idx}"
            v = st.checkbox(f"[{kind}] {label}",
                            value=st.session_state.progress.get(key, False),
                            key=f"chk_{idx}")
            st.session_state.progress[key] = v
            done += int(v)
        pct = int(100 * done / len(steps)) if steps else 0
        st.progress(pct / 100, text=f"{pct}% 완료")
        nxt = next((s for j, s in enumerate(steps)
                    if not st.session_state.progress.get(f"step_{j}")), None)
        if nxt:
            st.success(f"👉 지금 시작: {nxt[1]}")
        else:
            st.success("다 했어요! 이제 공고를 기다리며 모니터링하세요.")
        g0 = rm0.get("합격자가이드")
        if g0:
            st.caption("⚠️ 현실 체크: " + g0["현실"])

    # ── 데이터 근거 AI 상담 (접어둠, 동의식) ──
    with st.expander("🤖 데이터로만 답하는 AI 상담 — 추천에 없는 직무까지 물어보기 (선택 · 외부 전송)"):
        st.markdown(
            "**이게 무슨 기능이에요?** 추천 카드에 안 나온 직무·전형까지, **우리 데이터 안에서** "
            "AI가 정리해 주는 상담 코너예요. 핵심은 **‘지어내지 않는다’**예요 — 경쟁률·합격선 "
            "같은 숫자는 코드가 데이터에서 **직접 찾아** AI에게 넘기고, AI는 **문장으로 정리만** "
            "해요. 데이터에 없는 건 가짜 숫자 대신 ‘공고로 확인하세요’라고 답하고요.")
        st.caption("이럴 때 써요 → ① 추천에 안 나온 다른 직무 경쟁률이 궁금할 때 "
                   "② 두 직무를 비교하고 싶을 때 ③ 사회배려 전형이 얼마나 유리한지 볼 때")
        st.warning("아래 버튼/질문을 누르면 내 프로필·질문이 외부 AI(Gemini)로 전송돼요.")

        # 1) 한 번에: 내 로드맵 요약
        if st.button("✍️ 내 1순위 로드맵 요약 받기", width="stretch"):
            with st.spinner("정리 중…"):
                st.session_state.ai_roadmap = ai.narrate_roadmap(student, recs, ds)
        if st.session_state.get("ai_roadmap"):
            st.info(st.session_state.ai_roadmap)

        st.divider()
        # 2) 예시 질문 — 클릭하면 바로 질문 실행(뭘 물어야 할지 모르는 사람용)
        st.markdown("**예시 질문 — 눌러보세요** (직접 입력도 가능해요):")
        examples = ["전기직 경쟁률은 얼마야?",
                    "사무·행정이랑 전기직 중 어디가 덜 치열해?",
                    "사회배려 전형은 일반전형보다 얼마나 유리해?",
                    "부산시설공단 합격선 알려줘"]
        ex_cols = st.columns(2)
        pending = None
        for bi, ex in enumerate(examples):
            if ex_cols[bi % 2].button(ex, key=f"exq_{bi}", width="stretch"):
                pending = ex

        if "chat" not in st.session_state:
            st.session_state.chat = []
        for role, msg in st.session_state.chat:
            with st.chat_message(role):
                st.write(msg)
        typed = st.chat_input("직접 질문하기 (전송 시 외부 AI로 전송)")
        q = pending or typed
        if q:
            st.session_state.chat.append(("user", q))
            with st.chat_message("user"):
                st.write(q)
            with st.chat_message("assistant"):
                with st.spinner("…"):
                    a = ai.chat(student, recs, q, ds=ds)
                st.write(a)
            st.session_state.chat.append(("assistant", a))

# ════════════════ 탭 2: 근거·데이터 ════════════════
with tab2:
    st.markdown('<div class="sect">이 추천, 어떤 데이터로 만든 거예요?</div>',
                unsafe_allow_html=True)
    st.caption(ds["coverage"]["한줄정정"])
    st.write("")

    st.write("")

    # ── AI 비환각 검증 (쉬운 말 + ? 도움말 + 실시간 확인) ──
    st.markdown("**🛡️ 이 AI는 모르는 걸 지어내지 않아요** (비환각 검증)")
    st.caption("취업 정보에 가짜 숫자는 사고예요. 그래서 수치는 코드가 데이터에서 직접 "
               "찾고, AI는 문장으로 정리만 해요. 없는 값은 '공고 확인'이라고 답하고요.")
    h1, h2, h3 = st.columns(3)
    h1.metric("데이터 있는 질문, 정답률", "100%",
              help="경쟁률·합격선이 데이터에 있으면 AI가 그 값을 그대로 인용해요. "
                   "다른 숫자로 바꾸거나 지어내지 않아요. (검증 하네스 13개 질의 실측)")
    h2.metric("데이터 없는 질문, 방어율", "100%",
              help="우리한테 없는 값(예: 시설공단 합격선, 당해 채용일정)을 물으면, "
                   "그럴듯한 가짜 숫자 대신 '공고로 확인하세요'라고 답해요.")
    h3.metric("지어낸 수치", "0건",
              help="위 13개 질의 전체에서, 데이터에 없는 경쟁률·합격선·점수를 새로 "
                   "만들어 답한 경우가 한 건도 없어요.")
    with st.expander("직접 확인해보기 (실시간)"):
        st.caption("아래 버튼을 누르면, 일부러 '우리한테 없는 데이터'를 AI에게 물어봐요. "
                   "AI가 가짜 숫자를 만드는지, 정직하게 방어하는지 바로 보여드려요.")
        if st.button("‘부산시설공단 합격선’처럼 없는 걸 물어보기", key="halluc_demo"):
            demo_q = "부산시설공단 일반전형 필기 합격선 평균은?"
            demo_a = ai.chat(student, recs, demo_q, ds=ds)
            st.markdown(f"**질문**: {demo_q}")
            st.success(f"**AI 답변**: {demo_a}")
            st.caption("→ 가짜 점수를 만들지 않고 '데이터에 없음 → 공고 확인'으로 답하면 통과예요.")
    st.write("")

    st.markdown("**직무별 경쟁률** — 몇 명 중 1명 뽑았나 (낮을수록 들어가기 쉬움)")
    st.caption("막대 옆 숫자는 '경쟁률 N:1' = 평균적으로 N명 지원해서 1명 합격했다는 뜻이에요.")
    mm = [m for m in ds["mismatch"] if m["평균경쟁률"]]
    mm.sort(key=lambda m: m["평균경쟁률"])
    cmap = {"과경쟁": BAD, "미달위험": WARN, "적정": GOOD}
    fig = go.Figure(go.Bar(
        x=[m["평균경쟁률"] for m in mm], y=[m["직무"] for m in mm], orientation="h",
        marker_color=[cmap.get(m["분류"], MUTED) for m in mm],
        text=[f"{m['평균경쟁률']}:1" for m in mm], textposition="outside"))
    fig.update_layout(title="🔴 치열 · 🟡 보통 · 🟢 여유",
                      height=360, margin=dict(l=10, r=40, t=40, b=10),
                      plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(fig, width="stretch")

    cs = ds["cut_stat"]
    with st.expander("일반전형 vs 사회배려전형 — 경쟁률 차이 보기"):
        st.markdown("같은 직무라도 **어느 전형으로 지원하느냐**에 따라 경쟁률이 달라요. "
                    "아래 막대는 **경쟁률(몇 명 중 1명 뽑았나)**을 비교한 거예요. "
                    "사회배려 전형(장애·취업지원 등 해당자만 지원)이 보통 경쟁률이 더 낮아요.")
        gj = [(j, s["일반_가중경쟁률"], s["사회배려_가중경쟁률"])
              for j, s in ds["job_stats"].items()
              if s["일반_가중경쟁률"] and s["사회배려_가중경쟁률"]]
        gj.sort(key=lambda t: -t[1])
        if gj:
            gfig = go.Figure()
            gfig.add_trace(go.Bar(name="일반전형 경쟁률", y=[t[0] for t in gj],
                                  x=[t[1] for t in gj], orientation="h", marker_color=MUTED))
            gfig.add_trace(go.Bar(name="사회배려전형 경쟁률", y=[t[0] for t in gj],
                                  x=[t[2] for t in gj], orientation="h", marker_color=TEAL))
            gfig.update_layout(barmode="group", height=300,
                               xaxis_title="경쟁률 (N:1, 낮을수록 유리)",
                               margin=dict(l=10, r=10, t=10, b=40),
                               plot_bgcolor="white", font=dict(family="Pretendard"))
            st.plotly_chart(gfig, width="stretch")
        st.caption("사회배려(장애·보훈·취업지원)는 ‘직무’가 아니라 지원 ‘전형’이에요. "
                   "셋은 법적으로 다른 집단이라, 실제 지원 가능 여부는 공고를 확인하세요.")

    with st.expander("어떤 데이터를 어디까지 가지고 있나요? (커버리지)"):
        cov = ds["coverage"]
        INSTS = ["부산교통공사", "부산도시공사", "부산관광공사", "부산환경공단", "부산시설공단"]
        rows_cov = [("경쟁률", cov["경쟁률"]["기관"]),
                    ("필기 합격선", cov["합격선"]["기관"]),
                    ("신규채용 규모", cov["신규채용규모"]["기관"]),
                    ("채용정보", cov["채용정보"]["기관"])]
        head = "<tr><th style='text-align:left;padding:.3rem .6rem'>데이터</th>" + \
               "".join(f"<th style='padding:.3rem .5rem'>{i.replace('부산','')}</th>" for i in INSTS) + "</tr>"
        body = ""
        for name, have in rows_cov:
            cells = "".join(
                (f"<td style='text-align:center;color:{GOOD};font-weight:700'>●</td>" if i in have
                 else "<td style='text-align:center;color:#cfd8e0'>○</td>") for i in INSTS)
            body += f"<tr><td style='padding:.3rem .6rem'>{name}</td>{cells}</tr>"
        st.markdown(f"<table style='border-collapse:collapse;font-size:.86rem'>{head}{body}</table>",
                    unsafe_allow_html=True)
        st.caption("● 있음 / ○ 없음. 경쟁률·합격선은 교통·도시 2기관만 있어요.")

    with st.expander("직무 자동분류, 믿어도 되나요? (전수검수)"):
        v = ds["meta"]["검증표"]
        st.markdown(f"직무 분류는 키워드 기반이라 오분류 위험이 있어, 전체 "
                    f"**{v['전수검수행']}건을 검증표로 전수 공개**하고 있어요. "
                    f"사람이 바로잡은 정정값이 있으면 자동분류보다 **우선 적용**돼요 "
                    f"(현재 정정 적용 **{v['정정적용']}건**).")
        st.caption("키워드가 둘 이상 겹치는 모호 케이스(예: '공무직 채용(전기설비 유지보수)')는 "
                   "검증표에서 따로 검토해요. 분류 근거를 숨기지 않는 게 핵심이에요.")

    with st.expander("필기시험 합격선 (과거 합격자 평균 점수)"):
        st.markdown("공기업 필기는 100점 만점이지만 **구성이 직무·기관마다 달라요** "
                    "(예: 부교공 운영직 = NCS+일반상식 / 기술직 = NCS+전공시험). "
                    "그래서 합격선도 **기관별로 따로** 봐야 해요. 아래는 과거 합격자들의 "
                    "필기 평균 점수예요(이 점수 근처면 합격권이었다는 뜻).")
        cc = st.columns(len(cs["기관별"]))
        for col_, (inst, dd) in zip(cc, cs["기관별"].items()):
            col_.metric(inst.replace("부산", ""), f"{dd['평균']}점",
                        help=f"표본 {dd['n']}건 · 점수 편차 ±{dd['표준편차']}점")
        st.info("두 기관을 **하나의 평균으로 합치지 않았어요.** 시험 과목이 달라서 합치면 "
                "통계적으로 무의미한 숫자(착시)가 돼요. **지원할 기관 칸만 보면 됩니다.**")

    with st.expander("신규채용 추세"):
        tfig = go.Figure()
        for inst, rows in ds["hire_trend"].items():
            tfig.add_trace(go.Scatter(x=[r["연도"] for r in rows],
                                      y=[r["정규직일반"] for r in rows],
                                      mode="lines+markers", name=inst))
        tfig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10),
                           plot_bgcolor="white", font=dict(family="Pretendard"))
        st.plotly_chart(tfig, width="stretch")
        st.caption("당해연도 규모는 각 기관 공고로 다시 확인하세요.")

# ════════════════ 탭 3: 더보기 ════════════════
with tab3:
    st.caption("⚠️ 여기는 '특정 공고 하나'를 기준으로 한 계산기 모음이에요. "
               "탭1의 전체 추천과는 별개고, 공고가 바뀌면 값도 달라져요.")
    sub1, sub2, sub3 = st.tabs(["🎓 청년인턴 점수", "🏢 정규직 가산 계산", "📋 관광공사 계약직 체커"])

    with sub1:
        st.markdown('<div class="sect">청년인턴 서류 점수 계산기</div>', unsafe_allow_html=True)
        st.markdown("부산교통공사 청년인턴 지원 시, **내가 가진 자격증·가산점으로 서류 정량점수가 "
                    "몇 점인지(55점 만점)** 자동 계산하고, **뭘 더 따면 몇 점 오르는지**까지 알려줘요.")
        st.caption("출처: 부산교통공사 제2026-245호 공고에 명시된 배점만 계산해요. "
                   "정량 55점 = IT(20) + 사무(20) + 한국사(15). 항목 안에서는 가장 높은 자격 1개만 인정돼요.")
        have_certs = set(student.get("보유자격", []))
        quant = sc.intern_quant_score(student.get("보유자격", []))
        bonus = sc.bonus_points(student.get("가산", {}), stage_max=100)
        res = sc.residency_ok(student.get("거주지", ""))

        c1, c2, c3 = st.columns(3)
        c1.metric("내 정량 점수", f"{quant['정량점수']} / {quant['만점']}점",
                  help="IT+사무+한국사 합산(항목별 최고 1개). 정성평가 45점은 별도예요.")
        c2.metric("정량 달성률", f"{int(100*quant['정량점수']/quant['만점'])}%")
        c3.metric("가산 비율", f"+{bonus['가산비율']}%",
                  help="취업지원대상자·장애인 가산(단계별 점수에 적용).")
        st.progress(quant['정량점수'] / quant['만점'])

        CAT_MAX = {"IT": 20, "사무": 20, "한국사": 15}
        st.markdown("**항목별 현황 & 다음에 따면 좋은 자격**")
        for item, table in sc.INTERN_CERT_TABLE.items():
            cur = quant["세부"][item]["점수"]
            cur_cert = quant["세부"][item]["자격"]
            cur_txt = f"{cur_cert} {cur}점" if cur_cert else "해당 자격증 없음 (0점)"
            ups = sorted(((c, p) for c, p in table.items()
                          if c not in have_certs and p > cur), key=lambda t: t[1])
            if cur >= CAT_MAX[item]:
                tip = "✅ 이 항목은 만점이에요."
            elif ups:
                tip = "더 받으려면 → " + " / ".join(f"**{c}**(+{p-cur})" for c, p in ups)
            else:
                tip = "더 올릴 자격이 없어요(이미 최고점이거나 해당 없음)."
            st.markdown(f"- **{item}** (만점 {CAT_MAX[item]}): 현재 {cur_txt}  \n  {tip}")

        if bonus["근거"]:
            st.markdown("**가산점 근거**: " + " / ".join(bonus["근거"]))
        if not res["충족"]:
            st.warning("📍 거주지 요건: " + res["설명"])
        else:
            st.success("📍 거주지 요건 충족 — 부산·울산·경남 거주(또는 합산 36개월)")
        st.caption("자기소개서 정성평가(45점)는 사람이 평가하는 거라 자동 계산이 안 돼요. "
                   "정량에서 최대한 벌어두는 게 유리해요.")

    with sub2:
        st.markdown('<div class="sect">정규직 필기 가산점 계산기</div>', unsafe_allow_html=True)
        st.markdown("정규직 필기시험에서 **내 자격증·가산 자격으로 몇 % 가산점을 받는지** 계산해줘요. "
                    "예를 들어 전기기사가 있으면 필기 만점의 몇 %를 더 받는 식이에요. "
                    "**기관마다 가점율이 달라서**, 기관을 바꿔 비교할 수 있어요.")
        st.caption("출처: 교통공사 제2025-186호 / 시설공단 제2024-98호의 검증된 가점 규칙. "
                   "합격 예측이 아니라 '필기 만점 대비 더 받는 점수 비율'이에요.")
        inst = st.radio("어느 기관 기준으로 볼까요? (가점율이 달라요)",
                        ["부산교통공사", "부산시설공단"], horizontal=True, key="reg_inst")
        reg_track = st.selectbox("지원할 직무", [j for j in rc.TRACK_PREP if j != "청년인턴"],
                                 index=([j for j in rc.TRACK_PREP if j != "청년인턴"]
                                        .index(recs[0]["직무"])
                                        if recs[0]["직무"] in rc.TRACK_PREP else 0),
                                 key="reg_track")
        reg = sc.regular_bonus_score(reg_track, student.get("보유자격", []),
                                     student.get("가산", {}), institution=inst)
        c1, c2 = st.columns([1, 2])
        c1.metric("내 필기 가산 비율", f"+{reg['가산비율']}%",
                  help="필기시험 만점 대비 이 비율만큼 점수를 더 받아요.")
        with c2:
            if reg["가산비율"] > 0:
                st.markdown("**적용 내역**: " + " + ".join(reg["근거"]))
            else:
                st.markdown("**가산 0% — 사이트 오류가 아니에요.** 아래 자격/전형 중 "
                            "**아직 가진 게 없다**는 뜻이에요. 따면 바로 가산이 붙어요.")
        # [개선] 0%일 때 침묵하지 않고 '뭘 따면 몇 % 붙는지' 카탈로그를 펼쳐 보여준다.
        cat = sc.regular_bonus_catalog(reg_track, inst)
        with st.expander(f"💡 {inst.replace('부산','')} {reg_track} — 가산 받을 수 있는 자격/전형 보기",
                         expanded=(reg["가산비율"] == 0)):
            if cat["해당직렬자격"]:
                st.markdown("**이 직무에서 인정되는 자격** (가장 직접적)")
                for it in cat["해당직렬자격"]:
                    st.markdown(f"- {it['자격']} → {it['가산']}")
            if cat["전직렬자격"]:
                st.markdown("**직무 무관 전문자격**")
                st.markdown(" / ".join(f"{it['자격']} {it['가산']}" for it in cat["전직렬자격"]))
            st.markdown("**전형 가산**")
            for it in cat["전형가산"]:
                st.markdown(f"- {it['항목']} → {it['가산']}")
            st.caption(cat["안내"])
        if inst == "부산교통공사" and student.get("가산", {}).get("장애인"):
            st.info("참고: 같은 장애인 가점도 교통공사 5% vs 시설공단 3%로 달라요. "
                    "위에서 기관을 바꿔 비교해 보세요.")
        st.caption(reg["주의"])

    with sub3:
        P = sc.TOURISM_CONTRACT_2026_42
        st.markdown(f'<div class="sect">관광공사 계약직 지원 가능 여부 체커</div>', unsafe_allow_html=True)
        st.markdown(f"부산관광공사 계약직 공고({P['공고']})는 **분야마다 요구하는 어학 점수가 "
                    f"달라요.** 내 어학 점수로 **어느 분야에 지원할 수 있는지** 바로 확인해줘요. "
                    f"공고에 적힌 점수 기준을 그대로 써서 정확하게 판정해요.")
        st.caption(f"{P['고용형태']} · 계약 {P['계약기간']} · 총 {P['총원']}명 모집 · 블라인드 채용")
        with st.expander("❓ ‘공통응시자격’이 뭔가요? (어학요건 없는 분야는 이것만 보면 적격)"):
            st.markdown(
                "어학요건이 따로 없는 분야는 **공통응시자격만 충족하면 지원할 수 있어요.** "
                "공공기관 블라인드 계약직의 공통응시자격은 보통 이런 항목들이에요:")
            st.markdown(
                "- 학력·전공·연령 **제한 없음** (단, 정년 미만 / 임용예정일부터 즉시 근무 가능)\n"
                "- 성별 무관 (남성은 병역을 마쳤거나 면제된 자)\n"
                "- 해당 기관 인사규정상 **결격사유가 없는 자**\n"
                "- (공고에 따라) 부산 거주 요건·우대가 붙기도 함")
            st.caption("⚠️ 위는 공공기관 일반 기준이에요. 정확한 항목은 반드시 해당 공고문의 "
                       "‘공통응시자격’란을 확인하세요(공고마다 조금씩 달라요).")
        lang_raw = student.get("어학원본", {})
        if not lang_raw:
            st.warning("👈 왼쪽 사이드바에서 어학 점수를 넣고 ‘추천 받기’를 누르면, "
                       "분야별로 지원 가능한지 표시돼요. (어학요건 없는 분야는 지금도 지원 가능)")
        for field in P["분야"]:
            r = sc.field_eligibility(P, field, lang_raw)
            req_txt = _fmt_req(r["어학요건"])
            if not lang_raw and r["어학요건"]:
                badge, c = "어학 점수 입력 필요", MUTED
            elif r["어학"]["적격"]:
                badge, c = "✅ 지원 가능", GOOD
            else:
                badge, c = "❌ 어학 미달", BAD
            st.markdown(f"""
            <div class="card" style="padding:1rem 1.2rem">
              <div class="sc"><div class="v" style="font-size:1rem;color:{c}">{badge}</div></div>
              <div class="nm" style="font-size:1.05rem">{field}</div>
              <div class="muted">선발 {r['인원']}명 · 근무지 {r['근무지']}</div>
              <div class="facts">🗣 필요 어학: {req_txt}<br>▸ {r['어학']['사유']}</div>
            </div>
            """, unsafe_allow_html=True)
        st.divider()
        st.markdown("**면접에서 가산점이 어떤 도움이 되나요?**")
        sim_base = sc.interview_score_bto_contract(70, {})        # 가산 없는 기준선
        sim_user = sc.interview_score_bto_contract(70, student.get("가산", {}))
        has_bonus = sim_user["가산점적용"] > 0
        if has_bonus:
            st.success(
                f"내가 면접에서 **70점(합격 컷)**을 맞았을 때, "
                f"가산점 **+{sim_user['가산점적용']}점**이 더해져 "
                f"**{sim_user['최종점수']}점**이 돼요. "
                f"같은 70점 받은 일반 지원자({sim_base['최종점수']}점)보다 "
                f"정렬 순위가 더 높아져요 — 경쟁자가 같은 원점수여도 내가 앞서요.")
            st.markdown(f"**적용 가산점**: {' / '.join(sim_user['가산근거'])}")
            st.caption("70점 컷은 면접 원점수 기준. 가산점은 컷을 낮추는 게 아니라 "
                       "합격자 간 정렬 순위를 올려줘요. 최종 선발은 가점 포함 고득점순이에요.")
        else:
            st.info(
                "현재 입력된 정보로는 이 공고에서 적용되는 가산점이 없어요. "
                "(이 공고는 취업지원대상자만 가산점이 있고, 장애인 가산은 없어요.) "
                "왼쪽 '취업지원·장애 전형 해당자만' 항목에서 해당되는 게 있으면 체크해보세요.")
            st.caption("70점 이상이면 합격 컷 통과, 이후 고득점순으로 최종 선발해요.")
