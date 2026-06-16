"""
gemini_advisor.py — 데이터 근거 기반 AI 커리어 어드바이저
=========================================================
추천 엔진(recommender)의 결정론적 결과를 컨텍스트로 받아, Gemini가
'제공된 부산 공공데이터 수치 안에서만' 로드맵 서술과 Q&A를 생성한다.
환각을 막기 위해 모델에 외부지식 추정을 금지하고 근거 수치를 강제한다.

API 키는 st.secrets["GEMINI_API_KEY"] → 환경변수 순으로 로드한다.
키가 없으면 결정론적 폴백 서술을 반환한다(데모/오프라인 대비).
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
        return None  # 폴백 유도
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
반드시 아래 규칙을 지키세요.
1. 답변은 제공된 '데이터 컨텍스트'의 수치에만 근거합니다. 컨텍스트에 없는
   경쟁률·합격선·연봉·일정을 지어내지 마세요. 모르면 모른다고 하세요.
2. 단일 공고가 아니라 '5년 누적 구조'로 말합니다. 과거 데이터의 시차
   한계를 한 번은 솔직히 언급하세요.
3. 학생의 전공·학년에 맞는 현실적 준비 순서(자격→어학→필기)를 제시합니다.
   전공과 무관한 직렬로 무리하게 갈아타라고 권하지 마세요.
4. 사회배려(장애·취업지원·보훈) 안내가 컨텍스트에 있으면 정중히 반영합니다.
5. 과장·영업 문구 없이 담백하게. 마크다운 헤더 남발 금지, 핵심만."""


def narrate_roadmap(student: dict, recs: list) -> str:
    """추천 결과 → 학생 맞춤 로드맵 서술 (Gemini, 없으면 폴백)."""
    ctx = {
        "학생": {k: student.get(k) for k in ("학년", "전공계열", "보유자격", "어학", "사회배려")},
        "추천직렬": [
            {"직렬군": r["직렬군"], "적합도": r["적합도"], "근거": r["구성"],
             "5년평균경쟁률": r["데이터"]["평균경쟁률"], "평균합격선": r["데이터"]["평균합격선"],
             "채용추세": r["데이터"]["추세"],
             "필기목표": r["로드맵"]["필기목표"],
             "취득권장": r["로드맵"]["취득권장자격"],
             "사회배려안내": r["로드맵"]["사회배려안내"]}
            for r in recs
        ],
    }
    prompt = (f"데이터 컨텍스트:\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n\n"
              "이 학생에게 1순위 직렬을 중심으로, 지금부터 졸업까지의 준비 로드맵을 "
              "4~6문장으로 제시하세요. 왜 그 직렬이 데이터상 유리한지 수치로 근거를 들고, "
              "구체적 자격·어학·필기 목표 순서를 담으세요.")
    out = _call(prompt, _SYSTEM)
    return out or _fallback_roadmap(student, recs)


def chat(student: dict, recs: list, question: str, history=None) -> str:
    """자유 질문 응답 (데이터 근거)."""
    ctx = {"학생전공계열": student.get("전공계열"), "학년": student.get("학년"),
           "추천결과": [{"직렬군": r["직렬군"], "적합도": r["적합도"],
                       "평균경쟁률": r["데이터"]["평균경쟁률"],
                       "평균합격선": r["데이터"]["평균합격선"],
                       "추세": r["데이터"]["추세"]} for r in recs]}
    prompt = (f"데이터 컨텍스트:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
              f"학생 질문: {question}\n\n컨텍스트 수치에 근거해 3~5문장으로 답하세요.")
    out = _call(prompt, _SYSTEM, max_tokens=700)
    return out or "지금은 AI 응답을 불러올 수 없습니다. 화면의 적합도·로드맵 데이터를 참고해 주세요."


def _fallback_roadmap(student: dict, recs: list) -> str:
    """API 키가 없을 때의 결정론적 서술 (데모 안정성)."""
    if not recs:
        return "전공계열을 선택하면 데이터 기반 직렬 로드맵을 제시합니다."
    top = recs[0]
    d = top["데이터"]
    lines = [
        f"데이터상 1순위는 '{top['직렬군']}' (적합도 {top['적합도']}점)입니다. "
        f"최근 5년 평균 경쟁률 {d['평균경쟁률']}:1, 평균 필기합격선 "
        f"{d['평균합격선']}점, 채용추세 {d['추세']}.",
        f"준비 순서: {', '.join(top['로드맵']['취득권장자격'])} → {top['로드맵']['필기목표']}.",
    ]
    if top["로드맵"]["사회배려안내"]:
        lines.append(top["로드맵"]["사회배려안내"])
    lines.append("※ 본 추천은 과거 5년 공시 데이터 기반의 구조적 경향이며, "
                 "당해연도 채용규모 변동은 공고로 재확인이 필요합니다.")
    return " ".join(lines)
