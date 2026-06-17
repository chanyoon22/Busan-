"""
recommender.py — 부산 공공기관 직무 추천 엔진 (v2)
=========================================================
busan_data v2의 (직무 × 전형) 통계를 받아, 학생 프로필에 대해 '데이터상
유리한 직무'를 설명가능하게 스코어링하고 준비 로드맵을 만든다.

v1 대비 핵심 수정
  1) [도메인] 블라인드 채용 반영. 일반행정(사무·행정)은 학력·전공 무관이므로
     전공 적합도를 모든 계열에 1.0으로 둔다(인문계 0.8 페널티 삭제). 단,
     전공 무관이라는 사실을 그대로 노출해 '적합도'를 경쟁·규모 축으로 설명한다.
  2) [도메인] 자격 로드맵에서 '기사 + 산업기사' 중복 권장을 제거한다.
     동일 분야는 상위 자격(기사) 하나만 권장한다.
  3) [설계] 가중치를 외부 주입(weights)으로 받는다. 앱에서 슬라이더로 조절 →
     '하드코딩 점수'가 아니라 '사용자 조절형 시뮬레이터'가 된다.
  4) [정직성] 사회배려는 가짜 직무가 아니라, 추천된 각 직무의 '사회배려 전형
     경쟁률 갭'으로 보여준다(예: 전기직 일반 48:1 → 사회배려 3:1).
  5) [근거] 어학·자격 가이드는 임의값이 아니라 공고 임용조건(eligibility)에서
     추출한 실제 최저 기준을 인용한다.
"""
from __future__ import annotations
import math, statistics
from collections import defaultdict
import busan_data as bd

# ── 전공계열 → 지원가능 직무 적합도 ──
# 기술직은 자격·전공이 실제로 요구되므로 적합도 차등이 정당하다.
# 사무·행정은 블라인드(전공 무관)이므로 모든 계열에 1.0을 부여한다.
MAJOR_FIT = {
    "전기·전자":      {"전기": 1.0, "신호·통신": 0.85, "전산": 0.6, "사무·행정": 1.0},
    "기계":          {"기계": 1.0, "사무·행정": 1.0},
    "토목·건축·도시":  {"토목·건축": 1.0, "사무·행정": 1.0},
    "컴퓨터·정보":     {"전산": 1.0, "신호·통신": 0.7, "사무·행정": 1.0},
    "상경·행정·법":    {"사무·행정": 1.0, "전산": 0.4},
    "인문·사회·기타":  {"사무·행정": 1.0, "운전·운송": 0.7, "공무직·기능": 0.7},
}

# 블라인드(전공 무관) 직무 — 적합도 설명을 다르게 표기한다.
BLIND_JOBS = {"사무·행정", "운전·운송", "공무직·기능"}

# 직무별 권장 자격 — 동일 분야 중복(기사+산업기사) 금지, 상위 1개만.
TRACK_PREP = {
    "전기":      ["전기기사"],
    "기계":      ["일반기계기사"],
    "토목·건축":  ["토목기사 또는 건축기사(택1)"],
    "신호·통신":  ["정보통신기사"],
    "전산":      ["정보처리기사"],
    "사무·행정":  ["컴퓨터활용능력 1급", "한국사능력검정 1급"],
    "운전·운송":  ["제2종 전기차량 운전면허"],
    "공무직·기능": ["해당 분야 기능사 이상"],
}

DEFAULT_WEIGHTS = dict(fit=0.45, comp=0.35, size=0.20)
# [정직성] v2.1에서 'trend(추세)' 축을 제거함. 기존 _trend()는 모든 직무에 항상
# '유지'(0.6)를 반환해, 슬라이더가 있어도 점수에 아무 변별을 주지 못하는 '가짜
# 조절'이었다. 직무 단위 연도추세는 표본이 얕아 신뢰할 수 없으므로(핸드오프 8),
# 추세는 점수에서 빼고 '신규채용 추세 차트'(앱 탭2)에서 정보로만 보여준다.


