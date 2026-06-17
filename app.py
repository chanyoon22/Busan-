"""
app.py — 부산 공공기관 커리어 로드맵 내비게이터 (v2)
================================================
v1 대비 핵심 수정
  1) [비용/안정성] 프로필 입력을 st.form 으로 감싸 '제출' 시에만 추천·AI가
     돈다. v1은 위젯을 만질 때마다 전체 리런 → Gemini가 연속 호출되어 요금
     폭탄·429 위험이 있었다.
  2) [신뢰] '하드코딩 가중치'를 슬라이더로 노출 → 사용자 조절형 시뮬레이터.
  3) [정직성] 'AI 합격선 예측/MAE' 표현 제거. '합격선 통계(과거 평균±편차)'로
     명명하고 제공기관·결측을 명시한다.
  4) [신규] 직무별 '일반 vs 사회배려 전형' 경쟁률 갭을 시각화(사회배려는 가짜
     직무가 아니라 전형 옵션임을 보여줌).
  5) [성능] 무거운 ETL을 캐시. recommend는 캐시된 dataset을 주입받는다.

실행:  streamlit run app.py
배포:  GitHub push → Streamlit Cloud (Secrets에 GEMINI_API_KEY)
"""
import hashlib, json
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
  <p>부산교통공사·부산도시공사·부산관광공사 5년 채용데이터로,
     <b>전공·전형별로 데이터상 유리한 직무와 준비 순서</b>를 설계합니다.
     <span class="src">(추천 수치는 과거 통계이며 예측이 아닙니다)</span></p>
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
    with st.form("profile"):
        grade = st.select_slider("학년", options=[1, 2, 3, 4], value=2)
        major = st.selectbox("전공계열", list(rc.MAJOR_FIT.keys()),
                             index=len(rc.MAJOR_FIT) - 1)
        certs = st.multiselect("보유 자격증", sc.CERT_MASTER)

        st.markdown("**어학 성적** (보유한 것만 입력)")
        lang_test = st.selectbox("시험 종류", sc.LANG_TESTS)
        lang_val = st.text_input("점수/등급 (예: 토익 780, 오픽 IH)", value="")

        st.markdown("**거주지(주민등록 기준)**")
        region = st.selectbox("현재 주민등록 지역", sc.RESIDENCY_REGIONS)
        social_v = st.selectbox("취업지원대상자 가점", [0, 5, 10],
                                help="국가보훈부 증명서 비율(없으면 0)")
        disabled = st.checkbox("장애인 등록")

        st.markdown("**가중치 조절** (추천 기준을 직접 설계)")
        w_fit = st.slider("전공 적합", 0.0, 1.0, 0.40, 0.05)
        w_comp = st.slider("경쟁 여유", 0.0, 1.0, 0.30, 0.05)
        w_size = st.slider("채용 규모", 0.0, 1.0, 0.15, 0.05)
        w_trend = st.slider("채용 추세", 0.0, 1.0, 0.15, 0.05)

        submitted = st.form_submit_button("프로필 제출 / 다시 계산", use_container_width=True)
    st.caption("입력은 저장되지 않습니다. 제출해야 추천·AI가 실행되어 API 비용을 아낍니다.")

# 제출 전이면 기본 프로필로 1회만 계산(초기 화면용), 제출 시 갱신
if submitted or "student" not in st.session_state:
    tot = (w_fit + w_comp + w_size + w_trend) or 1.0
    weights = dict(fit=w_fit/tot, comp=w_comp/tot, size=w_size/tot, trend=w_trend/tot)
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

student = st.session_state.student
recs = st.session_state.recs

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎯 내 직무 로드맵", "📊 채용 미스매치 진단",
                                  "💬 AI 커리어 상담", "🎓 청년인턴 점수+성장추적",
                                  "📋 공고 적격 체커(관광공사 계약직)"])

