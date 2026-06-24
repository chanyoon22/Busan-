"""
gemini_advisor.py — 데이터 근거 기반 AI 커리어 어드바이저 (v2)
=========================================================
추천 엔진의 결정론적 결과 + 공고 임용조건(eligibility) 원문을 컨텍스트로
받아, Gemini가 '제공된 부산 공공데이터 안에서만' 서술·상담한다.

설계 방어 포인트
  - '환각 금지(컨텍스트 밖 수치 지어내기 금지)'는 버그가 아니라 의도된 안전장치다.
    공기업 가산점·일정을 모델이 상상해 답하면 그게 사고다. 대신 v2는 답변 가능한
    근거 자체를 넓혔다 → 공고 임용조건(토익 최저·요구자격·전공제한 여부)을 주입.
  - 데이터에 없는 질문(예: 2026년 세부 가산점표)은 "공고로 확인"이라고 답하는 게
    정답이다. 이를 위해 폴백도 임용조건 근거를 인용하도록 강화했다.

API 키: st.secrets["GEMINI_API_KEY"] → 환경변수. 없으면 결정론적 폴백.
"""
from __future__ import annotations
import os, json, httpx

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _get_key():
    try:
        import streamlit as st
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def _call(prompt: str, system: str, max_tokens=8192, temp=0.4):
    key = _get_key()
    if not key:
        return None
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {"temperature": temp, "maxOutputTokens": max_tokens},
    }
    try:
        r = httpx.post(GEMINI_URL, json=body,
                       headers={"Content-Type": "application/json", "x-goog-api-key": key},
                       timeout=30)
        r.raise_for_status()
        cands = r.json().get("candidates", [])
        if not cands or "content" not in cands[0]:
            return None
        return cands[0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None


_SYSTEM = """당신은 부산 공공기관 취업을 준비하는 대학생의 커리어 코치입니다.
규칙:
1. 답변은 제공된 '데이터 컨텍스트'(경쟁률·합격선·임용조건)에만 근거합니다.
   컨텍스트에 없는 경쟁률·합격선·가산점·일정을 지어내지 마세요. 없으면
   "해당 수치는 데이터에 없어 공고로 확인이 필요하다"고 정직하게 답합니다.
2. 합격선·경쟁률은 단일 공고가 아니라 '과거 누적 통계'이며 예측이 아님을
   한 번은 분명히 합니다.
3. 사무·행정 등 블라인드 직무는 전공 제한이 없음을 정확히 안내하고, 전공과
   무관한 기술직으로 무리하게 갈아타라고 권하지 않습니다.
4. 임용조건 컨텍스트에 토익 최저·요구자격이 있으면 그 수치를 인용합니다.
5. 코드가 조회해 제공한 직무 데이터의 수치만 씁니다. 표에 없는 직무·수치를 새로
   만들어 답하지 마세요. 없으면 "데이터에 없어 공고로 확인이 필요하다"고 답합니다.
6. 담백하게, 핵심만. 마크다운 헤더 남발 금지."""



# ───────── 질문→직무 파싱 + 전체 데이터 결정론적 조회 (AI 상담 재설계) ─────────
# 핵심 원칙: 수치는 코드가 ds["job_stats"]에서 '직접 조회'하고, LLM은 문장화만 한다.
# 과거 구조는 추천(recs)에만 의존해, 추천에 없는 직무(예: 추천이 사무직인데
# "전기직 경쟁률은?")를 물으면 답할 데이터가 없었다. 이제 전체 직무를 조회한다.

# 사용자가 말로 쓰는 표현 → 표준 직무 카테고리. busan_data.JOB_GROUPS와 같은 어휘.
_JOB_ALIASES = {
    "사무·행정": ["사무", "행정", "운영", "경영", "회계", "법무", "비서", "총무", "일반직"],
    "전기": ["전기"],
    "기계": ["기계", "설비", "공조", "냉동"],
    "전산": ["전산", "it", "아이티", "정보처리", "개발", "프로그램"],
    "신호·통신": ["신호", "통신"],
    "토목·건축": ["토목", "건축", "조경", "도시계획", "감리"],
    "운전·운송": ["운전", "운송", "차량", "기관사"],
    "공무직·기능": ["공무직", "미화", "기능", "경비", "유지보수"],
    "청년인턴": ["인턴", "청년인턴", "체험형"],
}


def _detect_jobs(question: str, ds: dict) -> list:
    """질문에서 언급된 직무 카테고리를 찾는다(ds에 실제 통계가 있는 것만)."""
    if not ds:
        return []
    q = (question or "").lower().replace(" ", "")
    stats = ds.get("job_stats", {})
    found = []
    for job, aliases in _JOB_ALIASES.items():
        if job not in stats:
            continue
        if any(a.replace(" ", "") in q for a in aliases):
            found.append(job)
    return found


def _job_facts(job: str, ds: dict) -> dict:
    """한 직무의 모든 통계를 결정론적으로 묶는다(LLM이 지어낼 필요 없게)."""
    s = ds.get("job_stats", {}).get(job, {}) if ds else {}
    elig = ds.get("eligibility", {}).get(job, {}) if ds else {}
    return {
        "직무": job,
        "일반전형_경쟁률": s.get("일반_가중경쟁률"),
        "일반전형_표본수": s.get("일반_n"),
        "사회배려전형_경쟁률": s.get("사회배려_가중경쟁률"),
        "합격선평균": s.get("합격선평균"),
        "합격선출처기관": s.get("합격선기관", []),
        "경쟁분류": s.get("분류"),
        "공고근거_토익최저": elig.get("토익최저"),
        "공고근거_블라인드명시": elig.get("블라인드명시"),
    }


# 경쟁률·합격선 데이터가 '없는' 기관(교통·도시만 보유). 이 기관의 경쟁률/합격선을
# 물으면 추천 직무 숫자로 답하지 말고 '데이터 없음'으로 방어해야 한다(비환각).
_NO_RATE_INSTITUTIONS = ["시설공단", "환경공단", "관광공사"]
_SCHEDULE_KEYS = ["일정", "언제", "날짜", "며칠", "모집기간", "접수기간", "원서접수"]
_METRIC_KEYS = ["경쟁률", "합격선", "커트라인", "합격점", "필기점수"]


def _is_absent_query(question: str, jobs: list) -> str | None:
    """질문이 '우리에게 없는 데이터'를 묻는지 판정. 결측이면 사유 문자열, 아니면 None.
       (직무가 명확히 잡힌 보유 데이터 질의는 결측으로 보지 않는다.)"""
    q = (question or "")
    # 일정/날짜는 데이터에 없음
    if any(k in q for k in _SCHEDULE_KEYS):
        return "당해 채용 일정·날짜는 데이터에 없습니다(공고 확인 필요)."
    # 경쟁률/합격선 데이터가 없는 기관을 명시적으로 물은 경우(직무가 잡혀도 방어:
    # 우리 경쟁률·합격선은 교통·도시 2기관 값이라 타 기관 질의에 답이 안 됨)
    if any(m in q for m in _METRIC_KEYS) and any(i in q for i in _NO_RATE_INSTITUTIONS):
        return ("해당 기관의 경쟁률·합격선은 데이터에 없습니다(보유: 교통공사·도시공사 2기관). "
                "공고로 확인이 필요합니다.")
    return None


def _lookup(question: str, recs: list, ds: dict) -> dict:
    """질문에 맞는 데이터를 결정론적으로 조회.
       직무가 명시되면 그 직무를, 결측 질의면 '없음'으로 방어, 그 외엔 추천 직무로 폴백."""
    jobs = _detect_jobs(question, ds)
    absent = _is_absent_query(question, jobs)
    if absent:
        return {"직무명시": False, "결측": absent, "데이터": []}
    if jobs:
        return {"직무명시": True, "결측": None, "데이터": [_job_facts(j, ds) for j in jobs]}
    return {"직무명시": False, "결측": None, "데이터": [_job_facts(r["직무"], ds) for r in recs]}


def _ctx(student, recs, ds=None):
    elig = (ds or {}).get("eligibility", {}) if ds else {}
    return {
        "학생": {k: student.get(k) for k in ("학년", "전공계열", "보유자격", "어학", "사회배려")},
        "추천직무": [
            {"직무": r["직무"], "적합도": r["적합도"], "블라인드": r["블라인드"],
             "일반경쟁률": r["데이터"]["일반경쟁률"],
             "사회배려경쟁률": r["데이터"]["사회배려경쟁률"],
             "합격선평균": r["데이터"]["합격선평균"],
             "필기목표": r["로드맵"]["필기목표"],
             "권장자격": r["로드맵"]["취득권장자격"],
             "공고근거": elig.get(r["직무"], {})}
            for r in recs
        ],
    }


def narrate_roadmap(student: dict, recs: list, ds: dict = None) -> str:
    prompt = (f"데이터 컨텍스트:\n{json.dumps(_ctx(student, recs, ds), ensure_ascii=False, indent=2)}\n\n"
              "이 학생에게 1순위 직무를 중심으로 졸업까지의 준비 로드맵을 4~6문장으로 "
              "제시하세요. 왜 데이터상 유리한지 경쟁률·합격선 수치로 근거를 들고, "
              "블라인드 직무면 전공 무관함을 짚고, 자격·어학·필기 순서를 담으세요.")
    return _call(prompt, _SYSTEM) or _fallback_roadmap(student, recs)


def chat(student: dict, recs: list, question: str, ds: dict = None, history=None) -> str:
    # [재설계] 수치는 코드가 조회(_lookup), LLM은 그 수치를 문장으로만 정리.
    look = _lookup(question, recs, ds)
    if look.get("결측"):                       # 보유하지 않은 데이터는 LLM에 넘기지 않는다
        return look["결측"]
    학생요약 = {k: student.get(k) for k in ("학년", "전공계열", "보유자격", "어학", "사회배려")}
    prompt = (
        f"학생 정보: {json.dumps(학생요약, ensure_ascii=False)}\n"
        f"질문에서 코드가 직접 조회한 직무 데이터(이 수치만 사용, 새 수치 금지):\n"
        f"{json.dumps(look['데이터'], ensure_ascii=False, indent=1)}\n\n"
        f"학생 질문: {question}\n\n"
        + ("위 '질문 직무 데이터'의 수치(경쟁률·합격선·표본수·토익최저)만 인용해 "
           if look["직무명시"] else
           "질문에 특정 직무가 없어 추천 직무 데이터를 제공했습니다. 이 수치만 인용해 ")
        + "3~5문장으로 답하세요. 표에 없는 직무·가산점표·당해 일정 등은 "
          "'데이터에 없어 공고로 확인 필요'라고 정직하게 답하세요. 합격선은 과거 통계이며 "
          "예측이 아님을 한 번 짚으세요.")
    return _call(prompt, _SYSTEM, max_tokens=8192) or _fallback_chat(student, recs, question, ds)


def _fallback_roadmap(student: dict, recs: list) -> str:
    if not recs:
        return "전공계열을 선택하면 데이터 기반 직무 로드맵을 제시합니다."
    top = recs[0]
    d = top["데이터"]
    lines = [
        f"데이터상 1순위는 '{top['직무']}'(적합도 {top['적합도']}점)입니다. "
        f"일반전형 5년 누적 경쟁률 {d['일반경쟁률']}:1"
        + (f", 평균 필기합격선 {d['합격선평균']}점" if d['합격선평균'] else "") + ".",
    ]
    if top["블라인드"]:
        lines.append("이 직무는 전공 제한이 없는 블라인드 채용이라, 전공보다 NCS 필기 점수가 당락을 가릅니다.")
    lines.append(f"준비 순서: {', '.join(top['로드맵']['취득권장자격'])} → {top['로드맵']['필기목표']}.")
    if top["로드맵"]["어학"]:
        lines.append(top["로드맵"]["어학"] + ".")
    if top["로드맵"]["사회배려안내"]:
        lines.append(top["로드맵"]["사회배려안내"])
    lines.append("※ 위 수치는 과거 5년 공시 통계이며 예측이 아닙니다. 당해연도 채용규모·기준은 공고로 재확인하세요.")
    return " ".join(lines)


def _fallback_chat(student: dict, recs: list, question: str, ds: dict = None) -> str:
    # [재설계] 폴백도 결정론적 조회를 사용 → API 키 없어도 질문 직무를 정확히 답한다.
    look = _lookup(question, recs, ds)
    if look.get("결측"):                       # 우리에게 없는 데이터 → 가짜 수치 대신 방어
        return look["결측"]
    facts = look["데이터"]
    if not facts:
        return "먼저 프로필을 제출하면 데이터 근거로 답해 드립니다."
    parts = []
    for f in facts:
        if f["일반전형_경쟁률"] is None:
            parts.append(f"'{f['직무']}'은(는) 경쟁률 데이터가 충분치 않습니다.")
            continue
        seg = (f"'{f['직무']}'의 일반전형 누적 경쟁률은 {f['일반전형_경쟁률']}:1"
               f"(표본 {f['일반전형_표본수']}건)")
        if f["합격선평균"]:
            seg += f", 평균 합격선 {f['합격선평균']}점"
            if len(f["합격선출처기관"]) > 1:
                seg += "(기관 혼합 — 직접 비교 주의)"
        if f["사회배려전형_경쟁률"]:
            seg += f". 사회배려 전형은 {f['사회배려전형_경쟁률']}:1로 더 낮습니다"
        parts.append(seg + ".")
    tail = (" 위 수치는 과거 공시 통계이며 예측이 아닙니다. 가산점표·당해 일정 등 "
            "데이터에 없는 항목은 각 기관 공고로 확인하세요.")
    return " ".join(parts) + tail
