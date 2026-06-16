"""
recommender.py — 부산 공공기관 커리어 로드맵 / 추천 엔진
=========================================================
busan_data.py 의 진단/예측 데이터를 받아, 학생 프로필(학년·전공계열·
보유자격·어학·관심)에 대해 '데이터상 유리한 직렬군'을 설명가능하게
스코어링하고, 직렬군별 준비 로드맵(목표 필기합격선·자격·어학·타임라인)을
산출한다.

설계 원칙
  - 설명가능성(explainable): 점수의 각 구성요소를 그대로 노출한다.
    심사 "AI 성능 검증" 항목 대비, 블랙박스가 아니라 근거를 보인다.
  - 구조적 패턴 우선: 단일 공고가 아니라 5년 누적 패턴으로 추천한다.
    당해연도 변수에 흔들리지 않도록 다년 평균 + 추세 방향을 함께 준다.
"""
from __future__ import annotations
import statistics
from collections import defaultdict
import busan_data as bd

# ── 전공계열 → 지원가능 직렬군 (primary 1.0 / secondary 0.6) ──
# 공공기관 직렬은 전공 적합성이 강하게 작용하므로 매핑을 명시한다.
MAJOR_FIT = {
    "전기·전자": {"전기": 1.0, "신호·통신": 0.8, "전산": 0.5},
    "기계":      {"기계": 1.0, "토목·건축": 0.4},
    "토목·건축·도시": {"토목·건축": 1.0, "기계": 0.3},
    "컴퓨터·정보": {"전산": 1.0, "신호·통신": 0.7, "사무·행정": 0.4},
    "상경·행정·법": {"사무·행정": 1.0, "전산": 0.3},
    "인문·사회·기타": {"사무·행정": 0.8, "운전·운송": 0.6, "공무직·기능": 0.6},
}
# 가산 대상(사회배려) — 본인 해당 시 사회배려 전형 접근성 ↑
SOCIAL_GROUPS = {"장애", "취업지원대상자", "보훈"}


def build_track_profiles():
    """직렬군별 구조적 프로필:
       평균경쟁률 / 평균필기합격선 / 최근3년 평균선발 / 추세방향 / 데이터수
    """
    rate = bd.load_rate_records()
    by = defaultdict(lambda: dict(comp=[], cut=[], sel_by_year=defaultdict(int)))
    for x in rate:
        g = x["직렬군"]
        if x["경쟁률"]:
            by[g]["comp"].append(x["경쟁률"])
        if x["합격선"] and x["합격선"] > 0:
            by[g]["cut"].append(x["합격선"])
        if x["선발"] and x["연도"]:
            by[g]["sel_by_year"][x["연도"]] += x["선발"]

    profiles = {}
    for g, d in by.items():
        years = sorted(d["sel_by_year"])
        recent = [d["sel_by_year"][y] for y in years if y >= 2022]
        early = [d["sel_by_year"][y] for y in years if y < 2022]
        trend = "—"
        if recent and early:
            r, e = statistics.mean(recent), statistics.mean(early)
            trend = "증가" if r > e * 1.1 else ("감소" if r < e * 0.9 else "유지")
        profiles[g] = dict(
            평균경쟁률=round(statistics.mean(d["comp"]), 1) if d["comp"] else None,
            평균합격선=round(statistics.mean(d["cut"]), 1) if d["cut"] else None,
            최근평균선발=round(statistics.mean(recent), 1) if recent else 0,
            추세=trend,
            데이터수=len(d["comp"]),
        )
    return profiles


def _competition_score(comp):
    """경쟁률이 낮을수록 진입 유리 → 0~1 점수 (역스케일, log)"""
    if not comp:
        return 0.5
    import math
    # 경쟁률 5:1 → 1.0, 100:1 → 0.0 근방으로 매핑
    s = 1 - (math.log10(comp) - math.log10(5)) / (math.log10(100) - math.log10(5))
    return max(0.0, min(1.0, s))