# ───────────────────────── 탭 1 ─────────────────────────
with tab1:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("##### 데이터가 추천하는 직무 (전공 지원범위 내)")
        if not recs:
            st.info("선택한 전공계열에 매칭되는 직무 데이터가 없습니다.")
        for i, r in enumerate(recs, 1):
            comp = r["구성"]
            d = r["데이터"]
            blind_tag = ('<span class="tag" style="background:#e7f4f5;color:#0e7c86">블라인드·전공무관</span>'
                         if r["블라인드"] else "")
            social_tag = (f'<span class="tag" style="background:#fde8e1;color:{ACCENT}">사회배려 전형 갭 반영</span>'
                          if r["사회배려적용"] else "")
            cut_txt = (f"평균 합격선 {d['합격선평균']}점 (±{d['합격선표준편차']})"
                       if d['합격선평균'] else "합격선 공시 없음")
            st.markdown(f"""
            <div class="reccard">
              <span class="scorepill">{r['적합도']}</span>
              <div class="rank">{i}순위 · 적합도</div>
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
    with c2:
        st.markdown("##### AI 맞춤 로드맵")

        @st.cache_data(show_spinner=False)
        def cached_narrate(profile_key, recs_key):
            return ai.narrate_roadmap(student, recs, ds)

        pkey = hashlib.md5(json.dumps(student, ensure_ascii=False, default=str).encode()).hexdigest()
        rkey = "|".join(r["직무"] for r in recs)
        with st.spinner("로드맵 생성 중…"):
            st.info(cached_narrate(pkey, rkey))
        st.caption("AI는 위 공공데이터 수치와 공고 임용조건에만 근거해 서술합니다.")

# ───────────────────────── 탭 2: 미스매치 + 사회배려 갭 ─────────────────────────
with tab2:
    mm = [m for m in ds["mismatch"] if m["평균경쟁률"]]
    mm.sort(key=lambda m: m["평균경쟁률"])
    fig = go.Figure(go.Bar(
        x=[m["평균경쟁률"] for m in mm], y=[m["직무"] for m in mm], orientation="h",
        marker_color=[class_color(m["분류"]) for m in mm],
        text=[f"{m['평균경쟁률']}:1" for m in mm], textposition="outside"))
    fig.update_layout(
        title="직무별 5년 가중 경쟁률(일반전형) — 빨강=과경쟁·노랑=미달위험·초록=적정",
        height=420, margin=dict(l=10, r=40, t=50, b=10),
        plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(fig, use_container_width=True)

    k1, k2, k3, k4 = st.columns(4)
    cs = ds["cut_stat"]
    k1.metric("경쟁률 레코드", f"{ds['meta']['경쟁률레코드']}건")
    k2.metric("합격선 통계(평균±편차)", f"{cs['전체평균']}±{cs['전체표준편차']}",
              help=f"제공기관 {', '.join(cs['제공기관'])} · n={cs['n']} · {cs['주의']}")
    k3.metric("사회배려 전형 가중경쟁률", f"{ds['esg']['가중경쟁률']}:1")
    k4.metric("사회배려 미달 건수", f"{ds['esg']['미달건수']}건",
              help=f"표본 {ds['esg']['표본수']}건 중")

    # 신규: 일반 vs 사회배려 전형 경쟁률 갭
    st.markdown("##### 직무별 일반 vs 사회배려 전형 경쟁률 갭")
    gj = [(j, s["일반_가중경쟁률"], s["사회배려_가중경쟁률"])
          for j, s in ds["job_stats"].items()
          if s["일반_가중경쟁률"] and s["사회배려_가중경쟁률"]]
    gj.sort(key=lambda t: -t[1])
    gfig = go.Figure()
    gfig.add_trace(go.Bar(name="일반전형", y=[t[0] for t in gj],
                          x=[t[1] for t in gj], orientation="h", marker_color=MUTED))
    gfig.add_trace(go.Bar(name="사회배려전형", y=[t[0] for t in gj],
                          x=[t[2] for t in gj], orientation="h", marker_color=ACCENT))
    gfig.update_layout(barmode="group", height=360,
                       margin=dict(l=10, r=10, t=10, b=10),
                       plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(gfig, use_container_width=True)
    st.caption("사회배려(장애·보훈·취업지원)는 '직무'가 아니라 '전형'입니다. "
               "같은 직무라도 사회배려 전형의 경쟁률이 크게 낮습니다.")

    st.markdown("##### 신규채용 추세 (정규직 일반)")
    tfig = go.Figure()
    for inst, rows in ds["hire_trend"].items():
        tfig.add_trace(go.Scatter(x=[r["연도"] for r in rows],
                                  y=[r["정규직일반"] for r in rows],
                                  mode="lines+markers", name=inst))
    tfig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                       plot_bgcolor="white", font=dict(family="Pretendard"))
    st.plotly_chart(tfig, use_container_width=True)
    st.caption("출처: data.go.kr — 부산교통공사·부산도시공사·부산관광공사 채용 공시. "
               "수치는 5년 누적 구조 경향이며 당해연도 채용규모는 각 기관 공고로 재확인 필요.")

# ───────────────────────── 탭 3: AI 상담 ─────────────────────────
with tab3:
    st.markdown("##### 무엇이든 물어보세요 (데이터·공고 근거로 답합니다)")
    st.caption('예: "전기직 일반전형 경쟁률은?" / "사무직 토익 몇 점 필요해?" / "사회배려 전형이 얼마나 유리해?"')
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
                a = ai.chat(student, recs, q, ds=ds)
            st.write(a)
        st.session_state.chat.append(("assistant", a))

# ───────────────── 탭 4: 청년인턴 서류점수 시뮬레이터 + 성장추적 ─────────────────
with tab4:
    st.markdown("##### 🎓 청년인턴 서류전형 점수 시뮬레이터")
    st.caption("출처: 부산교통공사 제2026-245호 공고 — 실제 정량 가점 테이블·가산점 규칙. "
               "여기 점수는 공고가 명시한 범위에서만 계산됩니다(추정 아님).")

    # (1) 정량 점수 — 사이드바에서 입력한 자격증 기반
    quant = sc.intern_quant_score(student.get("보유자격", []))
    bonus = sc.bonus_points(student.get("가산", {}), stage_max=100)
    res = sc.residency_ok(student.get("거주지", ""))

    c1, c2, c3 = st.columns(3)
    c1.metric("정량 점수(자격증)", f"{quant['정량점수']} / {quant['만점']}")
    c2.metric("가산 비율", f"+{bonus['가산비율']}%")
    c3.metric("거주지 요건", "충족" if res["충족"] else "미충족")

    st.markdown("**항목별 정량 득점** (항목 내 최고 자격 1개만 인정 · 동일항목 중복불가)")
    for item, d in quant["세부"].items():
        label = d["자격"] or "해당 자격 없음"
        st.markdown(f"- **{item}**: {label} → {d['점수']}점")
    if bonus["근거"]:
        st.markdown("**가산점 근거**: " + " / ".join(bonus["근거"]))
    if not res["충족"]:
        st.warning(res["설명"])
    st.caption(res["주의"])

    # 정성평가는 자기소개서 등급이라 자동계산 불가 — 정직하게 안내
    st.info("정성평가(45점: 자기소개·지원동기·직무목표, 등급 S15~D7)는 자기소개서 "
            "정성평가라 자동 산출이 불가합니다. 위 정량 점수는 '내가 통제 가능한 부분'입니다.")

    st.divider()

    # (2) 성장추적 — 로드맵 체크리스트 (세션 기반 MVP)
    st.markdown("##### 📈 성장추적: 다음에 켤 단계")
    st.caption("⚠️ 현재는 세션 기반(새로고침 시 초기화). 진짜 월 단위 추적은 로그인+DB가 "
               "필요합니다(아래 한계 참고).")

    # 1순위 직무 로드맵을 단계 체크리스트로 변환
    if recs:
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
        for i, (kind, label) in enumerate(steps):
            key = f"step_{i}"
            checked = st.checkbox(f"[{kind}] {label}", value=st.session_state.progress.get(key, False))
            st.session_state.progress[key] = checked
            if checked:
                done_now.append(label)

        # 다음 액션 제안: 첫 미완료 단계
        nxt = next((s for i, s in enumerate(steps)
                    if not st.session_state.progress.get(f"step_{i}")), None)
        pct = int(100 * len(done_now) / len(steps)) if steps else 0
        st.progress(pct / 100, text=f"로드맵 진척률 {pct}%")
        if nxt:
            st.success(f"👉 지금 켤 단계: **{nxt[1]}** ({nxt[0]})")
        else:
            st.balloons()
            st.success("로드맵 완주! 공고 모니터링 단계로 넘어가세요.")
    else:
        st.info("사이드바에서 전공을 선택하고 제출하면 단계가 생성됩니다.")

    with st.expander("성장추적을 '진짜'로 만들려면 — 솔직한 한계와 다음 단계"):
        st.markdown(
            "- **지금 한계**: Streamlit Cloud는 로그인이 없어 사용자별 진척이 세션이 끝나면 "
            "사라집니다. '이번 달 토익 750 달성 → 다음 단계' 같은 월 단위 추적은 불가합니다.\n"
            "- **현실적 업그레이드 경로**: ① 간단한 이메일 로그인(streamlit-authenticator) + "
            "② Google Sheets나 SQLite/Supabase에 진척 저장 → 재방문 시 불러오기. "
            "이 구조를 붙이면 비로소 '내비게이터(지속 안내)'가 됩니다.\n"
            "- **공모전 발표 팁**: 현재 버전은 '계산기→로드맵 변환'까지 구현, "
            "'지속 추적'은 로드맵으로 제시하면 과장 없이 성숙도를 보여줄 수 있습니다.")

# ───────────────── 탭 5: 공고 적격 체커 (관광공사 일반계약직 2026-42호) ─────────────────
with tab5:
    P = sc.TOURISM_CONTRACT_2026_42
    st.markdown(f"##### 📋 {P['공고']}")
    st.caption(f"출처: {P['출처']} · 고용형태: {P['고용형태']} · 계약기간 {P['계약기간']} · "
               f"전형: {P['전형']} · 총 {P['총원']}명")

    # 이 화면의 존재 이유: 글로벌 환산표가 아니라 '공고 원문 컷'으로 판정한다.
    st.info("이 체커는 어학을 환산표로 추정하지 않고, **공고가 명시한 분야별 시험 컷**으로 "
            "직접 적격 여부를 판정합니다. (같은 TOEIC라도 공고마다 타 시험 컷이 다르기 때문)")

    lang_raw = student.get("어학원본", {})
    if not lang_raw:
        st.warning("사이드바에서 어학 성적을 입력하면 분야별 적격 여부가 자동 판정됩니다. "
                   "(예: 시험 종류 '토익(TOEIC)', 점수 '790')")

    st.markdown("**분야별 적격 판정** (어학요건은 한 시험만 충족해도 됨)")
    for field in P["분야"]:
        r = sc.field_eligibility(P, field, lang_raw)
        req = r["어학요건"]
        req_txt = _fmt_req(req)

        if not lang_raw and req:
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

    # 면접 배점 + 점수 시뮬레이터
    st.markdown("##### 🎤 면접 배점표 & 점수 시뮬레이터")
    st.caption("출처: 공고 붙임 면접심사 평가기준표. 면접 100점, 합격: 70점 이상자 중 고득점순.")

    cols = st.columns(2)
    rubric = sc.INTERVIEW_RUBRIC_BTO_CONTRACT
    for col, (cat, items) in zip(cols, rubric.items()):
        with col:
            st.markdown(f"**{cat}**")
            for name, pt in items.items():
                st.markdown(f"- {name}: {pt}점")

    st.markdown("**면접 점수 시뮬레이션** (원점수는 본인 추정값 — 예측 아님)")
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

    with st.expander("이 공고를 시스템에 넣은 이유 — 어학 환산표의 함정"):
        st.markdown(
            "- 이 공고는 **TOEIC 800 = TOEFL 69 = New TEPS 228**로 명시합니다.\n"
            "- 그런데 같은 관광공사 '일반직' 공고는 **TOEIC 800 = TOEFL 91 = TEPS 650**입니다.\n"
            "- 즉 **동일 기관·동일 TOEIC라도 공고에 따라 타 시험 컷이 크게 다릅니다.**\n"
            "- 그래서 이 체커는 글로벌 환산표(`LANG_EQUIV`)로 '충족'을 추정하지 않고, "
            "공고가 적은 시험별 컷을 직접 비교합니다. (지어내지 않는다 — 1원칙)")
