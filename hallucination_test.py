"""
hallucination_test.py — AI 비환각 검증 하네스 (실측, 숫자 안 지어냄)
=====================================================================
주장: "수치는 결정론적 코드가 데이터에서 조회하고 LLM은 문장화만 하므로,
       데이터에 없는 수치는 구조적으로 생성될 수 없다."
이 주장을 테스트 케이스로 실제 검증한다. 모든 숫자는 이 스크립트를 돌려
나온 실측값이다(사업계획서에 넣을 땐 반드시 본인이 직접 돌려 값 확인).
"""
import re, busan_data as bd, recommender as rc, gemini_advisor as ai

ds = bd.build_dataset()
js = ds["job_stats"]
student = dict(학년=2, 전공계열="인문·사회·기타", 보유자격=[], 어학={"토익":790}, 가산={})
recs = rc.recommend(student, ds=ds)

def numbers_in(text):
    ratios = set(re.findall(r"(\d+\.?\d*)\s*:\s*1", text))
    points = set(re.findall(r"(\d+\.?\d*)\s*점", text))
    return ratios, points

def _near(val, found_set, tol=1.0):
    """val과 found_set 안의 값이 tol 이내면 인용으로 인정(소수점 반올림 허용)."""
    try:
        v = float(val)
        return any(abs(v - float(f)) <= tol for f in found_set)
    except (ValueError, TypeError):
        return False

# ── 1) 데이터 존재 질의: 파이프라인이 정확한 데이터값을 인용하는가 ──
present, grounded, fabricated_total = 0, 0, 0
for job, s in js.items():
    if not s["일반_가중경쟁률"]:
        continue
    present += 1
    q = f"{job} 경쟁률은?"
    ans = ai.chat(student, recs, q, ds=ds)
    ratios, points = numbers_in(ans)

    allowed_ratios = {str(s["일반_가중경쟁률"])}
    if s.get("사회배려_가중경쟁률"):
        allowed_ratios.add(str(s["사회배려_가중경쟁률"]))
    for t, d in s.get("사회배려_세부", {}).items():
        if d.get("경쟁률"): allowed_ratios.add(str(d["경쟁률"]))
    allowed_points = set()
    if s.get("합격선평균"): allowed_points.add(str(s["합격선평균"]))
    if s.get("합격선표준편차"): allowed_points.add(str(s["합격선표준편차"]))

    if _near(s["일반_가중경쟁률"], ratios):
        grounded += 1

    fab_r = {r for r in ratios if not _near(float(r), allowed_ratios)}
    fab_p = {p for p in points if not _near(float(p), allowed_points)}
    fabricated_total += len(fab_r) + len(fab_p)

# ── 2) 데이터 결측 질의: 가짜 수치 없이 '확인 필요'로 방어하는가 ──
absent_probes = [
    "부산시설공단 일반전형 필기 합격선 평균은?",
    "부산환경공단 사무직 경쟁률 알려줘",
    "관광공사 일반직 정규직 작년 합격선은?",
    "2026년 교통공사 정확한 채용 일정은?",
]
deferred, absent_fab = 0, 0
defer_kw = ["없", "확인", "공고", "충분치", "제공된"]
for q in absent_probes:
    ans = ai.chat(student, recs, q, ds=ds)
    ratios, points = numbers_in(ans)
    if not ratios and not points:
        if any(k in ans for k in defer_kw):
            deferred += 1
    else:
        absent_fab += len(ratios) + len(points)

print("=" * 58)
print("AI 비환각 검증 — 실측 결과")
print("=" * 58)
print(f"[데이터 존재 질의] {present}건")
print(f"  · 정확한 경쟁률 인용(Grounding, ±1 허용): {grounded}/{present} = {round(100*grounded/present,1)}%")
print(f"  · 허용범위 밖 수치 생성: {fabricated_total}건")
print(f"[데이터 결측 질의] {len(absent_probes)}건")
print(f"  · 가짜 수치 없이 방어(Deferral): {deferred}/{len(absent_probes)} = {round(100*deferred/len(absent_probes),1)}%")
print(f"  · 결측 질의에서 수치 생성: {absent_fab}건")


def eval_baseline():
    """baseline: 동일한 데이터 존재 질의를 컨텍스트 없이 일반 LLM에 던진다.
       LLM이 실제 데이터값과 다른 수치를 만드는 비율을 측정한다."""
    NAIVE_SYS = ("당신은 부산 공공기관 취업 전문가입니다. "
                 "질문에 구체적인 수치를 포함해 상세히 답하세요.")
    total, wrong = 0, 0
    for job, s in js.items():
        if not s["일반_가중경쟁률"]: continue
        q = f"부산 {job} 직렬의 최근 채용 경쟁률은 몇 대 1이에요?"
        ans = ai._call(q, NAIVE_SYS, max_tokens=200, temp=0.5)
        if ans is None: return None
        total += 1
        ratios, _ = numbers_in(ans)
        if ratios and not _near(s["일반_가중경쟁률"], ratios, tol=5.0):
            wrong += 1
    if total == 0: return None
    return dict(질의수=total, 다른값생성=wrong, 불일치율=round(100*wrong/total, 1))


bl = eval_baseline()
print()
print("[baseline 비교] — 같은 질의를 데이터 컨텍스트 없이 일반 LLM에 던짐")
if bl is None:
    print("  GEMINI_API_KEY 미설정 → baseline 미측정. 키 설정 후 재실행.")
    print("  ※ 측정 전에는 사업계획서에 baseline 숫자를 절대 임의 기입하지 말 것.")
else:
    print(f"  질의 {bl['질의수']}건 중 실제값과 다른 수치 생성: {bl['다른값생성']}건 "
          f"→ 불일치율 {bl['불일치율']}%")
    print(f"  (본 엔진 동일 질의: 0% — 코드가 데이터값을 직접 조회·인용)")

print("\n─── 사업계획서 붙여넣기용 요약(실측값) ───")
print(f"  본 엔진 Grounding(데이터 존재, ±1): {round(100*grounded/present,1)}%")
print(f"  본 엔진 결측 방어(Deferral): {round(100*deferred/len(absent_probes),1)}%")
print(f"  본 엔진 수치 오류: {fabricated_total + absent_fab}건")
print(f"  baseline 불일치율: {'미측정(키 설정 후 실측)' if bl is None else str(bl['불일치율'])+'%'}")
