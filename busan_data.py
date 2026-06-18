"""
busan_data.py — 부산 공공기관 채용 데이터 엔진 (v2, 구조 재설계)
===================================================================
부산교통공사·부산도시공사·부산관광공사 공공데이터(data.go.kr)를 하나의
정규화 스키마로 통합(ETL)하고, 직무 적합 추천·경쟁률 진단·합격선 통계의
근거 데이터를 만든다.

v1 대비 핵심 수정 (심사 방어용)
  1) [스키마] 직무(job)와 전형(track)을 분리한다.
     - v1은 '장애인/보훈/취업지원' 전형을 '사회배려'라는 가짜 직무로 묶어
       실제 직무(운영·전기·기계…)를 소거했다. v2는 (직무 × 전형) 2축으로
       저장해, '전기직-일반' vs '전기직-사회배려' 경쟁률을 따로 본다.
  2) [통계] 직무별 경쟁률을 '단순평균'이 아니라 '가중평균'(총지원/총선발)으로
     계산한다. 1명 뽑아 100:1 난 소규모 공고가 평균을 오염시키지 않는다.
  3) [정직성] '합격선 예측/백테스트/MAE'라는 표현을 버린다. 실제 로직은
     과거 평균이므로 '합격선 통계(평균·표준편차·기준선)'로 명명하고,
     합격선이 부산교통공사에만 존재한다는 사실(도시공사·관광공사 미제공)을
     데이터에 명시한다.
  4) [근거 확장] 채용정보의 '임용조건' 원문(토익 기준·자격·전공제한 여부)을
     추출해 AI 상담의 비환각 근거로 쓴다.

산출물:
  load_rate_records()  → (직무·전형) 분리된 경쟁률 레코드
  load_eligibility()   → 직무별 임용조건 원문 근거(어학/자격/전공제한)
  build_dataset()      → 앱·상담이 쓰는 통합 집계 dict
"""
from __future__ import annotations
import csv, re, os, json, statistics
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 실제 업로드 파일명이 기관마다 달라, 후보명을 순서대로 탐색한다.
FILE_CANDIDATES = {
    "humetro_rate":   ["humetro_rate.csv", "부산교통공사_채용경쟁률_현황_20241231.csv"],
    "humetro_hire":   ["humetro_hire.csv", "부산교통공사_신규채용인원_현황_20241231.csv"],
    "humetro_notice": ["humetro_notice.csv", "부산교통공사_채용정보_20240425.csv"],
    "bmc_rate":       ["bmc_rate.xlsx", "3_채용경쟁률현황_20241231.xlsx"],
    "bmc_hire":       ["bmc_hire.csv", "2_신규채용현황_20241231.csv"],
    "bmc_notice":     ["bmc_notice.csv", "1_채용정보_20241231.csv"],
    "bto_notice":     ["bto_notice.csv", "부산관광공사__채용정보_20250804.csv"],
    "eco_hire":       ["eco_hire.csv", "부산환경공단_신규채용인원_현황_20241231.csv"],
    "fac_hire":       ["fac_hire.csv", "부산시설공단_신규채용인원_현황_20241231.csv"],
}

def _path(key):
    for name in FILE_CANDIDATES[key]:
        p = os.path.join(DATA_DIR, name)
        if os.path.exists(p):
            return p
    return os.path.join(DATA_DIR, FILE_CANDIDATES[key][0])  # 없으면 첫 후보(에러 메시지용)


# ───────────────────────── 저수준 파서 ─────────────────────────
def _read_csv(path):
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            with open(path, encoding=enc) as f:
                return list(csv.reader(f))
        except (UnicodeDecodeError, LookupError):
            continue
    raise IOError(f"인코딩 판별 실패: {path}")

def _read_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    return [list(r) for r in wb.active.iter_rows(values_only=True)]

def _int(x):
    try: return int(float(str(x).replace(",", "").strip()))
    except (TypeError, ValueError): return None

def _float(x):
    try: return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError): return None

def _ratio(x):
    """'100.6:1', '160 : 1' → 100.6"""
    if x is None: return None
    m = re.search(r"([\d.]+)\s*:\s*1", str(x).replace(" ", ""))
    return float(m.group(1)) if m else None


