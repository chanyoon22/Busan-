"""
app.py — 부산 공공기관 커리어 로드맵 내비게이터 (v3 · 3탭 재설계)
================================================================
v2(6탭) → v3(3탭) 재설계 핵심
  [정체성] 제품을 '정규직 로드맵 / 데이터분석 / AI상담 / 인턴점수 / 계약직체커 /
    데이터품질'의 6개 동급 기능으로 흩어 놓던 구조를 정리. 제품의 본체는
    '내 전공 기준 준비 우선순위 로드맵'(탭1) 하나로 수렴한다.
      · 탭1 내 로드맵      = 사용자 가치 (핵심, 화면의 70%)
      · 탭2 추천 근거·품질  = 심사 방어 (경쟁률 차트 + 데이터 커버리지·합격선 한계)
      · 탭3 더보기(부가도구) = 청년인턴 점수 + 관광 계약직 체커 (별도 공고 기반 계산기)

  [가독성] 처음 들어온 1학년이 "뭐부터 눌러야 하지"를 겪지 않도록
    첫 화면에 ①입력→②확인→③근거 3단계 안내 + '예측 아님' 한 줄을 고정.

  [개인정보] 탭1 AI 로드맵이 자동으로 Gemini를 호출하던 흐름을 제거.
    '동의하고 생성' 버튼을 눌렀을 때만 외부 API로 전송된다(고지와 동작 일치).
    AI 상담은 별도 탭이 아니라 탭1 안의 선택 기능으로 내렸다.

  [정직성] Streamlit은 서버에서 계산하는 구조라, 안내 문구를 '브라우저 안에서만'
    → '서버 세션 안에서만(외부 AI로는 전송 안 함)'으로 정정.

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

INK, PRIMARY, ACCENT = "#0f2438", "#0e7c86", "#f06543"
GOOD, WARN, BAD, MUTED = "#2e9e6b", "#e0a800", "#d9534f", "#5b7185"

st.markdown(f"""
<style>
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
  html, body, [class*="css"] {{ font-family:'Pretendard',sans-serif; }}
  .main {{ background:#f7f9fb; }}
  .hero {{ border-left:5px solid {ACCENT}; padding:.2rem 0 .2rem 1rem; margin:.2rem 0 .8rem; }}
  .hero h1 {{ color:{INK}; font-size:1.7rem; font-weight:800; margin:0; letter-spacing:-.02em; }}
  .hero p  {{ color:{MUTED}; margin:.35rem 0 0; font-size:.98rem; }}
  .howto {{ background:#fff; border:1px solid #e6edf3; border-radius:14px;
            padding:.9rem 1.1rem; margin:.2rem 0 1rem;
            box-shadow:0 1px 3px rgba(15,36,56,.05); }}
  .howto .step {{ display:inline-block; min-width:1.4rem; height:1.4rem; line-height:1.4rem;
                  text-align:center; background:{PRIMARY}; color:#fff; border-radius:50%;
                  font-weight:800; font-size:.82rem; margin-right:.45rem; }}
  .howto .row {{ font-size:.95rem; color:{INK}; margin:.25rem 0; }}
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
  .secthead {{ font-size:1.05rem; font-weight:800; color:{INK}; margin:.2rem 0 .1rem; }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="hero">
  <h1>🧭 부산 공공기관 커리어 로드맵</h1>
  <p>부산 공공기관 채용 공시데이터로,
     <b>내 전공에 데이터상 유리한 직무와 졸업까지 준비 순서</b>를 정리해 줍니다.</p>
</div>
""", unsafe_allow_html=True)

# 1학년도 바로 이해하도록 — 3단계 사용법 + '예측 아님' 한 줄을 첫 화면에 고정
st.markdown(f"""
<div class="howto">
  <div class="row"><span class="step">1</span>왼쪽 사이드바에서 <b>학년·전공·자격·어학</b>을 입력하고 ‘제출’을 누르세요.</div>
  <div class="row"><span class="step">2</span><b>‘내 로드맵’ 탭</b>에서 추천 직무 Top 3와 다음에 할 일을 확인하세요.</div>
  <div class="row"><span class="step">3</span>근거가 궁금하면 <b>‘추천 근거·데이터 품질’ 탭</b>에서 실제 공시데이터 범위를 보세요.</div>
  <div style="margin-top:.55rem;color:{ACCENT};font-size:.86rem;font-weight:700">
    ※ 이 서비스는 합격 가능성을 예측하지 않습니다. 과거 공시데이터로 <u>준비 우선순위</u>를 정리하는 참고 도구입니다.
  </div>
</div>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def get_dataset():
    return bd.build_dataset()

ds = get_dataset()


def class_color(c):
    return {"과경쟁": BAD, "미달위험": WARN, "적정": GOOD}.get(c, MUTED)


def _fmt_req(req: dict) -> str:
    """공고 어학요건 dict → 사람이 읽는 'OR' 문자열."""
    if not req:
        return "별도 어학요건 없음(공통응시자격만)"
    parts = []
    if req.get("TOEIC"):     parts.append(f"TOEIC {req['TOEIC']}")
    if req.get("TOEFL_iBT"): parts.append(f"TOEFL(iBT) {req['TOEFL_iBT']}")
    if req.get("TEPS_new"):  parts.append(f"New TEPS {req['TEPS_new']}")
    if req.get("TOEIC_S"):   parts.append(f"TOEIC S {req['TOEIC_S']}")
    if req.get("OPIc"):      parts.append(f"OPIc {req['OPIc']}")
    return " / ".join(parts) + " 중 1개 이상"


# ───────────────────── 사이드바: 프로필 + 가중치 (st.form) ─────────────────────
with st.sidebar:
    st.subheader("내 프로필")
    st.caption("입력 후 아래 ‘제출’을 눌러야 추천이 계산됩니다.")
    with st.form("profile"):
        grade = st.select_slider("학년", options=[1, 2, 3, 4], value=2)
        major = st.selectbox("전공계열", list(rc.MAJOR_FIT.keys()),
                             index=len(rc.MAJOR_FIT) - 1)
        certs = st.multiselect("보유 자격증 (없으면 비워두세요)", sc.CERT_MASTER)

        st.markdown("**어학 성적** (있는 것만)")
        lang_test = st.selectbox("시험 종류", sc.LANG_TESTS)
        lang_val = st.text_input("점수/등급 (예: 토익 780, 오픽 IH)", value="")

        st.markdown("**거주지(주민등록 기준)**")
        region = st.selectbox("현재 주민등록 지역", sc.RESIDENCY_REGIONS)

        with st.expander("사회배려 전형 해당자만 (선택)"):
            social_v = st.selectbox("취업지원대상자 가점", [0, 5, 10],
                                    help="국가보훈부 증명서 비율(없으면 0)")
            disabled = st.checkbox("장애인 등록")

        with st.expander("추천 기준 직접 조절 (선택 · 기본값 권장)"):
            w_fit = st.slider("전공 적합", 0.0, 1.0, 0.45, 0.05)
            w_comp = st.slider("경쟁 여유", 0.0, 1.0, 0.35, 0.05)
            w_size = st.slider("데이터 표본량(신뢰도)", 0.0, 1.0, 0.20, 0.05,
                               help="실제 채용 인원 크기가 아니라, 그 직무의 경쟁률 추정에 쓰인 "
                                    "데이터 레코드 수입니다. 많을수록 추정이 안정적입니다.")

        submitted = st.form_submit_button("프로필 제출 / 다시 계산", width="stretch")
    st.caption("🔒 입력값(장애·취업지원대상자 등 민감정보 포함)은 추천·점수 계산 시 "
               "서버 세션 안에서만 처리되며, 외부로 전송되지 않습니다. "
               "단, ‘내 로드맵’ 탭에서 **‘AI 요약’ 버튼을 직접 누른 경우에만** "
               "프로필이 외부 생성형 AI(Gemini)로 전송됩니다.")

# 제출 전이면 기본 프로필로 1회만 계산(초기 화면용), 제출 시 갱신
if submitted or "student" not in st.session_state:
    tot = (w_fit + w_comp + w_size) or 1.0
    weights = dict(fit=w_fit/tot, comp=w_comp/tot, size=w_size/tot)
    lang_scores = {lang_test: lang_val} if lang_val.strip() else {}
    lsum = sc.lang_summary(lang_scores)
    st.session_state.student = dict(
        학년=grade, 전공계열=major, 보유자격=certs,
        어학={"토익": lsum["토익등가"]},     # 추천 엔진 호환용(다종→토익등가)
        어학상세=lsum, 어학원본=lang_scores, 거주지=region,
        사회배려=bool(social_v or disabled),
        가산={"취업지원대상자": social_v, "장애인": disabled})
    st.session_state.weights = weights
    st.session_state.recs = rc.recommend(st.session_state.student, weights=weights, ds=ds)
    st.session_state.pop("ai_roadmap", None)   # 프로필 바뀌면 이전 AI 요약 무효화

student = st.session_state.student
recs = st.session_state.recs

tab1, tab2, tab3 = st.tabs(
    ["🎯 내 로드맵", "📊 추천 근거·데이터 품질", "🧰 더보기 (공고·인턴 도구)"])

# ════════════════════════ 탭 1: 내 로드맵 (제품 본체) ════════════════════════
with tab1:
    c1, c2 = st.columns([3, 2])

    # ── 왼쪽: 추천 직무 카드 ──
    with c1:
        st.markdown('<div class="secthead">데이터가 추천하는 직무 (내 전공 지원범위 내)</div>',
                    unsafe_allow_html=True)
        st.caption("‘데이터 유리도’ = 전공적합 + 경쟁여유 + 표본량을 합친 **준비 우선순위 점수**"
                   "입니다. 합격 가능성·예측이 아닙니다.")
        if not recs:
            st.info("선택한 전공계열에 매칭되는 직무 데이터가 없습니다. 다른 전공계열을 선택해 보세요.")
        for i, r in enumerate(recs, 1):
            comp = r["구성"]
            d = r["데이터"]
            blind_tag = ('<span class="tag" style="background:#e7f4f5;color:#0e7c86">블라인드·전공무관</span>'
                         if r["블라인드"] else "")
            social_tag = (f'<span class="tag" style="background:#fde8e1;color:{ACCENT}">사회배려 전형 갭 반영</span>'
                          if r["사회배려적용"] else "")
            cut_txt = (f"평균 합격선 {d['합격선평균']}점 (±{d['합격선표준편차']})"
                       + (f" · {'+'.join(x.replace('부산','') for x in d.get('합격선기관',[]))} 혼합"
                          if len(d.get('합격선기관', [])) > 1 else "")
                       if d['합격선평균'] else "합격선 공시 없음")
            st.markdown(f"""
            <div class="reccard">
              <span class="scorepill">{r['적합도']}</span>
              <div class="rank">{i}순위 · 데이터 유리도(시뮬)</div>
              <div class="track">{r['직무']}</div>
              {blind_tag}{social_tag}
              <div style="margin-top:.6rem;font-size:.82rem;color:{MUTED}">전공적합 {int(comp['전공적합']*100)}%</div>
              <div class="barwrap"><div class="bar" style="width:{int(comp['전공적합']*100)}%"></div></div>
              <div style="font-size:.82rem;color:{MUTED}">경쟁여유 {int(comp['경쟁여유']*100)}% · 일반전형 {d['일반경쟁률']}:1</div>
              <div class="barwrap"><div class="bar" style="width:{int(comp['경쟁여유']*100)}%;background:{ACCENT}"></div></div>
              <div style="font-size:.85rem;color:{INK};margin-top:.5rem">
                📌 {r['로드맵']['필기목표']}<br>
                📊 {cut_txt}<br>
                🎓 취득권장: {', '.join(r['로드맵']['취득권장자격'])}
                {('<br>🗣 ' + r['로드맵']['어학']) if r['로드맵']['어학'] else ''}
              </div>
              {f'<div style="font-size:.8rem;color:{PRIMARY};margin-top:.4rem">ℹ️ {r["로드맵"]["블라인드안내"]}</div>' if r['로드맵']['블라인드안내'] else ''}
              {f'<div style="font-size:.8rem;color:{ACCENT};margin-top:.4rem">★ {r["로드맵"]["사회배려안내"]}</div>' if r['로드맵']['사회배려안내'] else ''}
            </div>
            """, unsafe_allow_html=True)

            # '왜 이 직무가 추천됐나' — 산식 투명 공개(접이식)
            with st.expander(f"왜 ‘{r['직무']}’가 {i}순위인가요? (점수 계산 근거)"):
                w = st.session_state.weights
                st.markdown(
                    f"- **전공적합 {comp['전공적합']:.2f}** × 가중치 {w['fit']:.2f}"
                    f"{' — 블라인드 직무라 모든 전공에 1.00' if r['블라인드'] else ''}\n"
                    f"- **경쟁여유 {comp['경쟁여유']:.2f}** × 가중치 {w['comp']:.2f} "
                    f"— 일반전형 누적 경쟁률 {d['일반경쟁률']}:1 (낮을수록 점수↑)\n"
                    f"- **표본량 {comp['표본량']:.2f}** × 가중치 {w['size']:.2f} "
                    f"— 경쟁률 레코드가 많을수록 추정이 안정적\n"
                    f"- 세 항목 가중합 → **데이터 유리도 {r['적합도']}점**")
                st.caption("가중치는 사이드바 ‘추천 기준 직접 조절’에서 바꿀 수 있습니다. "
                           "이 점수는 준비 우선순위 시뮬레이션이며 합격 예측이 아닙니다.")

        # 1순위 직무 기준 다음 할 일 체크리스트(로드맵의 일부 → 탭1로 통합)
        if recs:
            st.divider()
            st.markdown('<div class="secthead">✅ 다음에 할 일 (1순위 직무 기준)</div>',
                        unsafe_allow_html=True)
            st.caption("세션 체크리스트입니다. 새로고침하면 초기화됩니다(지속 저장은 로그인+DB 필요 — 미구현).")
            top = recs[0]
            steps = []
            for c in top["로드맵"]["취득권장자격"]:
                if c not in ("보유 자격으로 충분",):
                    steps.append(("자격", f"{c} 취득"))
            if top["로드맵"]["어학"]:
                steps.append(("어학", top["로드맵"]["어학"]))
            steps.append(("필기", top["로드맵"]["필기목표"]))

            if "progress" not in st.session_state:
                st.session_state.progress = {}
            done_now = []
            for idx, (kind, label) in enumerate(steps):
                key = f"step_{idx}"
                checked = st.checkbox(f"[{kind}] {label}",
                                      value=st.session_state.progress.get(key, False),
                                      key=f"chk_{idx}")
                st.session_state.progress[key] = checked
                if checked:
                    done_now.append(label)
            nxt = next((s for j, s in enumerate(steps)
                        if not st.session_state.progress.get(f"step_{j}")), None)
            pct = int(100 * len(done_now) / len(steps)) if steps else 0
            st.progress(pct / 100, text=f"준비 진척률 {pct}%")
            if nxt:
                st.success(f"👉 지금 시작할 단계: **{nxt[1]}** ({nxt[0]})")
            else:
                st.success("로드맵 완주! 이제 각 기관 공고 모니터링 단계입니다.")

    # ── 오른쪽: AI 요약 (자동호출 금지, 동의 버튼식) ──
    with c2:
        st.markdown('<div class="secthead">AI 맞춤 로드맵 요약 (선택)</div>',
                    unsafe_allow_html=True)
        st.caption("위 추천 수치를 AI가 문장으로 정리해 줍니다. 핵심 추천은 AI 없이도 "
                   "이미 왼쪽에 다 나와 있습니다.")
        st.warning("🔒 버튼을 누르면 **내 프로필(학년·전공·자격·어학·거주지, 입력 시 "
                   "장애·취업지원 여부)과 추천 결과가 외부 생성형 AI(Gemini)로 전송**됩니다. "
                   "전송을 원치 않으면 누르지 마세요.")

        if st.button("✅ 동의하고 AI 요약 생성", width="stretch"):
            with st.spinner("AI가 추천 근거를 정리하는 중…"):
                st.session_state.ai_roadmap = ai.narrate_roadmap(student, recs, ds)

        if st.session_state.get("ai_roadmap"):
            st.info(st.session_state.ai_roadmap)
            st.caption("AI는 위 공공데이터 수치와 공고 임용조건에만 근거해 서술합니다.")

        st.divider()

        # AI 상담도 별도 탭이 아니라 탭1 안의 선택 기능으로 축소
        with st.expander("💬 추가로 AI에게 직접 질문하기 (선택 · 외부 전송)"):
            st.caption('예: "전기직 일반전형 경쟁률은?" / "사무직 토익 몇 점 필요해?"')
            if "chat" not in st.session_state:
                st.session_state.chat = []
            for role, msg in st.session_state.chat:
                with st.chat_message(role):
                    st.write(msg)
            if q := st.chat_input("질문 입력 (전송 시 외부 AI로 프로필이 전송됩니다)"):
                st.session_state.chat.append(("user", q))
                with st.chat_message("user"):
                    st.write(q)
                with st.chat_message("assistant"):
                    with st.spinner("…"):
                        a = ai.chat(student, recs, q, ds=ds)
                    st.write(a)
                st.session_state.chat.append(("assistant", a))

# ════════════════ 탭 2: 추천 근거·데이터 품질 (심사 방어) ════════════════
with tab2:
    st.markdown('<div class="secthead">이 추천이 어떤 데이터에 근거하는가</div>',
                unsafe_allow_html=True)
    st.info(ds["coverage"]["한줄정정"])

    # (1) 직무별 경쟁률(미스매치)
    st.markdown("**① 직무별 5년 가중 경쟁률 (일반전형)**")
    mm = [m for m in ds["mismatch"] if m["평균경쟁률"]]
    mm.sort(key=lambda m: m["평균경쟁률"])
    fig = go.Figure(go.Bar(
        x=[m["평균경쟁률"] for m in mm], y=[m["직무"] for m in mm], orientation="h",
        marker_color=[class_color(m["분류"]) for m in mm],
        text=[f"{m['평균경쟁률']}:1" for m in mm], textposition="outside"))
    fig.update_layout(
        title="빨강=과경쟁 · 노랑=미달위험 · 초록=적정",
        height=380, margin=dict(l=10, r=40, t=40, b=10),
        plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(fig, width="stretch")

    k1, k2, k3 = st.columns(3)
    cs = ds["cut_stat"]
    k1.metric("경쟁률 레코드", f"{ds['meta']['경쟁률레코드']}건")
    k2.metric("사회배려 전형 가중경쟁률", f"{ds['esg']['가중경쟁률']}:1",
              help=f"표본 {ds['esg']['표본수']}건 · 미달 {ds['esg']['미달건수']}건")
    k3.metric("합격선 통계(혼합·참고용)", f"{cs['전체평균']}±{cs['전체표준편차']}",
              help=f"제공기관 {', '.join(cs['제공기관'])} · n={cs['n']}")

    st.divider()

    # (2) 일반 vs 사회배려 전형 갭
    st.markdown("**② 직무별 일반 vs 사회배려 전형 경쟁률 갭**")
    gj = [(j, s["일반_가중경쟁률"], s["사회배려_가중경쟁률"])
          for j, s in ds["job_stats"].items()
          if s["일반_가중경쟁률"] and s["사회배려_가중경쟁률"]]
    gj.sort(key=lambda t: -t[1])
    if gj:
        gfig = go.Figure()
        gfig.add_trace(go.Bar(name="일반전형", y=[t[0] for t in gj],
                              x=[t[1] for t in gj], orientation="h", marker_color=MUTED))
        gfig.add_trace(go.Bar(name="사회배려전형", y=[t[0] for t in gj],
                              x=[t[2] for t in gj], orientation="h", marker_color=ACCENT))
        gfig.update_layout(barmode="group", height=320,
                           margin=dict(l=10, r=10, t=10, b=10),
                           plot_bgcolor="white", font=dict(family="Pretendard"))
        st.plotly_chart(gfig, width="stretch")
    st.caption("사회배려(장애·보훈·취업지원)는 ‘직무’가 아니라 ‘전형’입니다. "
               "같은 직무라도 사회배려 전형 경쟁률이 크게 낮습니다. "
               "다만 장애·보훈·취업지원은 법적으로 다른 집단이라, 실제 지원 가능 여부는 "
               "공고별 응시자격을 반드시 확인하세요.")

    st.divider()

    # (3) 데이터 커버리지 매트릭스
    st.markdown("**③ 데이터 커버리지 — 무엇을 어느 기관까지 실제로 쓰는가**")
    cov = ds["coverage"]
    INSTS = ["부산교통공사", "부산도시공사", "부산관광공사", "부산환경공단", "부산시설공단"]
    rows_cov = [
        ("경쟁률(직무×전형)", cov["경쟁률"]["기관"]),
        ("필기 합격선",        cov["합격선"]["기관"]),
        ("신규채용 규모/추세",  cov["신규채용규모"]["기관"]),
        ("채용정보(임용조건)",  cov["채용정보"]["기관"]),
    ]
    head = "<tr><th style='text-align:left;padding:.3rem .6rem'>데이터</th>" + \
           "".join(f"<th style='padding:.3rem .6rem'>{i.replace('부산','')}</th>" for i in INSTS) + "</tr>"
    body = ""
    for name, have in rows_cov:
        cells = ""
        for i in INSTS:
            ok = i in have
            cells += (f"<td style='text-align:center;color:{GOOD};font-weight:700'>●</td>" if ok
                      else f"<td style='text-align:center;color:#cfd8e0'>○</td>")
        body += f"<tr><td style='padding:.3rem .6rem;color:{INK}'>{name}</td>{cells}</tr>"
    st.markdown(f"<table style='border-collapse:collapse;font-size:.86rem'>{head}{body}</table>",
                unsafe_allow_html=True)
    st.caption("● 보유 / ○ 없음. 경쟁률·합격선은 교통·도시 2기관에만 있습니다.")

    st.divider()

    # (4) 합격선 기관별 분리(이종 시험 경고)
    st.markdown("**④ 필기 합격선 — 기관별 분리** (시험 구성이 달라 직접 비교 주의)")
    cc = st.columns(len(cs["기관별"]) + 1)
    for col, (inst, dd) in zip(cc, cs["기관별"].items()):
        col.metric(inst.replace("부산", ""), f"{dd['평균']}점",
                   help=f"n={dd['n']} · ±{dd['표준편차']} · 범위 {dd['범위']}")
    cc[-1].metric("혼합 전체평균", f"{cs['전체평균']}점",
                  help="기관 혼합값 — 참고용. 직접 비교 금지.")
    st.warning(cs["주의"])

    st.divider()

    # (5) 직무별 표본량·결측
    st.markdown("**⑤ 직무별 데이터 양** (표본 얕은 직무 정직 표시)")
    jq = []
    for j, s in ds["job_stats"].items():
        jq.append(dict(직무=j, 경쟁률레코드=s["일반_n"],
                       표본신뢰=("낮음" if s["일반_n"] < 5 else "보통" if s["일반_n"] < 10 else "양호")))
    jq.sort(key=lambda d: -d["경쟁률레코드"])
    qfig = go.Figure(go.Bar(
        x=[d["경쟁률레코드"] for d in jq], y=[d["직무"] for d in jq], orientation="h",
        marker_color=[GOOD if d["표본신뢰"] == "양호" else WARN if d["표본신뢰"] == "보통" else BAD for d in jq],
        text=[f'{d["경쟁률레코드"]}건' for d in jq], textposition="outside"))
    qfig.update_layout(title="초록=양호 · 노랑=보통 · 빨강=표본부족(<5건)",
                       height=360, margin=dict(l=10, r=40, t=40, b=10),
                       plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(qfig, width="stretch")

    st.divider()
    st.markdown("**⑥ 신규채용 추세 (정규직 일반)**")
    tfig = go.Figure()
    for inst, rows in ds["hire_trend"].items():
        tfig.add_trace(go.Scatter(x=[r["연도"] for r in rows],
                                  y=[r["정규직일반"] for r in rows],
                                  mode="lines+markers", name=inst))
    tfig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10),
                       plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(tfig, width="stretch")
    st.caption("출처: data.go.kr 신규채용 공시. 5년 누적 구조 경향이며 당해연도 규모는 공고로 재확인.")

# ════════════════ 탭 3: 더보기 — 공고·인턴 부가도구 ════════════════
with tab3:
    st.caption("⚠️ 이 탭은 **특정 공고 기준 계산기**로, 핵심 추천 로드맵(탭1)과는 별도입니다. "
               "공고가 바뀌면 값이 달라질 수 있습니다.")

    sub1, sub2 = st.tabs(["🎓 청년인턴 서류점수", "📋 관광공사 계약직 적격 체커"])

    # ── 청년인턴 서류점수 ──
    with sub1:
        st.markdown('<div class="secthead">청년인턴 서류전형 점수 시뮬레이터</div>',
                    unsafe_allow_html=True)
        st.caption("출처: 부산교통공사 제2026-245호 공고 — 공고가 명시한 정량 가점 범위에서만 계산(추정 아님).")
        quant = sc.intern_quant_score(student.get("보유자격", []))
        bonus = sc.bonus_points(student.get("가산", {}), stage_max=100)
        res = sc.residency_ok(student.get("거주지", ""))

        c1, c2, c3 = st.columns(3)
        c1.metric("정량 점수(자격증)", f"{quant['정량점수']} / {quant['만점']}")
        c2.metric("가산 비율", f"+{bonus['가산비율']}%")
        c3.metric("거주지 요건", "충족" if res["충족"] else "미충족")

        st.markdown("**항목별 정량 득점** (항목 내 최고 자격 1개만 인정)")
        for item, dd in quant["세부"].items():
            label = dd["자격"] or "해당 자격 없음"
            st.markdown(f"- **{item}**: {label} → {dd['점수']}점")
        if bonus["근거"]:
            st.markdown("**가산점 근거**: " + " / ".join(bonus["근거"]))
        if not res["충족"]:
            st.warning(res["설명"])
        st.caption(res["주의"])
        st.info("정성평가(45점: 자기소개·지원동기·직무목표)는 자기소개서 평가라 자동 산출 불가. "
                "위 정량 점수는 ‘내가 통제 가능한 부분’입니다.")

    # ── 관광공사 계약직 적격 체커 ──
    with sub2:
        P = sc.TOURISM_CONTRACT_2026_42
        st.markdown(f'<div class="secthead">{P["공고"]}</div>', unsafe_allow_html=True)
        st.caption(f"출처: {P['출처']} · {P['고용형태']} · 계약 {P['계약기간']} · "
                   f"전형 {P['전형']} · 총 {P['총원']}명")
        st.info("이 체커는 어학을 환산표로 추정하지 않고, **공고가 명시한 분야별 시험 컷**으로 "
                "직접 적격 여부를 판정합니다(같은 TOEIC라도 공고마다 타 시험 컷이 다르기 때문).")

        lang_raw = student.get("어학원본", {})
        if not lang_raw:
            st.warning("사이드바에서 어학 성적을 입력하면 분야별 적격 여부가 자동 판정됩니다.")

        st.markdown("**분야별 적격 판정** (어학요건은 한 시험만 충족해도 됨)")
        for field in P["분야"]:
            r = sc.field_eligibility(P, field, lang_raw)
            req_txt = _fmt_req(r["어학요건"])
            if not lang_raw and r["어학요건"]:
                badge, color = "어학 입력 필요", MUTED
            elif r["어학"]["적격"]:
                badge, color = "응시 가능", GOOD
            else:
                badge, color = "응시 불가(어학 미달)", BAD
            st.markdown(f"""
            <div class="reccard">
              <span class="scorepill" style="background:{color}">{badge}</span>
              <div class="track" style="font-size:1.05rem">{field}</div>
              <div style="font-size:.83rem;color:{MUTED};margin-top:.2rem">
                선발 {r['인원']}명 · 근무지 {r['근무지']}</div>
              <div style="font-size:.85rem;color:{INK};margin-top:.5rem">
                🗣 어학요건: {req_txt}<br>
                ▸ 판정: {r['어학']['사유']}<br>
                ▸ 가점 적용: {r['가점적용']['적용']} — {r['가점적용']['설명']}
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.divider()
        st.markdown("**🎤 면접 점수 시뮬레이션** (원점수는 본인 추정값 — 예측 아님)")
        st.caption("출처: 공고 붙임 면접심사 평가기준표. 면접 100점, 합격: 70점 이상자 중 고득점순.")
        raw = st.number_input("예상 면접 원점수 (0~100)", min_value=0, max_value=100,
                              value=72, step=1)
        sim = sc.interview_score_bto_contract(raw, student.get("가산", {}))
        s1, s2, s3 = st.columns(3)
        s1.metric("면접 원점수", f"{sim['면접원점수']}")
        s2.metric("가점 적용", f"+{sim['가산점적용']}")
        s3.metric("70점 컷", "통과" if sim["컷통과"] else "미달")
        if sim["가산근거"]:
            st.markdown("**가점 근거**: " + " / ".join(sim["가산근거"]))
        st.markdown(f"최종(가점 포함, 정렬용) **{sim['최종점수']}점** — "
                    + ("70점 컷 통과" if sim["컷통과"] else
                       "⚠️ 면접 원점수가 70점 미만이라 가점을 받아도 컷 미달"))
        st.caption(sim["주의"])
