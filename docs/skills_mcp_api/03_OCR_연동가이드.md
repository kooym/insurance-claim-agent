# OCR 연동가이드

> **클로바 OCR (Template/General) vs GPT-4o Vision** 비교표, 실제 연동 코드 예시, 비용 계산

---

## 1. 비교표

| 항목 | 클로바 OCR | GPT-4o Vision |
|------|------------|---------------|
| **입력** | PDF, 이미지 | 이미지 (PDF는 페이지별 변환) |
| **Template** | 고정 양식 최적화 | - |
| **General** | 자유 형식 | 자유 형식 |
| **구조화** | JSON 템플릿 지정 가능 | 프롬프트로 JSON 추출 |
| **비용** | 건당 과금 (네이버 클라우드) | 토큰당 과금 (OpenAI) |
| **한국어** | 우수 | 우수 |
| **설정** | CLOVA_OCR_API_URL, CLOVA_OCR_SECRET_KEY | OPENAI_API_KEY |

---

## 2. 클로바 OCR 연동 코드 예시

```python
# config/settings.py 에서
# CLOVA_OCR_API_URL, CLOVA_OCR_SECRET_KEY 사용

import requests
from pathlib import Path

def extract_text_clova(image_path: Path) -> str:
    """클로바 OCR General API — 이미지 → 텍스트."""
    url = os.getenv("CLOVA_OCR_API_URL", "https://...")
    secret = os.getenv("CLOVA_OCR_SECRET_KEY", "")
    
    with open(image_path, "rb") as f:
        files = {"file": f}
        headers = {"X-OCR-SECRET": secret}
        resp = requests.post(url, files=files, headers=headers)
    
    if resp.status_code != 200:
        raise RuntimeError(f"OCR 실패: {resp.status_code}")
    
    data = resp.json()
    # 응답 구조에 따라 텍스트 추출
    return data.get("result", {}).get("text", "")
```

---

## 3. GPT-4o Vision 연동 코드 예시

```python
from openai import OpenAI

def extract_fields_gpt4v(image_path: Path) -> dict:
    """GPT-4o Vision — 이미지 → 구조화된 필드 (JSON)."""
    client = OpenAI()
    
    with open(image_path, "rb") as f:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"}
                        },
                        {
                            "type": "text",
                            "text": "이 진단서/청구서에서 accident_date, hospital_days, kcd_code, diagnosis, covered_self_pay, non_covered 를 JSON으로 추출해주세요."
                        }
                    ]
                }
            ],
            max_tokens=500
        )
    
    text = response.choices[0].message.content
    return json.loads(text)  # 또는 regex로 JSON 파싱
```

---

## 4. 비용 계산 (대략)

| 서비스 | 단가 | 예상 (청구 1건, 서류 3장) |
|--------|------|---------------------------|
| 클로바 OCR | 건당 수십 원~ | 약 100~300원 |
| GPT-4o Vision | 이미지당 ~$0.01 | 약 $0.03 (40원) |
| GPT-4o-mini | 더 저렴 | 약 $0.005 (7원) |

> 실제 비용은 사용량·요금제에 따라 다름.

---

## 5. doc_parser.py 연동

```python
# src/ocr/doc_parser.py 에 추가 예정

def _extract_text_from_file(file_path: Path) -> str:
    """PDF/이미지 → 텍스트. 확장자에 따라 OCR 또는 직접 추출."""
    suffix = file_path.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".webp"):
        return _extract_text_clova(file_path)  # 또는 gpt4v
    if suffix == ".pdf":
        # PDF → 페이지별 이미지 변환 후 OCR
        return _extract_text_from_pdf(file_path)
    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8")
    raise ValueError(f"지원하지 않는 형식: {suffix}")
```
