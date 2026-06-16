"""
busan_data.py — 부산 공공기관 채용 미스매치 내비게이터 / 데이터 엔진
===================================================================
3개 후원기관(부산교통공사·부산도시공사·부산관광공사)의 공공데이터를
하나의 정규화된 스키마로 통합(ETL)하고, 미스매치 진단 / 합격선·경쟁률
예측의 근거 데이터를 생성한다.

원천 데이터 (data.go.kr):
  - 부산교통공사_채용경쟁률현황      data/humetro_rate.csv   (data 15145399)
  - 부산교통공사_신규채용인원현황    data/humetro_hire.csv   (data 15145396)
  - 부산교통공사_채용정보            data/humetro_notice.csv (data 15145394)
  - 부산도시공사_채용경쟁률현황      data/bmc_rate.xlsx      (data 15145033)
  - 부산도시공사_신규채용현황        data/bmc_hire.csv
  - 부산도시공사_채용정보            data/bmc_notice.csv
  - 부산관광공사_채용정보            data/bto_notice.csv     (data 15144999)

핵심 산출물:
  load_rate_records()  → 정규화된 경쟁률 레코드 리스트
  build_dataset()      → 진단/예측에 필요한 모든 집계를 담은 dict
"""
from __future__ import annotations
import csv, re, os, json, statistics
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

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

# ───────────────────── 직렬군 정규화 (기관 공통) ─────────────────────
# 두 기관의 서로 다른 직렬 표기를 9개 공통 카테고리로 통합한다.
FIELD_GROUPS = [
    ("사회배려",   ["장애", "취업지원", "보훈"]),
    ("청년인턴",   ["인턴"]),
    ("사무·행정",  ["운영", "행정", "경영", "경제", "회계", "법", "비서", "안내", "기록물"]),
    ("전산",       ["전산", "전산직"]),
    ("전기",       ["전기"]),
    ("기계",       ["기계"]),
    ("토목·건축",  ["토목", "건축", "조경"]),
    ("신호·통신",  ["신호", "통신"]),
    ("운전·운송",  ["운전", "운송"]),
    ("공무직·기능", ["공무직", "미화", "시설", "유지보수", "중정비", "안전문", "관리사무소"]),
]

def normalize_field(*texts):
    blob = " ".join(t for t in texts if t)
    for group, keys in FIELD_GROUPS:
        if any(k in blob for k in keys):
            return group
    return "기타"

# ───────────────────────── 경쟁률 ETL ─────────────────────────
def load_rate_records():
    """정규화 스키마:
       기관, 연도, 직렬군, 전형(일반/장애인/…), 공고명,
       선발, 지원, 합격선, 경쟁률(지원/선발 우선, 없으면 원문 파싱)
    """
    recs = []

    # 교통공사: 연도, 공고명, 전형, 선발, 지원, 합격선, 경쟁률(문자열)
    for r in _read_csv(os.path.join(DATA_DIR, "humetro_rate.csv"))[1:]:
        if not r or not r[0]:
            continue
        sel, app = _int(r[3]), _int(r[4])
        recs.append(dict(
            기관="부산교통공사", 연도=_int(r[0]), 공고명=r[1], 전형=r[2],
            직렬군=normalize_field(r[1], r[2]),
            선발=sel, 지원=app, 합격선=_float(r[5]),
            경쟁률=(app / sel if sel and app else _ratio(r[6])),
        ))

    # 도시공사: 연도, 공고명, 전형(구분), 직렬, 선발, 지원, 합격선, 경쟁률
    rows = _read_xlsx(os.path.join(DATA_DIR, "bmc_rate.xlsx"))[1:]
    for r in rows:
        if not r or r[0] is None:
            continue
        sel, app = _int(r[4]), _int(r[5])
        gubun, field = str(r[2] or ""), str(r[3] or "")
        recs.append(dict(
            기관="부산도시공사", 연도=_int(r[0]), 공고명=str(r[1] or ""), 전형=gubun,
            직렬군=normalize_field(field, gubun),
            선발=sel, 지원=app, 합격선=_float(r[6]),
            경쟁률=(app / sel if sel and app else _ratio(r[7])),
        ))

    return recs