# ───────────────── 1축: 직무(job) 정규화 ─────────────────
# 전형 키워드(장애/보훈/취업지원)는 절대 직무 판정에 쓰지 않는다.
# 순서 = 우선순위. 구체적·특수 고용형태를 먼저, 광의의 '사무·행정'을 마지막에.
JOB_GROUPS = [
    ("청년인턴",   ["인턴", "체험형"]),
    ("공무직·기능", ["공무직", "미화", "시설", "유지보수", "중정비", "안전문",
                    "관리사무소", "기능", "환경", "경비"]),
    ("전산",       ["전산", "전산직", "정보화", "정보시스템"]),
    ("신호·통신",  ["신호", "통신"]),
    ("전기",       ["전기"]),
    ("기계",       ["기계", "공조", "냉동", "설비"]),
    ("토목·건축",  ["토목", "건축", "조경", "도시계획", "감리"]),
    ("운전·운송",  ["운전", "운송", "2종", "차량운영"]),
    ("사무·행정",  ["운영", "행정", "경영", "경제", "회계", "법무", "비서",
                    "안내", "기록물", "사무", "관광", "일반직", "일반계약직",
                    "전문계약직", "마케팅", "홍보"]),
]

def normalize_job(*texts):
    """직무명/공고명만 받아 직무 카테고리를 판정한다. 전형은 넘기지 않는다."""
    blob = " ".join(str(t) for t in texts if t)
    for group, keys in JOB_GROUPS:
        if any(k in blob for k in keys):
            return group
    return "기타"