def _competition_score(comp):
    """경쟁률이 낮을수록 유리 → 0~1. 범위를 3:1~200:1로 넓혀 변별력 확보."""
    if not comp:
        return 0.5
    lo, hi = 3.0, 200.0
    s = 1 - (math.log10(comp) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
    return round(max(0.0, min(1.0, s)), 3)


def _sample_score(n):
    """'규모'가 아니라 '데이터 표본량(추정 신뢰도)'. 레코드 수가 많을수록 그 직무의
       경쟁률 추정이 더 안정적이라는 의미일 뿐, 실제 채용 인원 크기가 아니다."""
    return min(1.0, (n or 0) / 8.0)


def build_job_view():
    """직무별 표시용 통계 묶음(앱·추천 공용). build_dataset 1회로 해결."""
    return bd.build_dataset()


def recommend(student: dict, top_k=3, weights=None, ds=None):
    """student = {학년, 전공계열, 보유자격[], 어학{토익}, 사회배려:bool}
       weights = {fit, comp, size} (합 1.0 권장, 앱 슬라이더 / 추세축은 v2.1에서 제거)
       반환: 직무별 적합도 + 설명 구성 + 로드맵
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)
    ds = ds or bd.build_dataset()
    job_stats = ds["job_stats"]
    elig = ds["eligibility"]

    fit_map = MAJOR_FIT.get(student.get("전공계열", ""), {})
    grade = student.get("학년", 2)
    years_left = max(0.5, 4 - grade + 0.5)
    social = bool(student.get("사회배려"))

    results = []
    for job, fit in fit_map.items():
        s = job_stats.get(job)
        if not s or not s["일반_가중경쟁률"]:
            continue

        gen_comp = s["일반_가중경쟁률"]
        comp_s = _competition_score(gen_comp)

        # 사회배려: 가짜 직무로 갈아타게 하지 않고, '이 직무의 사회배려 전형'
        # 경쟁률 갭만 정보로 제공한다(해당자에 한해 점수에 소폭 반영).
        soc_comp = s["사회배려_가중경쟁률"]
        social_applied = bool(social and soc_comp)
        if social_applied:
            comp_s = max(comp_s, _competition_score(soc_comp))

        size = _sample_score(s["일반_n"])           # '규모' 아님 → 데이터 표본량(신뢰도)

        score = (w["fit"] * fit + w["comp"] * comp_s + w["size"] * size)

        results.append(dict(
            직무=job, 적합도=round(score * 100),
            블라인드=job in BLIND_JOBS,
            구성=dict(전공적합=round(fit, 2), 경쟁여유=round(comp_s, 2),
                      표본량=round(size, 2)),
            사회배려적용=social_applied,
            데이터=dict(일반경쟁률=gen_comp, 사회배려경쟁률=soc_comp,
                       합격선평균=s["합격선평균"], 합격선표준편차=s["합격선표준편차"],
                       합격선기관=s.get("합격선기관", []),
                       분류=s["분류"]),
            로드맵=_roadmap(job, s, elig.get(job, {}), student,
                          years_left, social_applied),
        ))
    results.sort(key=lambda r: -r["적합도"])
    return results[:top_k]


def _roadmap(job, s, elig, student, years_left, social_applied):
    cut = s["합격선평균"]
    std = s["합격선표준편차"]
    if cut:
        buf = round(std) if std else 8
        target = f"필기 기준선 {round(cut)}점 + 버퍼 {buf}점 → {round(cut)+buf}점 목표"
    else:
        target = "합격선 공시 없음 — 공고별 확인 권장"

    have = set(student.get("보유자격", []))
    need = [c for c in TRACK_PREP.get(job, []) if not any(h in c for h in have)]

    # 어학: 임의값이 아니라 공고 임용조건의 실제 최저 토익을 인용
    toeic = student.get("어학", {}).get("토익")
    lang = None
    min_toeic = elig.get("토익최저")
    if min_toeic:
        msg = f"공고상 토익 최저 {min_toeic}점 사례 확인됨"
        if toeic:
            gap = "충족" if toeic >= min_toeic else f"{min_toeic-toeic}점 부족"
            msg += f" (현재 {toeic} — {gap})"
        lang = msg

    blind_note = None
    if job in BLIND_JOBS:
        blind_note = "이 직무는 전공·학력 제한이 없는 블라인드 채용이라, 전공보다 " \
                     "NCS 필기·경쟁률 관리가 핵심입니다."

    social_note = None
    if social_applied and s["사회배려_가중경쟁률"]:
        social_note = (f"사회배려(장애·보훈·취업지원) 전형 지원 시 이 직무의 경쟁률은 "
                       f"일반 {s['일반_가중경쟁률']}:1 → 사회배려 {s['사회배려_가중경쟁률']}:1로 "
                       f"낮아집니다. 증빙·자격을 미리 준비하세요.")

    return dict(
        필기목표=target,
        취득권장자격=need or ["보유 자격으로 충분"],
        어학=lang,
        준비기간=f"약 {years_left:.1f}년",
        블라인드안내=blind_note,
        사회배려안내=social_note,
    )


if __name__ == "__main__":
    ds = bd.build_dataset()
    samples = [
        dict(이름="A(전기전공 2학년)", 학년=2, 전공계열="전기·전자",
             보유자격=[], 어학={"토익": 700}, 사회배려=False),
        dict(이름="B(상경 3학년)", 학년=3, 전공계열="상경·행정·법",
             보유자격=["컴퓨터활용능력 1급"], 어학={"토익": 850}, 사회배려=False),
        dict(이름="C(영문 2학년·사회배려)", 학년=2, 전공계열="인문·사회·기타",
             보유자격=[], 어학={"토익": 790}, 사회배려=True),
    ]
    for smp in samples:
        print(f"\n=== {smp['이름']} ===")
        for r in recommend(smp, ds=ds):
            tag = " [블라인드]" if r["블라인드"] else ""
            print(f"  [{r['적합도']}점] {r['직무']}{tag}  일반 {r['데이터']['일반경쟁률']}:1  "
                  f"근거 {r['구성']}")
            rm = r["로드맵"]
            print(f"        {rm['필기목표']} | 자격 {rm['취득권장자격']}")
            if rm["어학"]: print(f"        어학: {rm['어학']}")
            if rm["사회배려안내"]: print(f"        ★ {rm['사회배려안내']}")
