"""
scoring.py — 공고 근거 기반 점수·자격 엔진 (신규)
=========================================================
업로드된 2026년 부산교통공사 실제 공고 PDF에서 추출한 '검증 가능한' 규칙만
인코딩한다. 임의값(하드코딩)이 아니라 공고 원문 출처를 주석으로 남긴다.

근거 공고
  - 제2026-245호 「2026년 체험형 청년인턴 공개채용」  → 서류 정량 가점 테이블·가산점
  - 제2026-154호 「2026년 장애인 체험형 청년인턴」     → 장애인 전형 서류평가·가산점
  - 제2026-182호 「2026년 상반기 기능인재 공개채용」   → 고졸 기능인재(대학생 불가)
  - 도시공사/관광공사 채용정보 임용조건                → 어학 기준(토익·오픽·토플·텝스 등)

핵심: 여기 없는 수치(예: 정규직 직무별 세부 가점표)는 데이터에 없는 것이며,
지어내지 않는다. '청년인턴 서류 점수'는 공고가 명시한 범위에서만 계산한다.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────
# 1) 어학: 다종 시험 지원 + 공고 기준 환산
# ─────────────────────────────────────────────────────────────
# 지원 시험 종류 (입력 위젯용)
LANG_TESTS = ["토익(TOEIC)", "토익스피킹(TOEIC S)", "오픽(OPIc)",
              "텝스(TEPS)", "토플(TOEFL iBT)"]

# 공고가 직접 명시한 '동일 기준' 앵커(출처: 도시공사 행정직·관광공사 일반직 공고)
#   · 도시공사 행정직: 토익 700 = 오픽 IM1 = 토플(iBT) 79
#   · 관광공사 일반직: 토익 800 = 토플 91 = TEPS 650
# 아래 표는 위 앵커 + 공개된 표준 환산을 보수적으로 결합한 '참고 환산표'다.
# (정확한 인정 기준은 항상 당해 공고가 우선임을 앱에서 명시한다)
#   레벨별 토익 등가점수와 각 시험의 대응값
LANG_EQUIV = [
    # (대표 TOEIC, TOEIC_S, OPIc,  TEPS(new), TOEFL_iBT)
    (700, 120, "IM1", 264, 79),
    (750, 130, "IM2", 286, 85),
    (800, 140, "IH",  327, 91),
    (850, 150, "IH",  364, 96),
    (900, 160, "AL",  386, 100),
]
# 공기업 사무·행정의 흔한 '지원 가능' 최저 앵커(공고 근거: 토익 700/오픽 IM1/토플 79)
LANG_MIN_ANCHOR = dict(토익=700, 토플=79, 오픽="IM1", 텝스=264, 토스=120)


def toeic_equivalent(test_key: str, value) -> int | None:
    """입력한 어학 점수를 'TOEIC 등가점수'로 환산(참고용). 모르면 None."""
    if value in (None, "", 0):
        return None
    try:
        if test_key.startswith("토익(") :            # TOEIC 원점수
            return int(value)
        if test_key.startswith("토익스피킹"):
            col = 1
        elif test_key.startswith("오픽"):
            # OPIc은 등급 문자열 비교
            order = ["NL","NM","NH","IL","IM1","IM2","IM3","IH","AL"]
            v = str(value).upper().replace(" ", "")
            if v == "IM":            # 등급 없는 'IM'(공고 표기) → IM1로 간주
                v = "IM1"
            best = None
            for toeic, ts, op, teps, toefl in LANG_EQUIV:
                if v in order and op in order and order.index(v) >= order.index(op):
                    best = toeic
            return best
        elif test_key.startswith("텝스"):
            col = 3
        elif test_key.startswith("토플"):
            col = 4
        else:
            return None
        val = float(value)
        best = None
        for row in LANG_EQUIV:
            if val >= row[col]:
                best = row[0]
        return best
    except (TypeError, ValueError):
        return None


def lang_summary(lang_scores: dict) -> dict:
    """여러 시험 입력 → 최고 TOEIC 등가 + 사무·행정 최저기준(700) 충족 여부."""
    equivs = []
    for test, val in (lang_scores or {}).items():
        eq = toeic_equivalent(test, val)
        if eq:
            equivs.append((test, eq))
    best = max((e for _, e in equivs), default=None)
    return dict(
        입력=equivs,
        토익등가=best,
        사무행정최저충족=(best is not None and best >= 700),
        기준출처="도시공사 행정직 공고(토익 700·오픽 IM1·토플 79 동일 인정)",
    )


# ─────────────────────────────────────────────────────────────
# 2) 청년인턴 서류전형 정량 가점 (출처: 제2026-245호)
# ─────────────────────────────────────────────────────────────
# 평가방법(공고 원문): 항목 내 '가장 유리한 자격증 1개'만 적용, 항목 간 합산.
# 동일 항목(IT 등) 내 복수 보유 시 중복 불가 — 최고점 1개만.
INTERN_CERT_TABLE = {
    "IT": {            # 최고 20점
        "정보처리기사": 20,
        "정보처리산업기사": 15,
        "사무자동화산업기사": 10,
    },
    "사무": {          # 최고 20점
        "컴퓨터활용능력 1급": 20,
        "컴퓨터활용능력 2급": 10,
        "워드프로세서": 5,
    },
    "한국사": {        # 최고 15점
        "한국사능력검정 1급": 15,
        "한국사능력검정 2급": 10,
    },
}
INTERN_QUANT_MAX = 55     # 정량 만점(공고)
INTERN_QUAL_MAX = 45      # 정성 만점(자기소개15+지원동기15+직무목표15)
INTERN_GRADE = {"S": 15, "A": 13, "B": 11, "C": 9, "D": 7}   # 정성 등급별


def intern_quant_score(certs: list[str]) -> dict:
    """보유 자격증 → 청년인턴 서류 '정량' 점수(55점 만점) 계산."""
    have = set(certs or [])
    breakdown = {}
    total = 0
    for item, table in INTERN_CERT_TABLE.items():
        # 해당 항목에서 보유한 자격 중 최고점 1개만
        owned = [(c, p) for c, p in table.items() if c in have]
        if owned:
            best = max(owned, key=lambda t: t[1])
            breakdown[item] = dict(자격=best[0], 점수=best[1])
            total += best[1]
        else:
            breakdown[item] = dict(자격=None, 점수=0)
    return dict(정량점수=total, 만점=INTERN_QUANT_MAX, 세부=breakdown)


# ─────────────────────────────────────────────────────────────
# 3) 가산점 (출처: 제2026-245호 / 제2026-154호)
# ─────────────────────────────────────────────────────────────
# · 취업지원대상자: 시험단계별 만점의 5% 또는 10%(보훈부 증명서 비율), 상한제 30%
# · 장애인: 서류전형 만점의 5% (서류 4할 이상 득점 시 적용)
# · 취업지원 + 장애인 중복 시 합산 적용
def bonus_points(social: dict, stage_max: int = 100) -> dict:
    """social = {취업지원대상자:5|10|0, 장애인:bool}"""
    social = social or {}
    notes = []
    pct = 0
    veteran = int(social.get("취업지원대상자", 0) or 0)
    if veteran in (5, 10):
        pct += veteran
        notes.append(f"취업지원대상자 {veteran}% (보훈부 증명서 기준, 상한제 30%)")
    if social.get("장애인"):
        pct += 5
        notes.append("장애인 5% (서류전형, 4할 이상 득점 시)")
    return dict(가산비율=pct, 가산점=round(stage_max * pct / 100, 1), 근거=notes)


# ─────────────────────────────────────────────────────────────
# 4) 거주지(지역) 요건 — '출신대학'이 아니라 '주민등록' 기준
# ─────────────────────────────────────────────────────────────
# 출처: 제2026-245호/154호 — 부산·울산·경남 주민등록(면접최종일까지) 또는
#       과거 합산 36개월 이상. 블라인드 채용이라 출신학교는 오히려 기재 금지.
RESIDENCY_REGIONS = ["부산광역시", "울산광역시", "경상남도", "그 외(요건 미충족)"]

def residency_ok(region: str, months_total: int = 0) -> dict:
    eligible = region in ("부산광역시", "울산광역시", "경상남도") or months_total >= 36
    return dict(
        충족=eligible,
        설명=("현재 부산·울산·경남 주민등록(또는 합산 36개월 이상) → 응시 자격 충족"
              if eligible else
              "부산·울산·경남 주민등록 요건 미충족 → 다수 부산 공기업 응시 불가 가능"),
        주의="이 요건은 '출신대학'이 아니라 '거주지(주민등록)' 기준이며, "
             "블라인드 채용상 출신학교 가점은 없음(공고 붙임2).",
    )


# ─────────────────────────────────────────────────────────────
# 5) 전체 자격증 마스터 목록 (입력 위젯용, 대폭 확장)
# ─────────────────────────────────────────────────────────────
CERT_MASTER = [
    # 청년인턴 정량평가 대상(공고 명시)
    "정보처리기사", "정보처리산업기사", "사무자동화산업기사",
    "컴퓨터활용능력 1급", "컴퓨터활용능력 2급", "워드프로세서",
    "한국사능력검정 1급", "한국사능력검정 2급",
    # 기술직 정규직 관련
    "전기기사", "전기산업기사", "일반기계기사", "공조냉동기계기사",
    "토목기사", "건축기사", "정보통신기사", "전자기사", "전산직(SQLD/ADsP)",
    "SQLD", "ADsP",
    # 운전직
    "제2종 전기차량 운전면허",
]


# ═════════════════════════════════════════════════════════════
# 6) 공고·분야별 어학 적격 판정 (글로벌 환산표 대신 '공고 원문 컷'을 직접 비교)
# ═════════════════════════════════════════════════════════════
# [왜 새로 만드나]
#   LANG_EQUIV(위 1번)는 '참고용 환산표'다. 그런데 실제 공고는 동일 TOEIC에
#   대해서도 타 시험 컷이 제각각이다. 예) 관광공사 일반계약직 제2026-42호는
#   TOEIC 800 = TOEFL(iBT) 69 = New TEPS 228 = OPIc IM 으로 명시하는데,
#   핸드오프 부록의 관광공사 '일반직'은 TOEIC 800 = TOEFL 91 = TEPS 650 이다.
#   즉 같은 기관·같은 TOEIC라도 공고에 따라 TOEFL 컷이 69 vs 91로 다르다.
#   → 글로벌 환산으로 '충족/미달'을 판정하면 틀린다. 적격 판정은 반드시
#     해당 공고가 명시한 시험별 컷을 'OR(하나만 충족하면 됨)'로 직접 비교한다.

# 말하기 시험 등급 순서(OPIc·TOEIC Speaking 공용 비교축). 공고가 'IM 이상'처럼
# 등급으로 요구하므로 숫자 비교가 아니라 등급 인덱스 비교를 한다.
SPOKEN_ORDER = ["NL", "NM", "NH", "IL", "IM1", "IM2", "IM3", "IH", "AL"]


def _num(x):
    """문자/콤마 섞인 점수 입력을 float으로. 실패 시 None."""
    if x in (None, "", 0):
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _spoken_rank(grade) -> int | None:
    g = str(grade).upper().replace(" ", "")
    if g == "IM":                  # 등급 없는 IM → IM1로 간주(공고 표기 호환)
        g = "IM1"
    return SPOKEN_ORDER.index(g) if g in SPOKEN_ORDER else None


def _spoken_ok(user_grade, req_grade) -> bool:
    u, r = _spoken_rank(user_grade), _spoken_rank(req_grade)
    return u is not None and r is not None and u >= r


# 사용자 입력 위젯 키(LANG_TESTS) → 공고 요건 dict의 시험 키 매핑 규칙은
# lang_requirement_met 안에서 prefix로 처리한다.
#   요건 dict 예: {"TOEIC":800,"TOEFL_iBT":69,"TEPS_new":228,"TOEIC_S":"IM3","OPIc":"IM"}
def lang_requirement_met(requirement: dict | None, lang_scores: dict) -> dict:
    """이 분야 어학요건(requirement)을 사용자 어학(lang_scores)이 충족하는지 판정.
       - requirement가 None/빈dict → '별도 어학요건 없음'(공통응시자격만으로 적격).
       - 여러 시험은 OR 관계: 하나라도 컷 이상이면 적격.
       - TEPS는 현행 'New TEPS' 기준으로 비교한다(구 TEPS 점수는 환산 필요).
    """
    if not requirement:
        return dict(요건있음=False, 적격=True, 충족시험=[],
                    사유="이 분야는 공고에 별도 어학요건이 명시되지 않음 → 공통응시자격만 충족하면 적격")
    met = []
    for test_key, val in (lang_scores or {}).items():
        k = str(test_key)
        if k.startswith("토익("):                       # TOEIC(원점수)
            req, v = requirement.get("TOEIC"), _num(val)
            if req and v is not None and v >= req:
                met.append(f"TOEIC {int(v)} ≥ {req}")
        elif k.startswith("토익스피킹"):                 # TOEIC Speaking(등급)
            req = requirement.get("TOEIC_S")
            if req and _spoken_ok(val, req):
                met.append(f"TOEIC S {str(val).upper()} ≥ {req}")
        elif k.startswith("오픽"):                       # OPIc(등급)
            req = requirement.get("OPIc")
            if req and _spoken_ok(val, req):
                met.append(f"OPIc {str(val).upper()} ≥ {req}")
        elif k.startswith("텝스"):                       # TEPS(New 기준)
            req = requirement.get("TEPS_new") or requirement.get("TEPS")
            v = _num(val)
            if req and v is not None and v >= req:
                met.append(f"New TEPS {int(v)} ≥ {req}")
        elif k.startswith("토플"):                       # TOEFL iBT
            req, v = requirement.get("TOEFL_iBT"), _num(val)
            if req and v is not None and v >= req:
                met.append(f"TOEFL(iBT) {int(v)} ≥ {req}")
    return dict(
        요건있음=True,
        적격=bool(met),
        충족시험=met,
        사유=("요건 충족(" + ", ".join(met) + ")") if met
             else "요구 어학시험 중 컷을 충족하는 성적이 없음 → 이 분야는 응시 불가",
    )


# ═════════════════════════════════════════════════════════════
# 7) 관광공사 일반계약직 공고 객체 (출처: 제2026-42호, 2026-03-13)
# ═════════════════════════════════════════════════════════════
# 모든 값은 공고 원문에서 추출. 추정·보간 없음.
# ※ 어학요건이 None인 분야는 '공고에 분야별 어학요건 미기재'라는 뜻이다.
#   '다국어 SNS마케팅 지원'은 이름상 어학이 필요해 보이지만, 공고는 이 분야에
#   별도 어학요건을 명시하지 않았다 → 임의로 요건을 만들어 넣지 않는다(1원칙).
TOURISM_CONTRACT_2026_42 = {
    "공고": "부산관광공사 일반계약직 채용 (공고 제2026-42호)",
    "기관": "부산관광공사",
    "고용형태": "일반계약직",
    "계약기간": "2026-04-13 ~ 2026-12-31",
    "보수_월": 2_565_480,                 # 세전 기본급(부산시 2026 생활임금)
    "블라인드": True,
    "총원": 7,
    "전형": "서류(적격심사) → 면접(블라인드)",   # 서류는 점수가 아니라 적격여부 판단
    "면접컷": 70,                          # 면접 70점 이상자 중 고득점순
    "출처": "공고 제2026-42호 (2026-03-13 공고)",
    "분야": {
        "부산관광기업지원센터 운영": dict(인원=4, 근무지="영도구", 어학요건=None),
        "페스티벌 시월 홍보마케팅":  dict(인원=1, 근무지="부산진구",
            어학요건={"TOEIC": 800, "TOEFL_iBT": 69, "TEPS_new": 228,
                     "TOEIC_S": "IM3", "OPIc": "IM"}),
        "다국어 SNS마케팅 지원":     dict(인원=1, 근무지="부산진구", 어학요건=None),
        "남부권 광역관광개발사업":   dict(인원=1, 근무지="부산진구",
            어학요건={"TOEIC": 600, "TOEFL_iBT": 69, "TEPS_new": 228,
                     "TOEIC_S": "IM3", "OPIc": "IM"}),
    },
}


def field_eligibility(posting: dict, field: str, lang_scores: dict) -> dict:
    """공고의 특정 분야에 대한 어학 적격 + 가점 적용가능성 종합 판정."""
    f = posting["분야"].get(field, {})
    lang = lang_requirement_met(f.get("어학요건"), lang_scores)
    bonus = bonus_applicable_for_field(f.get("인원"))
    return dict(분야=field, 인원=f.get("인원"), 근무지=f.get("근무지"),
                어학=lang, 가점적용=bonus, 어학요건=f.get("어학요건"))


def bonus_applicable_for_field(num_select: int | None, num_applicants: int | None = None) -> dict:
    """가점합격률(30%) 규정: 선발예정 3명 이하면 가점 미적용.
       단 '응시인원 ≤ 채용예정인원'이면 적용(공고 단서). 지원 전이라 응시인원은
       대개 미지(None) → 그 경우 '원칙 미적용(조건부 적용 가능)'으로 정직하게 안내."""
    if num_select is None:
        return dict(적용="불명", 설명="선발인원 정보 없음")
    if num_select >= 4:
        return dict(적용="적용", 설명=f"선발 {num_select}명(4명 이상) → 가점 적용")
    # 3명 이하
    if num_applicants is not None and num_applicants <= num_select:
        return dict(적용="적용", 설명=f"선발 {num_select}명이나 응시인원이 채용인원 이하 → 가점 적용")
    return dict(적용="원칙 미적용",
                설명=f"선발 {num_select}명(3명 이하) → 원칙상 가점 미적용. "
                     f"단 응시인원이 채용예정인원 이하이면 적용됨(공고 단서).")


# ═════════════════════════════════════════════════════════════
# 8) 면접 배점 시뮬레이터 (출처: 제2026-42호 붙임 평가기준표)
# ═════════════════════════════════════════════════════════════
# 면접 100점 = 직업기초능력 60 + 직무수행능력 40. 합격: 면접 70점 이상자 중
# 고득점순. 가점: 취업지원대상자 면접 만점의 5/10%(가장 유리한 1개), 단 40점
# 이상 득점자만 적용. 동점 시 취업지원대상자 우선.
INTERVIEW_RUBRIC_BTO_CONTRACT = {
    "직업기초능력(60)": {
        "조직이해·직업윤리": 20,
        "자원관리·문제해결": 20,
        "의사소통·대인관계": 20,
    },
    "직무수행능력(40)": {
        "지식·정보·기술": 20,
        "사업·업무관리": 20,
    },
}
INTERVIEW_PASS_CUT = 70


def interview_score_bto_contract(raw_100, social: dict | None = None) -> dict:
    """면접 원점수(본인 추정, 0~100)와 가산 정보로 가점 포함 점수·컷 통과를 계산.
       ※ 면접 원점수는 사용자가 가정한 값이며 '예측'이 아니다(공고 규정만 적용)."""
    raw = _num(raw_100)
    raw = 0.0 if raw is None else max(0.0, min(100.0, raw))
    b = bonus_points(social or {}, stage_max=100)        # 취업지원/장애인 가산비율
    # 공고: 우대가점은 100점 만점의 40점 이상 득점자에게만 적용
    applied = b["가산점"] if raw >= 40 else 0.0
    final = round(raw + applied, 1)
    return dict(
        면접원점수=round(raw, 1),
        가산비율=b["가산비율"],
        가산점적용=applied,
        가산근거=b["근거"],
        최종점수=final,                                   # 정렬(고득점순)에 쓰이는 점수
        컷=INTERVIEW_PASS_CUT,
        컷통과=raw >= INTERVIEW_PASS_CUT,                  # 컷은 면접 원점수 기준
        주의="면접 원점수는 본인 추정 입력값(예측 아님). 70점 컷·가점 규칙만 공고 근거. "
             "가점은 40점 이상 득점자에게만 적용되며, 최종 선발은 가점 포함 고득점순.",
    )


# ═════════════════════════════════════════════════════════════
# 자체 검증 (data/ 의존 없음 — 순수 규칙이라 단독 실행으로 검증 가능)
# ═════════════════════════════════════════════════════════════
if __name__ == "__main__":
    P = TOURISM_CONTRACT_2026_42
    print("=== 관광공사 일반계약직 제2026-42호 분야별 적격 판정 ===\n")

    cases = [
        ("TOEIC 790 보유자", {"토익(TOEIC)": 790}),
        ("TOEIC 820 보유자", {"토익(TOEIC)": 820}),
        ("OPIc IH 보유자",   {"오픽(OPIc)": "IH"}),
        ("OPIc IL 보유자",   {"오픽(OPIc)": "IL"}),
        ("어학 미입력",       {}),
    ]
    for who, ls in cases:
        print(f"[{who}]")
        for field in P["분야"]:
            r = field_eligibility(P, field, ls)
            mark = "○ 적격" if r["어학"]["적격"] else "✗ 부적격"
            print(f"  - {field}({r['인원']}명): {mark} — {r['어학']['사유']}")
            print(f"       가점: {r['가점적용']['적용']} ({r['가점적용']['설명']})")
        print()

    print("=== 면접 점수 시뮬레이션 ===")
    for raw, soc in [(72, {"취업지원대상자": 5}), (68, {"취업지원대상자": 10}),
                     (38, {"취업지원대상자": 10}), (85, {})]:
        s = interview_score_bto_contract(raw, soc)
        print(f"  원점수 {s['면접원점수']} +가점 {s['가산점적용']} = 최종 {s['최종점수']} "
              f"| 70컷 {'통과' if s['컷통과'] else '미달'}")