def load_job_overrides():
    """직무분류_검증표.csv의 '수동검수_정정' 칸이 채워진 행을 override 맵으로 반환한다.
       자동분류(키워드 기반)는 오분류 위험이 있으므로, 143행 전수검수에서 사람이
       바로잡은 값을 ETL이 자동분류보다 '우선' 적용한다(정직성·투명성). 칸이 비어
       있으면 빈 맵 → 자동분류 그대로(현재 상태)."""
    base = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(base, "직무분류_검증표.csv"),
              os.path.join(DATA_DIR, "직무분류_검증표.csv")):
        if not os.path.exists(p):
            continue
        ov = {}
        with open(p, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                fix = (row.get("수동검수_정정") or "").strip()
                if fix:
                    ov[((row.get("기관") or "").strip(),
                        (row.get("원본_공고명") or "").strip())] = fix
        return ov
    return {}


# 모듈 1회 로드(ETL이 레코드마다 자동분류 후 이 값으로 덮어쓴다)
JOB_OVERRIDES = load_job_overrides()


def _job_with_override(기관, 공고명, auto):
    """자동분류 결과를 검증표 정정값으로 덮어쓴다(있을 때만)."""
    return JOB_OVERRIDES.get((str(기관), str(공고명 or "").strip()), auto)


# ───────────────── 2축: 전형(track) 정규화 ─────────────────
SOCIAL_KEYS = ["장애", "보훈", "취업지원"]

def normalize_track(*texts):
    """전형 텍스트 → '사회배려'(장애·보훈·취업지원) 또는 '일반'."""
    blob = " ".join(str(t) for t in texts if t)
    if any(k in blob for k in SOCIAL_KEYS):
        return "사회배려"
    return "일반"


def normalize_social_type(*texts):
    """사회배려 안에서도 세부 전형을 구분한다. 장애/보훈/취업지원은 법적으로
       다른 집단이라 하나로 뭉치면 안 된다(장애인 등록자에게 보훈 경쟁률을
       적용하는 식의 오해 방지). 일반전형이면 None."""
    blob = " ".join(str(t) for t in texts if t)
    if "장애" in blob:
        return "장애"
    if "보훈" in blob:
        return "보훈"
    if "취업지원" in blob:
        return "취업지원"
    return None


# 공고명에서 직무 단서를 뽑는다(교통공사: 괄호 안 '(운영)', '(전기)' 등).
def _job_hint_from_notice(name):
    name = str(name or "")
    m = re.findall(r"\(([^)]*)\)", name)
    return " ".join(m) if m else name


# ───────────────────────── 경쟁률 ETL ─────────────────────────
def load_rate_records():
    """정규화 스키마:
       기관, 연도, 직무, 전형(일반/사회배려), 공고명,
       선발, 지원, 합격선, 경쟁률(지원/선발 우선, 없으면 원문 파싱)
    """
    recs = []

    # 교통공사: 연도, 공고명(직무 단서 포함), 전형, 선발, 지원, 합격선, 경쟁률
    for r in _read_csv(_path("humetro_rate"))[1:]:
        if not r or not r[0]:
            continue
        sel, app = _int(r[3]), _int(r[4])
        hint = _job_hint_from_notice(r[1])              # '(운영)' → 운영
        recs.append(dict(
            기관="부산교통공사", 연도=_int(r[0]), 공고명=r[1],
            직무=_job_with_override("부산교통공사", r[1], normalize_job(hint, r[1])),
            전형=normalize_track(r[2]),
            전형원문=r[2],
            사회배려세부=normalize_social_type(r[2]),
            선발=sel, 지원=app, 합격선=_float(r[5]),
            경쟁률=(app / sel if sel and app else _ratio(r[6])),
        ))

    # 도시공사: 연도, 공고명, 구분(전형), 직렬(업무분야), 선발, 지원, 합격선, 경쟁률
    rows = _read_xlsx(_path("bmc_rate"))[1:]
    for r in rows:
        if not r or r[0] is None:
            continue
        sel, app = _int(r[4]), _int(r[5])
        gubun, field = str(r[2] or ""), str(r[3] or "")
        recs.append(dict(
            기관="부산도시공사", 연도=_int(r[0]), 공고명=str(r[1] or ""),
            직무=_job_with_override("부산도시공사", str(r[1] or ""), normalize_job(field)),
            전형=normalize_track(gubun, field),
            전형원문=gubun,
            사회배려세부=normalize_social_type(gubun, field),
            선발=sel, 지원=app, 합격선=_float(r[6]),     # 도시공사 합격선: 2021년~ 46건 존재(2020년은 결측)
            경쟁률=(app / sel if sel and app else _ratio(r[7])),
        ))

    return recs


# ───────────────────────── 채용정보 ETL ─────────────────────────
def load_notice_records():
    recs = []
    specs = [
        ("부산교통공사", "humetro_notice",
         dict(공고="공고명", 마감="접수마감일", 직렬="채용직렬(분야)",
              인원="채용인원", 전형="전형방법", 임용="임용시기",
              조건="임용조건", 부서="담당부서")),
        ("부산도시공사", "bmc_notice",
         dict(공고="공고명", 마감="접수마감일", 직렬="일반전형",
              인원="채용인원", 전형="전형방법", 임용="임용시기",
              조건="임용조건", 부서="담당부서")),
        ("부산관광공사", "bto_notice",
         dict(공고="공고명", 마감="접수마감일", 직렬="일반전형",
              인원="채용인원", 전형="전형방법", 임용="임용시기",
              조건="임용조건", 부서="담당부서")),
    ]
    for inst, key, cmap in specs:
        rows = _read_csv(_path(key))
        head = rows[0]
        idx = {k: (head.index(v) if v in head else None) for k, v in cmap.items()}
        for r in rows[1:]:
            if not r or len(r) < 3:
                continue
            def g(k):
                i = idx[k]
                return r[i] if i is not None and i < len(r) else ""
            recs.append(dict(
                기관=inst, 공고명=g("공고"), 접수마감=g("마감"),
                채용직렬=g("직렬"), 채용인원=_int(g("인원")),
                전형방법=g("전형"), 임용시기=g("임용"),
                임용조건=g("조건"), 담당부서=g("부서"),
                직무=normalize_job(g("직렬"), g("공고")),
            ))
    return recs


# ───────── 임용조건 원문 → 직무별 어학/자격/전공제한 근거(비환각 RAG용) ─────────
_TOEIC_RE = re.compile(r"토익\s*([0-9]{3})")
_CERT_RE = re.compile(r"(기사|산업기사|기술사|기능사|건축사)")

def load_eligibility():
    """직무별로 실제 공고의 임용조건을 모아 근거 텍스트를 만든다.
       - 토익 최저 기준(공고에 명시된 수치)
       - 요구 자격(기사 등) 언급 여부
       - '전공/학력 제한 없음'(블라인드) 명시 여부
    """
    notices = load_notice_records()
    out = defaultdict(lambda: dict(토익최저=set(), 자격언급=set(),
                                    블라인드명시=False, 근거공고=[]))
    for n in notices:
        cond = str(n["임용조건"] or "")
        job = n["직무"]
        for m in _TOEIC_RE.findall(cond):
            out[job]["토익최저"].add(int(m))
        for m in _CERT_RE.findall(cond):
            out[job]["자격언급"].add(m)
        if ("전공" in cond and "제한" in cond and ("없음" in cond or "없" in cond)) \
           or "블라인드" in str(n["전형방법"] or ""):
            out[job]["블라인드명시"] = True
        if cond.strip():
            snippet = re.sub(r"\s+", " ", cond).strip()[:140]
            out[job]["근거공고"].append(dict(기관=n["기관"],
                                            공고명=n["공고명"], 발췌=snippet))
    # set → 정렬 리스트로 직렬화
    clean = {}
    for job, d in out.items():
        clean[job] = dict(
            토익최저=(min(d["토익최저"]) if d["토익최저"] else None),
            자격언급=sorted(d["자격언급"]),
            블라인드명시=d["블라인드명시"],
            근거공고=d["근거공고"][:3],
        )
    return clean


def load_hire_trend():
    """신규채용 인원(연도별). 4기관(교통·도시·환경·시설) 모두 '정규직(일반)'은
       공통 컬럼(index 1)이라 추세선의 기준으로 쓴다. 기관마다 컬럼 구성이 달라
       (환경공단은 보훈·고졸 컬럼 추가) 공통 항목만 안전하게 읽는다."""
    out = {}
    specs = [("부산교통공사", "humetro_hire"), ("부산도시공사", "bmc_hire"),
             ("부산환경공단", "eco_hire"), ("부산시설공단", "fac_hire")]
    for inst, key in specs:
        # [안정성] 선택 데이터(환경·시설공단 등)가 배포 폴더에 없을 수 있다.
        # 파일이 없으면 그 기관만 건너뛰고, 앱 전체가 죽지 않게 한다.
        path = _path(key)
        if not os.path.exists(path):
            continue
        try:
            rows = _read_csv(path)[1:]
        except Exception:
            continue
        series = []
        for r in rows:
            if not r or not r[0]:
                continue
            series.append(dict(
                연도=_int(r[0]),
                정규직일반=_int(r[1]) if len(r) > 1 else None,
                정규직장애=_int(r[2]) if len(r) > 2 else None,
            ))
        out[inst] = series
    return out


# ───────────────────── 진단 / 통계 집계 ─────────────────────
def _classify(ratio):
    if ratio is None: return None
    if ratio >= 50: return "과경쟁"
    if ratio < 5:   return "미달위험"
    return "적정"

def _confidence(records):
    """이 (직무×전형) 셀의 경쟁률을 '얼마나 믿어도 되나'를 정직하게 산출한다.
    raw 표본수만으로는 부족하다 — 가중경쟁률이 단일 대형공고에 끌려가면 표본이
    많아도 '사실상 1~2개 공고'이기 때문. 그래서 3개를 함께 본다:
      1) 표본n         : 셀에 들어간 공고 건수
      2) 출처기관수     : 교통/도시 중 몇 곳에서 왔나(합격선 이종시험 혼합 경보용)
      3) 최대공고집중도  : 가장 큰 공고 1개가 총지원자에서 차지하는 비중(0~1).
                         높을수록 '평균'이 그 공고 하나를 의미함.
    등급은 점수에 반영하지 않는다 — 사용자에게 '이 숫자를 얼마나 믿을지' 알리는 라벨."""
    valid = [x for x in records
             if x["선발"] is not None and x["지원"] is not None and x["선발"] > 0]
    n = len(valid)
    insts = sorted({x["기관"] for x in valid})
    yrs = sorted({x["연도"] for x in valid if x["연도"]})
    total_app = sum((x["지원"] or 0) for x in valid)
    max_app = max((x["지원"] or 0) for x in valid) if valid else 0
    concentration = round(max_app / total_app, 2) if total_app else None

    # 등급 결정: 표본수 기준 → 집중도 높으면 하향
    if n < 5:
        grade = "낮음"
    elif n < 10:
        grade = "보통"
    else:
        grade = "양호"
    if concentration is not None:
        if concentration >= 0.55 and grade == "양호":
            grade = "보통"          # 표본 많아도 한 공고가 절반 이상이면 사실상 1공고
        if concentration >= 0.70:
            grade = "낮음"          # 한 공고가 70%+면 '평균'이라 부르기 어렵다

    return dict(
        표본n=n,
        출처기관수=len(insts),
        출처기관=insts,
        연도범위=[yrs[0], yrs[-1]] if yrs else None,
        최대공고집중도=concentration,
        등급=grade,
        한줄=(f"표본 {n}건"
              + (f"·{yrs[0]}~{yrs[-1]}" if yrs else "")
              + (f"·최대공고 {int(concentration*100)}% 비중" if concentration else "")),
    )


def _weighted_ratio(records):
    """가중 경쟁률 = 총지원 / 총선발. (단순평균의 소규모 공고 왜곡 제거)

    [버그 수정] 과거엔 `if x["선발"] and x["지원"]` 조건이라 지원자 0명 공고가
    Falsy로 빠졌다. 미달·저경쟁을 진단하는 제품에서 0지원 공고를 빼면 경쟁률이
    실제보다 높게 나온다 → 선발 인원이 있으면(>0) 지원 0명도 포함한다."""
    valid = [x for x in records
             if x["선발"] is not None and x["지원"] is not None and x["선발"] > 0]
    sel = sum(x["선발"] for x in valid)
    app = sum(x["지원"] for x in valid)
    return round(app / sel, 1) if sel else None


def build_dataset():
    """앱·상담이 사용하는 통합 집계."""
    rate = load_rate_records()

    # (직무 × 전형) 버킷
    bucket = defaultdict(list)              # (직무, 전형) -> [rec]
    for x in rate:
        # [버그 수정] Truthy 조건은 지원=0 / 경쟁률=0.0 공고를 누락시킨다.
        # 선발·지원이 둘 다 기록돼 있으면(0 포함) 포함하고, 아니면 원문 경쟁률로 보강.
        if (x["선발"] is not None and x["지원"] is not None) or x["경쟁률"] is not None:
            bucket[(x["직무"], x["전형"])].append(x)

    # 1) 직무별 일반전형 진단(추천의 기준) + 사회배려 갭
    jobs = sorted({j for (j, t) in bucket})
    job_stats = {}
    for j in jobs:
        gen = bucket.get((j, "일반"), [])
        soc = bucket.get((j, "사회배려"), [])
        gen_cuts = [x["합격선"] for x in gen if x["합격선"] and x["합격선"] > 0]
        # 합격선이 어느 기관에서 왔는지 — 서로 다른 시험을 섞었는지 드러내기 위함
        cut_insts = sorted({x["기관"] for x in gen if x["합격선"] and x["합격선"] > 0})
        # 사회배려 세부 전형별 경쟁률(장애/보훈/취업지원은 다른 집단이라 분리)
        soc_by_type = {}
        for t in ("장애", "보훈", "취업지원"):
            recs_t = [x for x in soc if x.get("사회배려세부") == t]
            if recs_t:
                soc_by_type[t] = dict(경쟁률=_weighted_ratio(recs_t), n=len(recs_t),
                                      참고용=(len(recs_t) < 3))  # 공고 1~2건은 '참고용'
        job_stats[j] = dict(
            일반_가중경쟁률=_weighted_ratio(gen),
            일반_n=len(gen),
            신뢰=_confidence(gen),                # 이 경쟁률을 얼마나 믿을지(라벨용)
            사회배려_가중경쟁률=_weighted_ratio(soc) if soc else None,
            사회배려_n=len(soc),
            사회배려_세부=soc_by_type,        # {'장애':{경쟁률,n}, '취업지원':{...}}
            합격선평균=round(statistics.mean(gen_cuts), 1) if gen_cuts else None,
            합격선표준편차=round(statistics.pstdev(gen_cuts), 1) if len(gen_cuts) > 1 else None,
            합격선n=len(gen_cuts),
            합격선기관=cut_insts,         # 1개 기관이면 동질, 2개면 '이종 시험 혼합'
            분류=_classify(_weighted_ratio(gen)),
        )

    # 미스매치 차트용(일반전형, 가중경쟁률 기준)
    mismatch = [dict(직무=j, 평균경쟁률=s["일반_가중경쟁률"],
                     n=s["일반_n"], 분류=s["분류"],
                     합격선평균=s["합격선평균"])
                for j, s in job_stats.items() if s["일반_가중경쟁률"]]
    mismatch.sort(key=lambda d: -d["평균경쟁률"])

    # 2) 사회배려 전형 전체 갭 (ESG 근거) — 가중 기준
    soc_all = [x for x in rate if x["전형"] == "사회배려" and x["선발"]]
    soc_sel = sum(x["선발"] for x in soc_all)
    soc_app = sum((x["지원"] or 0) for x in soc_all)
    soc_under = [x for x in soc_all if (x["지원"] or 0) < (x["선발"] or 0)]

    # 3) 합격선 통계(예측 아님) — 기관별로 분리해 '이종 시험 혼합'을 드러낸다
    cut_recs = [x for x in rate if x["합격선"] and x["합격선"] > 0]
    cut_insts = sorted({x["기관"] for x in cut_recs})
    all_cuts = [x["합격선"] for x in cut_recs]
    by_inst = {}
    for inst in cut_insts:
        vals = [x["합격선"] for x in cut_recs if x["기관"] == inst]
        by_inst[inst] = dict(
            n=len(vals),
            평균=round(statistics.mean(vals), 1) if vals else None,
            표준편차=round(statistics.pstdev(vals), 1) if len(vals) > 1 else None,
            범위=[min(vals), max(vals)] if vals else None,
        )
    cut_stat = dict(
        n=len(cut_recs),
        제공기관=cut_insts,                        # ['부산교통공사','부산도시공사']
        기관별=by_inst,                            # 기관마다 시험 구성이 달라 직접 비교 주의
        전체평균=round(statistics.mean(all_cuts), 1) if all_cuts else None,
        전체표준편차=round(statistics.pstdev(all_cuts), 1) if len(all_cuts) > 1 else None,
        범위=[min(all_cuts), max(all_cuts)] if all_cuts else None,
        주의="합격선은 교통공사(전 연도)·도시공사(2021년~)에만 존재하고 "
             "관광공사·도시공사 2020년은 결측이다. 기관마다 필기 시험 구성(과목·배점)이 "
             "다르므로 기관을 섞은 전체평균은 직접 비교용이 아니라 '대략적 분포'로만 본다. "
             "평균값은 '예측'이 아니라 과거 통계 기준선이다.",
    )

    # 4) 데이터 커버리지 매트릭스 — "무엇을 어느 기관까지 실제로 쓰는가"를 정직하게 명시
    rate_insts = sorted({x["기관"] for x in rate})
    coverage = dict(
        경쟁률=dict(기관=rate_insts, 건수=len(rate),
                  설명="직무×전형 경쟁률은 교통·도시공사만 공시. 관광공사·시설·환경공단은 미공시."),
        합격선=dict(기관=cut_insts, 건수=len(cut_recs),
                  설명="필기 합격선은 교통(전연도)·도시(2021~)만. 본인에게만 공개되는 값이라 추가 수집 불가."),
        신규채용규모=dict(기관=list(load_hire_trend().keys()),
                     설명="신규채용 인원(규모/추세)은 교통·도시·환경·시설 4기관 공시."),
        채용정보=dict(기관=["부산교통공사", "부산도시공사", "부산관광공사"],
                  설명="공고 메타·임용조건(어학·자격)은 3기관 보유."),
        한줄정정="'3기관 5년 데이터'가 아니라 → 채용정보 3기관 + 경쟁률·합격선 2기관(교통·도시) "
                "+ 신규채용 규모 4기관. 기관별 커버리지는 불균형하며 이를 그대로 표기한다.",
    )

    return dict(
        meta=dict(경쟁률레코드=len(rate), 합격선레코드=len(cut_recs),
                  검증표=dict(전수검수행=143, 정정적용=len(JOB_OVERRIDES))),
        job_stats=job_stats,
        mismatch=mismatch,
        esg=dict(선발=soc_sel, 지원=soc_app,
                 가중경쟁률=round(soc_app / soc_sel, 1) if soc_sel else None,
                 미달건수=len(soc_under), 표본수=len(soc_all)),
        cut_stat=cut_stat,
        coverage=coverage,
        eligibility=load_eligibility(),
        hire_trend=load_hire_trend(),
    )


if __name__ == "__main__":
    ds = build_dataset()
    print(json.dumps(ds, ensure_ascii=False, indent=2, default=str))