# ───────────────────────── 채용정보 ETL ─────────────────────────
def load_notice_records():
    """공고 단위: 기관, 공고명, 접수마감, 채용직렬(원문), 채용인원,
       전형방법, 임용시기, 담당부서"""
    recs = []
    specs = [
        ("부산교통공사", "humetro_notice.csv",
         dict(공고="공고명", 마감="접수마감일", 직렬="채용직렬(분야)",
              인원="채용인원", 전형="전형방법", 임용="임용시기", 부서="담당부서")),
        ("부산도시공사", "bmc_notice.csv",
         dict(공고="공고명", 마감="접수마감일", 직렬="일반전형",
              인원="채용인원", 전형="전형방법", 임용="임용시기", 부서="담당부서")),
        ("부산관광공사", "bto_notice.csv",
         dict(공고="공고명", 마감="접수마감일", 직렬="일반전형",
              인원="채용인원", 전형="전형방법", 임용="임용시기", 부서="담당부서")),
    ]
    for inst, fn, cmap in specs:
        rows = _read_csv(os.path.join(DATA_DIR, fn))
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
                전형방법=g("전형"), 임용시기=g("임용"), 담당부서=g("부서"),
            ))
    return recs

def load_hire_trend():
    """연도별 신규채용 인원: 기관별 정규직(일반/장애)/공무직/인턴"""
    out = {}
    for inst, fn in [("부산교통공사", "humetro_hire.csv"),
                     ("부산도시공사", "bmc_hire.csv")]:
        rows = _read_csv(os.path.join(DATA_DIR, fn))[1:]
        out[inst] = [dict(
            연도=_int(r[0]), 정규직일반=_int(r[1]), 정규직장애=_int(r[2]),
            공무직=_int(r[3]), 인턴일반=_int(r[4]), 인턴장애=_int(r[5]),
        ) for r in rows if r and r[0]]
    return out

# ───────────────────── 진단 / 예측 집계 ─────────────────────
def _classify(ratio):
    if ratio is None: return None
    if ratio >= 50: return "과경쟁"
    if ratio < 5:   return "미달위험"
    return "적정"

def build_dataset():
    """앱·문서가 사용하는 통합 집계 산출."""
    rate = load_rate_records()

    # 1) 직렬군 × 기관 미스매치 진단
    by_grp = defaultdict(lambda: defaultdict(list))   # 직렬군 -> 기관 -> [경쟁률]
    cut_grp = defaultdict(list)                        # 직렬군 -> [합격선]
    for x in rate:
        if x["경쟁률"]:
            by_grp[x["직렬군"]][x["기관"]].append(x["경쟁률"])
        if x["합격선"] and x["합격선"] > 0:
            cut_grp[x["직렬군"]].append(x["합격선"])

    mismatch = []
    for grp, insts in by_grp.items():
        allr = [r for v in insts.values() for r in v]
        mismatch.append(dict(
            직렬군=grp, n=len(allr),
            평균경쟁률=round(statistics.mean(allr), 1),
            최고경쟁률=round(max(allr), 1),
            평균합격선=(round(statistics.mean(cut_grp[grp]), 1) if cut_grp[grp] else None),
            분류=_classify(statistics.mean(allr)),
        ))
    mismatch.sort(key=lambda d: -d["평균경쟁률"])

    # 2) 사회배려(장애/취업지원/보훈) 갭 — ESG 근거
    esg = [x for x in rate if x["직렬군"] == "사회배려" and x["선발"]]
    esg_sel = sum(x["선발"] for x in esg)
    esg_app = sum(x["지원"] or 0 for x in esg)
    esg_under = [x for x in esg if (x["지원"] or 0) < x["선발"]]   # 실제 미달
    esg_risk = [x for x in esg if (x["지원"] or 0) < (x["선발"] or 0) * 3]

    # 3) 합격선 예측 백테스트 (2020–2023 학습 → 2024 검증)
    cut_recs = [x for x in rate if x["합격선"] and x["합격선"] > 0 and x["연도"]]
    train = [x for x in cut_recs if x["연도"] <= 2023]
    test = [x for x in cut_recs if x["연도"] == 2024]
    gm = defaultdict(list)
    for x in train:
        gm[(x["기관"], x["직렬군"])].append(x["합격선"])
    gm = {k: statistics.mean(v) for k, v in gm.items()}
    base = statistics.mean([x["합격선"] for x in train]) if train else 0
    errs = [abs(gm.get((x["기관"], x["직렬군"]), base) - x["합격선"]) for x in test]
    backtest = dict(
        학습수=len(train), 검증수=len(test),
        MAE=(round(statistics.mean(errs), 1) if errs else None),
        합격선범위=[min(x["합격선"] for x in cut_recs), max(x["합격선"] for x in cut_recs)],
    )

    return dict(
        meta=dict(경쟁률레코드=len(rate), 합격선레코드=len(cut_recs)),
        mismatch=mismatch,
        esg=dict(선발=esg_sel, 지원=esg_app,
                 평균경쟁률=round(esg_app / esg_sel, 1) if esg_sel else None,
                 미달건수=len(esg_under), 미달위험건수=len(esg_risk)),
        backtest=backtest,
        hire_trend=load_hire_trend(),
    )


if __name__ == "__main__":
    ds = build_dataset()
    print(json.dumps(ds, ensure_ascii=False, indent=2, default=str))
