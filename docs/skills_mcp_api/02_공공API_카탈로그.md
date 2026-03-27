# 공공API 카탈로그

> **HIRA(KCD 조회), 식약처 DUR(비급여주사), data.go.kr(보험통계)** 연동 코드 및 가이드

---

## 1. HIRA (건강보험심사평가원)

### 1.1 KCD 코드 조회

| 항목 | 내용 |
|------|------|
| 용도 | KCD 진단코드 검증, 진단명 확인 |
| API | [HIRA 의료정보 API](https://www.hira.or.kr/) — 사업자 등록 필요 |
| 대안 | 공개 KCD 코드표 다운로드 후 로컬 매핑 |

### 1.2 수가코드 조회

| 항목 | 내용 |
|------|------|
| 용도 | 진료비세부내역서 항목코드 → 비급여 분류 (도수치료, MRI 등) |
| 연동 | `billing_codes.json`에 HIRA 기준 코드 매핑 유지 |

### 1.3 연동 코드 예시 (Fetch MCP 또는 requests)

```python
# HIRA API (실제 엔드포인트는 HIRA 가입 후 확인)
# import requests
# resp = requests.get(
#     "https://api.hira.or.kr/...",
#     headers={"Authorization": f"Bearer {API_KEY}"},
#     params={"kcd": "K35.8"}
# )
# data = resp.json()
```

---

## 2. 식약처 DUR (Drug Utilization Review)

### 2.1 비급여 주사료 허가 범위

| 항목 | 내용 |
|------|------|
| 용도 | 비급여 주사료(영양제, 비타민 등) 약사법령상 허가 여부 확인 |
| API | [식약처 DUR API](https://www.data.go.kr/) — 공공데이터포털 가입 |
| FRD-005 | 비급여 비중 검토 시 DUR 결과 연동 |

### 2.2 연동 코드 예시

```python
# data.go.kr 공공데이터 API (식약처 DUR)
# import requests
# url = "https://apis.data.go.kr/1471000/DURPrdctInfoService02/..."
# params = {
#     "serviceKey": os.getenv("DATA_GO_KR_API_KEY"),
#     "itemName": "비타민C",
#     ...
# }
# resp = requests.get(url, params=params)
```

---

## 3. data.go.kr (공공데이터포털)

### 3.1 보험 통계·공시

| 항목 | 내용 |
|------|------|
| 용도 | 보험사 공시 정보, 보험금 지급 통계 |
| API | [공공데이터포털](https://www.data.go.kr/) — API 키 발급 |

### 3.2 연동 가이드

1. [data.go.kr](https://www.data.go.kr/) 회원가입
2. 원하는 API 검색 (예: "보험", "의료")
3. 활용신청 → 인증키 발급
4. `.env`에 `DATA_GO_KR_API_KEY` 설정

---

## 4. data_loader.py 연동

| 함수 | 연동 대상 |
|------|----------|
| `check_kcd_exclusion()` | kcd_exclusion_map.json (로컬) — HIRA 연동 시 실시간 검증 추가 |
| (신규) `validate_billing_code()` | billing_codes.json + HIRA 수가코드 |
| (신규) `check_dur_approval()` | 식약처 DUR API |

---

## 5. 환경 변수

```env
# .env 예시
DATA_GO_KR_API_KEY=your_data_go_kr_key
HIRA_API_KEY=your_hira_key
```
