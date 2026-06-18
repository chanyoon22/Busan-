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

st.set_page_config(page_title="부산 공공기관 커리어 로드맵",
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

  /* 헤더 */
  .hd h1 {{ font-size:1.55rem; font-weight:800; margin:0; letter-spacing:-.02em; }}
  .hd p  {{ color:{MUTED}; margin:.3rem 0 0; font-size:.95rem; }}

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
  <h1>🧭 부산 공공기관 커리어 로드맵</h1>
  <p>내 전공으로 어디가 그나마 덜 치열하고, 졸업까지 뭘 준비하면 되는지 알려드려요.</p>
</div>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def get_dataset():
    return bd.build_dataset()

ds = get_dataset()


# ── 신호등: 경쟁률을 '여유/보통/치열'로 ──
def signal(ratio):
    """경쟁률 → (라벨, 색, 쉬운 설명)"""
    if not ratio:
        return ("데이터 적음", MUTED, "표본이 적어요")
    if ratio <= 15:
        return ("여유", GOOD, f"평균 {round(ratio)}명 중 1명")
    if ratio <= 50:
        return ("보통", WARN, f"평균 {round(ratio)}명 중 1명")
    return ("치열", BAD, f"평균 {round(ratio)}명 중 1명")


def short_target(roadmap_target: str) -> str:
    """'필기 기준선 66점 + 버퍼 2점 → 68점 목표' → '필기 68점 목표'."""
    import re
    m = re.search(r"(\d+)점 목표", roadmap_target)
    return f"필기 {m.group(1)}점 목표" if m else roadmap_target


def short_lang(lang_msg) -> str:
    """'공고상 토익 최저 700점 사례 확인됨 (현재 700 — 충족)' → '토익 700 이상 (충족)'."""
    if not lang_msg:
        return ""
    import re
    m = re.search(r"토익 최저 (\d+)", lang_msg)
    base = f"토익 {m.group(1)} 이상" if m else "어학 요건 있음"
    if "충족" in lang_msg and "부족" not in lang_msg:
        return base + " · 충족"
    if "부족" in lang_msg:
        g = re.search(r"(\d+)점 부족", lang_msg)
        return base + (f" · {g.group(1)}점 부족" if g else " · 부족")
    return base


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

        st.markdown("**어학 점수** (있으면)")
        lang_test = st.selectbox("시험", sc.LANG_TESTS)
        lang_val = st.text_input("점수/등급 (예: 토익 780)", value="")

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
    lang_scores = {lang_test: lang_val} if lang_val.strip() else {}
    lsum = sc.lang_summary(lang_scores)
    st.session_state.student = dict(
        학년=grade, 전공계열=major, 보유자격=certs,
        어학={"토익": lsum["토익등가"]},
        어학상세=lsum, 어학원본=lang_scores, 거주지=region,
        사회배려=bool(social_v or disabled),
        가산={"취업지원대상자": social_v, "장애인": disabled})
    st.session_state.weights = weights
    st.session_state.recs = rc.recommend(st.session_state.student, weights=weights, ds=ds)
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
          <div class="big">{top['직무']} — 경쟁 {lbl} ({desc})</div>
          <div class="sub">{major} {grade}학년 기준 · 다음 할 일: {short_target(top['로드맵']['필기목표'])}</div>
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

        st.markdown(f"""
        <div class="card">
          <div class="sc"><div class="v">{r['적합도']}</div><div class="u">추천 점수</div></div>
          <div class="rk">{i}순위</div>
          <div class="nm">{r['직무']}</div>
          <span class="signal sig-{lbl}">
            <span class="dot" style="background:{col}"></span>경쟁 {lbl} · {desc}</span>
          {why_high}
          <div>{tags}</div>
          <div class="facts">
            🎯 <b>{short_target(r['로드맵']['필기목표'])}</b><br>
            🎓 준비할 자격: {certs_txt}
            {('<br>🗣 ' + lang_txt) if lang_txt else ''}
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(f"왜 {i}순위인지 · 더 자세히"):
            w = st.session_state.weights
            cut = (f"평균 합격선 {d['합격선평균']}점 (±{d['합격선표준편차']})"
                   if d["합격선평균"] else "합격선 공시 없음")
            if d["합격선평균"] and len(d.get("합격선기관", [])) > 1:
                cut += " · 기관마다 시험이 달라 참고용"
            st.markdown(
                f"**점수 계산**\n"
                f"- 전공 맞춤 {int(comp['전공적합']*100)}% × {w['fit']:.0%}"
                f"{' (블라인드라 모든 전공 100%)' if r['블라인드'] else ''}\n"
                f"- 경쟁 여유 {int(comp['경쟁여유']*100)}% × {w['comp']:.0%} "
                f"— 경쟁률 {d['일반경쟁률']}:1 (낮을수록 ↑)\n"
                f"- 데이터 충분한 정도 {int(comp['표본량']*100)}% × {w['size']:.0%}\n"
                f"- 합쳐서 → **추천 점수 {r['적합도']}점**\n\n"
                f"**합격선**: {cut}")
            if r["로드맵"]["블라인드안내"]:
                st.info(r["로드맵"]["블라인드안내"])
            if r["로드맵"]["사회배려안내"]:
                st.warning(r["로드맵"]["사회배려안내"])

    if not recs:
        st.stop()

    st.write("")
    # ── 다음 할 일 체크리스트 (접어둠) ──
    with st.expander("✅ 다음에 할 일 체크리스트 (1순위 기준)"):
        st.caption("체크는 이 화면에서만 기억돼요(새로고침하면 초기화).")
        steps = []
        for c in recs[0]["로드맵"]["취득권장자격"]:
            if c != "보유 자격으로 충분":
                steps.append(("자격", f"{c} 따기"))
        if recs[0]["로드맵"]["어학"]:
            steps.append(("어학", short_lang(recs[0]["로드맵"]["어학"])))
        steps.append(("필기", short_target(recs[0]["로드맵"]["필기목표"])))

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

    # ── AI 요약 (접어둠, 동의 버튼식) ──
    with st.expander("🤖 AI에게 요약 듣기 (선택 · 외부 전송)"):
        st.caption("위 추천을 AI가 문장으로 정리해줘요. 핵심은 이미 위에 다 있어요.")
        st.warning("버튼을 누르면 내 정보가 외부 AI(Gemini)로 전송됩니다.")
        if st.button("동의하고 AI 요약 생성", width="stretch"):
            with st.spinner("정리 중…"):
                st.session_state.ai_roadmap = ai.narrate_roadmap(student, recs, ds)
        if st.session_state.get("ai_roadmap"):
            st.info(st.session_state.ai_roadmap)

        st.divider()
        st.caption('AI에게 직접 묻기 — 추천에 없는 직무도 물어보세요. '
                   '예: "전기직 경쟁률은?" / "기계직 합격선은?"')
        if "chat" not in st.session_state:
            st.session_state.chat = []
        for role, msg in st.session_state.chat:
            with st.chat_message(role):
                st.write(msg)
        if q := st.chat_input("질문 (전송 시 외부 AI로 전송)"):
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

    st.markdown("**직무별 경쟁률** (낮을수록 들어가기 쉬움)")
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
    with st.expander("일반 vs 사회배려 전형 차이 보기"):
        gj = [(j, s["일반_가중경쟁률"], s["사회배려_가중경쟁률"])
              for j, s in ds["job_stats"].items()
              if s["일반_가중경쟁률"] and s["사회배려_가중경쟁률"]]
        gj.sort(key=lambda t: -t[1])
        if gj:
            gfig = go.Figure()
            gfig.add_trace(go.Bar(name="일반", y=[t[0] for t in gj],
                                  x=[t[1] for t in gj], orientation="h", marker_color=MUTED))
            gfig.add_trace(go.Bar(name="사회배려", y=[t[0] for t in gj],
                                  x=[t[2] for t in gj], orientation="h", marker_color=TEAL))
            gfig.update_layout(barmode="group", height=300,
                               margin=dict(l=10, r=10, t=10, b=10),
                               plot_bgcolor="white", font=dict(family="Pretendard"))
            st.plotly_chart(gfig, width="stretch")
        st.caption("사회배려(장애·보훈·취업지원)는 ‘직무’가 아니라 ‘전형’이에요. "
                   "단, 셋은 법적으로 다른 집단이니 실제 지원 가능 여부는 공고를 확인하세요.")

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

    with st.expander("필기 합격선 (기관별)"):
        cc = st.columns(len(cs["기관별"]) + 1)
        for col_, (inst, dd) in zip(cc, cs["기관별"].items()):
            col_.metric(inst.replace("부산", ""), f"{dd['평균']}점",
                        help=f"n={dd['n']} · ±{dd['표준편차']}")
        cc[-1].metric("혼합 평균", f"{cs['전체평균']}점", help="참고용. 직접 비교 금지")
        st.caption("기관마다 시험 과목이 달라서, 합격선을 직접 비교하면 안 돼요.")

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
    st.caption("⚠️ 여기는 특정 공고 기준 계산기예요. 핵심 추천(탭1)과는 별개고, "
               "공고가 바뀌면 값도 달라져요.")
    sub1, sub2 = st.tabs(["🎓 청년인턴 점수", "📋 관광공사 계약직 체커"])

    with sub1:
        st.markdown('<div class="sect">청년인턴 서류 점수 계산기</div>', unsafe_allow_html=True)
        st.caption("출처: 부산교통공사 제2026-245호 공고 (명시된 범위만 계산)")
        quant = sc.intern_quant_score(student.get("보유자격", []))
        bonus = sc.bonus_points(student.get("가산", {}), stage_max=100)
        res = sc.residency_ok(student.get("거주지", ""))
        c1, c2, c3 = st.columns(3)
        c1.metric("자격증 점수", f"{quant['정량점수']} / {quant['만점']}")
        c2.metric("가산 비율", f"+{bonus['가산비율']}%")
        c3.metric("거주지", "충족" if res["충족"] else "미충족")
        for item, dd in quant["세부"].items():
            st.markdown(f"- **{item}**: {dd['자격'] or '없음'} → {dd['점수']}점")
        if bonus["근거"]:
            st.markdown("**가산점**: " + " / ".join(bonus["근거"]))
        if not res["충족"]:
            st.warning(res["설명"])
        st.caption("자기소개서 정성평가(45점)는 자동 계산이 안 돼요. 위는 ‘내가 바꿀 수 있는 부분’이에요.")

    with sub2:
        P = sc.TOURISM_CONTRACT_2026_42
        st.markdown(f'<div class="sect">{P["공고"]}</div>', unsafe_allow_html=True)
        st.caption(f"{P['고용형태']} · 계약 {P['계약기간']} · 총 {P['총원']}명")
        st.caption("환산표로 추정하지 않고, 공고에 적힌 시험별 컷으로 직접 판정해요.")
        lang_raw = student.get("어학원본", {})
        if not lang_raw:
            st.warning("왼쪽에서 어학 점수를 넣으면 분야별 가능 여부가 나와요.")
        for field in P["분야"]:
            r = sc.field_eligibility(P, field, lang_raw)
            req_txt = _fmt_req(r["어학요건"])
            if not lang_raw and r["어학요건"]:
                badge, c = "어학 입력 필요", MUTED
            elif r["어학"]["적격"]:
                badge, c = "지원 가능", GOOD
            else:
                badge, c = "어학 미달", BAD
            st.markdown(f"""
            <div class="card" style="padding:1rem 1.2rem">
              <div class="sc"><div class="v" style="font-size:1rem;color:{c}">{badge}</div></div>
              <div class="nm" style="font-size:1.05rem">{field}</div>
              <div class="muted">선발 {r['인원']}명 · {r['근무지']}</div>
              <div class="facts">🗣 {req_txt}<br>▸ {r['어학']['사유']}</div>
            </div>
            """, unsafe_allow_html=True)
        st.divider()
        st.markdown("**면접 점수 시뮬** (원점수는 직접 가정 — 예측 아님)")
        raw = st.number_input("예상 면접 점수 (0~100)", 0, 100, 72, 1)
        sim = sc.interview_score_bto_contract(raw, student.get("가산", {}))
        s1, s2, s3 = st.columns(3)
        s1.metric("원점수", f"{sim['면접원점수']}")
        s2.metric("가점", f"+{sim['가산점적용']}")
        s3.metric("70점 컷", "통과" if sim["컷통과"] else "미달")
        st.caption(sim["주의"])