def recommend(student: dict, top_k=3):
    """student = {
        학년:int, 전공계열:str(MAJOR_FIT 키), 보유자격:[..], 어학:{토익:int..},
        사회배려:bool, 관심직렬:[..](선택)
    }
    반환: 직렬군별 적합도 점수 + 설명 + 로드맵
    """
    profiles = build_track_profiles()
    fit_map = MAJOR_FIT.get(student.get("전공계열", ""), {})
    grade = student.get("학년", 2)
    years_left = max(0.5, 4 - grade + 0.5)   # 준비 가능 기간(년)

    # 사회배려(장애·취업지원·보훈) 해당 시, 사회배려 전형의 평균 경쟁률을
    # 적용 — 데이터상 일반전형(고경쟁)보다 풀이 훨씬 얕아 진입 여유가 크다.
    social = bool(student.get("사회배려"))
    social_comp = _competition_score(
        bd.build_dataset()["esg"]["평균경쟁률"]  # 사회배려 전형 평균 경쟁률
    )

    results = []
    for track, fit in fit_map.items():
        prof = profiles.get(track)
        if not prof:
            continue
        comp_s = _competition_score(prof["평균경쟁률"])
        social_applied = False
        if social and comp_s < social_comp:
            # 사회배려 전형으로 지원 시 경쟁여유가 사회배려 평균 수준까지 개선
            comp_s = social_comp
            social_applied = True
        # 채용규모: 최근평균선발 클수록 기회 ↑ (정규화)
        size_s = min(1.0, prof["최근평균선발"] / 20.0)
        trend_s = {"증가": 1.0, "유지": 0.6, "감소": 0.3, "—": 0.5}[prof["추세"]]
        # 가중합 (전공적합 0.40 / 경쟁여유 0.30 / 채용규모 0.15 / 추세 0.15)
        score = 0.40 * fit + 0.30 * comp_s + 0.15 * size_s + 0.15 * trend_s
        results.append(dict(
            직렬군=track, 적합도=round(score * 100),
            구성=dict(전공적합=round(fit, 2), 경쟁여유=round(comp_s, 2),
                      채용규모=round(size_s, 2), 추세=prof["추세"]),
            사회배려적용=social_applied,
            데이터=prof,
            로드맵=_roadmap(track, prof, student, years_left, social_applied),
        ))
    results.sort(key=lambda r: -r["적합도"])
    return results[:top_k]


# 직렬군별 권장 준비요소(공공기관 공통 + 직렬 특화)
TRACK_PREP = {
    "전기":      ["전기기사", "전기산업기사"],
    "기계":      ["일반기계기사", "공조냉동기계기사"],
    "토목·건축":  ["토목기사", "건축기사"],
    "신호·통신":  ["정보통신기사", "전자기사"],
    "전산":      ["정보처리기사", "SQLD"],
    "사무·행정":  ["컴퓨터활용능력1급", "한국사1급"],
    "운전·운송":  ["제2종 전기차량 운전면허"],
    "공무직·기능": ["해당 분야 기능사 이상"],
}


def _roadmap(track, prof, student, years_left, social_applied=False):
    cut = prof["평균합격선"]
    target = (f"필기 목표 {round(cut + 8)}점 이상 (평균합격선 {cut} + 안전마진)"
              if cut else "필기 합격선 데이터 부족 — 공고별 확인 권장")
    have = set(student.get("보유자격", []))
    need = [c for c in TRACK_PREP.get(track, []) if c not in have]
    # 어학(공공기관 사무·행정 토익 비중) 가이드
    toeic = student.get("어학", {}).get("토익")
    lang = None
    if track == "사무·행정":
        lang = "토익 800+ 권장" + (f" (현재 {toeic})" if toeic else "")
    social_note = None
    if social_applied:
        social_note = ("사회배려(장애·취업지원·보훈) 전형으로 지원 시, 데이터상 "
                       "해당 전형은 지원풀이 얕아(평균 경쟁률 한 자릿수·일부 미달) "
                       "진입 여유가 큽니다. 해당 전형 자격·증빙을 미리 준비하세요.")
    return dict(
        필기목표=target,
        취득권장자격=need or ["보유 자격 충분"],
        어학=lang,
        준비기간=f"약 {years_left:.1f}년",
        구조노트=f"{track}: 5년 평균 경쟁률 {prof['평균경쟁률']}:1, 채용추세 {prof['추세']}",
        사회배려안내=social_note,
    )


if __name__ == "__main__":
    import json
    samples = [
        dict(이름="A(전기전공 2학년)", 학년=2, 전공계열="전기·전자",
             보유자격=[], 어학={"토익": 700}, 사회배려=False),
        dict(이름="B(상경 3학년)", 학년=3, 전공계열="상경·행정·법",
             보유자격=["컴퓨터활용능력1급"], 어학={"토익": 850}, 사회배려=False),
        dict(이름="C(인문 2학년)", 학년=2, 전공계열="인문·사회·기타",
             보유자격=[], 어학={"토익": 600}, 사회배려=False),
    ]
    print("=== 직렬군 구조 프로필 ===")
    for g, p in build_track_profiles().items():
        print(f"  {g:<10} 경쟁률{str(p['평균경쟁률']):>6}:1  합격선{str(p['평균합격선']):>5}  "
              f"최근선발{p['최근평균선발']:>5}  추세{p['추세']}")
    for s in samples:
        print(f"\n=== {s['이름']} 추천 ===")
        for r in recommend(s):
            print(f"  [{r['적합도']}점] {r['직렬군']}  근거{r['구성']}")
            rm = r["로드맵"]
            print(f"        {rm['필기목표']}")
            print(f"        취득권장: {', '.join(rm['취득권장자격'])}  | {rm['구조노트']}")
