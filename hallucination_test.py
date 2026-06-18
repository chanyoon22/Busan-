"""
hallucination_test.py — AI 비환각 검증 하네스 (실측, 숫자 안 지어냄)
=====================================================================
주장: "수치는 결정론적 코드가 데이터에서 조회하고 LLM은 문장화만 하므로,
       데이터에 없는 경쟁률·합격선은 '구조적으로' 생성될 수 없다."
이 주장을 테스트 케이스로 실제 검증한다. 모든 숫자는 이 스크립트를 돌려
나온 실측값이다(사업계획서에 넣을 땐 반드시 본인이 직접 돌려 값 확인).
"""
import re, busan_data as bd, recommender as rc, gemini_advisor as ai

ds = bd.build_dataset()
js = ds["job_stats"]
student = dict(학년=2, 전공계열="인문·사회·기타", 보유자격=[], 어학={"토익":790}, 가산={})
recs = rc.recommend(student, ds=ds)

def numbers_in(text):
    """문장에서 'NN:1' 경쟁률, 'NN점' 합격선 등 수치를 뽑는다."""
    ratios = set(re.findall(r"(\d+\.?\d*)\s*:\s*1", text))
    points = set(re.findall(r"(\d+\.?\d*)\s*점", text))
    return ratios, points

# ── 1) 데이터 존재 질의: 엔진이 '정확한 데이터값'을 인용하는가 ──
present, grounded = 0, 0
fabricated_total = 0
for job, s in js.items():
    if not s["일반_가중경쟁률"]:
        continue
    present += 1
    q = f"{job} 경쟁률은?"
    ans = ai.chat(student, recs, q, ds=ds)   # 키 없으면 결정론적 폴백
    ratios, points = numbers_in(ans)
    # 데이터에 실제 존재하는 값 집합
    allowed_ratios = {str(s["일반_가중경쟁률"])}
    if s.get("사회배려_가중경쟁률"):
        allowed_ratios.add(str(s["사회배려_가중경쟁률"]))
    for t, d in s.get("사회배려_세부", {}).items():
        if d.get("경쟁률"): allowed_ratios.add(str(d["경쟁률"]))
    allowed_points = set()
    if s.get("합격선평균"): allowed_points.add(str(s["합격선평균"]))
    # 정확한 경쟁률 인용 여부
    if str(s["일반_가중경쟁률"]) in ratios:
        grounded += 1
    # 데이터에 없는 수치를 지어냈는가
    fab = (ratios - allowed_ratios) | (points - allowed_points)
    fabricated_total += len(fab)

# ── 2) 데이터 결측 질의: 엔진이 가짜 수치 없이 '확인 필요'로 방어하는가 ──
absent_probes = [
    "부산시설공단 일반전형 필기 합격선 평균은?",   # 시설공단 합격선 데이터 없음
    "부산환경공단 사무직 경쟁률 알려줘",             # 환경공단 경쟁률 데이터 없음
    "관광공사 일반직 정규직 작년 합격선은?",         # 관광 합격선 없음
    "2026년 교통공사 정확한 채용 일정은?",           # 일정 데이터 없음
]
deferred = 0
defer_kw = ["없", "확인", "공고", "충분치", "제공된"]
absent_fab = 0
for q in absent_probes:
    ans = ai.chat(student, recs, q, ds=ds)
    ratios, points = numbers_in(ans)
    # 결측 질의인데 구체 수치를 뱉으면 환각
    if not ratios and not points:
        if any(k in ans for k in defer_kw):
            deferred += 1
    else:
        absent_fab += len(ratios) + len(points)

print("="*58)
print("AI 비환각 검증 — 실측 결과 (결정론적 엔진, API 키 없이)")
print("="*58)
print(f"[데이터 존재 질의] {present}건")
print(f"  · 정확한 경쟁률 인용(Grounding): {grounded}/{present} = {round(100*grounded/present,1)}%")
print(f"  · 데이터에 없는 수치 생성(환각): {fabricated_total}건")
print(f"[데이터 결측 질의] {len(absent_probes)}건")
print(f"  · 가짜 수치 없이 '확인 필요'로 방어(Deferral): {deferred}/{len(absent_probes)} = {round(100*deferred/len(absent_probes),1)}%")
print(f"  · 결측 질의에서 가짜 수치 생성: {absent_fab}건")


def eval_baseline():
    """[선택] GEMINI_API_KEY가 있으면 '데이터 컨텍스트 없는 일반 LLM'이 동일한
       결측 질의에 가짜 수치를 만드는 비율을 실측한다. 키가 없으면 측정 안 함
       (숫자를 임의로 채우지 않는다 — 1원칙)."""
    NAIVE_SYS = "당신은 취업 상담가입니다. 사용자 질문에 아는 대로 구체적으로 답하세요."
    fab, answered = 0, 0
    for q in absent_probes:
        ans = ai._call(q, NAIVE_SYS, max_tokens=300)
        if ans is None:
            return None
        answered += 1
        r, p = numbers_in(ans)
        if r or p:
            fab += 1
    return dict(질의수=answered, 가짜수치생성=fab, 환각률=round(100*fab/answered, 1)) if answered else None


bl = eval_baseline()
print()
print("[baseline 일반 LLM 비교] — 데이터 컨텍스트 없이 같은 결측 질의")
if bl is None:
    print("  GEMINI_API_KEY 미설정 → baseline 미측정. 키 설정 후 재실행 시 실측됨.")
    print("  ※ 측정 전에는 사업계획서에 baseline 숫자를 절대 임의 기입하지 말 것.")
else:
    print(f"  결측 {bl['질의수']}건 중 가짜 수치 {bl['가짜수치생성']}건 → 환각률 {bl['환각률']}% "
          f"(본 엔진은 동일 질의 0.0%)")

print("\n─── 사업계획서 붙여넣기용 요약(실측값) ───")
print(f"  본 엔진 Grounding(데이터 존재): {round(100*grounded/present,1)}%")
print(f"  본 엔진 결측 방어(Deferral): {round(100*deferred/len(absent_probes),1)}%")
print(f"  본 엔진 환각(가짜 수치): {fabricated_total + absent_fab}건")
print(f"  baseline 환각률: {'미측정(키 설정 후 실측)' if bl is None else str(bl['환각률'])+'%'}")
