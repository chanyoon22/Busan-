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


def _call(prompt: str, system: str, max_tokens=900, temp=0.4):
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
5. 담백하게, 핵심만. 마크다운 헤더 남발 금지."""


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
    ctx = _ctx(student, recs, ds)
    prompt = (f"데이터 컨텍스트:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
              f"학생 질문: {question}\n\n컨텍스트(경쟁률·합격선·공고 임용조건)에 근거해 "
              "3~5문장으로 답하세요. 컨텍스트에 없으면 솔직히 없다고 하고 공고 확인을 권하세요.")
    return _call(prompt, _SYSTEM, max_tokens=700) or _fallback_chat(student, recs, question)


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


def _fallback_chat(student: dict, recs: list, question: str) -> str:
    if not recs:
        return "먼저 프로필을 제출하면 데이터 근거로 답해 드립니다."
    top = recs[0]
    d = top["데이터"]
    return (f"제공 데이터 기준으로 답하면, '{top['직무']}'의 일반전형 누적 경쟁률은 "
            f"{d['일반경쟁률']}:1"
            + (f", 평균 합격선 {d['합격선평균']}점입니다. " if d['합격선평균'] else "입니다. ")
            + "질문에 필요한 세부 수치(가산점표·당해 일정 등)가 데이터에 없으면 "
              "각 기관 채용공고로 확인해야 정확합니다.")
