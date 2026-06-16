# 🧭 부산 공공기관 커리어 로드맵 내비게이터

부산교통공사·부산도시공사의 5년 채용 공공데이터(경쟁률·필기합격선·신규채용)
위에서, 아직 직렬·자격을 정하기 전 단계의 대학생에게 **데이터상 유리한 직렬과
준비 로드맵**을 제시하는 AI 커리어 설계 도구.

## 구성
| 파일 | 역할 |
|------|------|
| `app.py` | Streamlit UI (로드맵 · 미스매치 진단 · AI 상담 3탭) |
| `busan_data.py` | 3기관 공공데이터 통합 ETL·진단·합격선 예측(백테스트) |
| `recommender.py` | 학생 프로필 → 설명가능 직렬 적합도 + 로드맵 |
| `gemini_advisor.py` | 데이터 근거 기반 AI 서술·상담 (Gemini, st.secrets) |
| `data/` | 원천 공공데이터 (data.go.kr) |

## 로컬 실행
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # 키 입력
streamlit run app.py
```

## 배포 (Streamlit Cloud)
1. GitHub 저장소에 push
2. share.streamlit.io 에서 app.py 지정
3. App settings → Secrets 에 `GEMINI_API_KEY` 입력 (코드에 키를 넣지 말 것)

> AI 키가 없어도 결정론적 폴백 로드맵으로 모든 기능이 시연됩니다.

## 데이터 출처
- 부산교통공사 채용경쟁률현황 (data.go.kr/data/15145399)
- 부산교통공사 신규채용인원현황 (data.go.kr/data/15145396)
- 부산교통공사 채용정보 (data.go.kr/data/15145394)
- 부산도시공사 채용경쟁률현황·신규채용현황·채용정보 (data.go.kr/data/15145033 외)

본 도구의 추천은 과거 5년 공시데이터 기반의 **구조적 경향**이며,
당해연도 채용규모 변동은 각 기관 공고로 재확인이 필요합니다.
