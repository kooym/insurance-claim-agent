"""
문서 파서 — 텍스트·PDF 서류 파일에서 구조화 정보 추출.

지원 파일 형식:
  .txt  : 텍스트 직접 읽기
  .pdf  : pypdf 로 텍스트 레이어 추출 (TASK-07)
           ※ 스캔 PDF(이미지 전용)는 텍스트 추출량이 적어 confidence 낮게 평가됨
           ※ 이미지 OCR은 TASK-08에서 구현 예정

파싱 모드:
  regex  : 정규식 기반 추출 (API 키 불필요, PoC 기본)
  llm    : LLM API로 서류 전체 파싱 (높은 정확도)
  hybrid : regex 실패 시 LLM fallback (권장)
"""
from __future__ import annotations
import re
import itertools
from pathlib import Path
from typing import Optional

from src.schemas import ParsedDocument
from config.settings import DOC_PARSE_MODE, OCR_BACKEND, VISION_OCR_MODEL


# ══════════════════════════════════════════════════════════════════
# 파일 형식별 텍스트 추출
# ══════════════════════════════════════════════════════════════════

def extract_text_from_file(file_path: Path) -> tuple[str, list[str]]:
    """
    파일 확장자에 따라 텍스트를 추출한다.

    반환:
      (raw_text, errors)
      raw_text : 추출된 텍스트 (실패 시 빈 문자열)
      errors   : 경고/오류 메시지 목록

    지원 형식:
      .txt              — UTF-8 / CP949 직독
      .pdf              — pypdf PdfReader (텍스트 레이어 있는 PDF)
                           ※ 스캔 PDF(텍스트 레이어 없음)는 OCR 대상으로 자동 전환
      .jpg/.jpeg/.png   — pytesseract OCR (kor+eng, TASK-08)
                           ※ 시스템에 Tesseract 5.x 설치 필요
                              macOS: brew install tesseract tesseract-lang
    """
    suffix = file_path.suffix.lower()
    errors: list[str] = []

    if suffix == ".txt":
        try:
            return file_path.read_text(encoding="utf-8"), errors
        except UnicodeDecodeError:
            try:
                return file_path.read_text(encoding="cp949"), errors
            except Exception as e:
                errors.append(f"텍스트 파일 읽기 실패: {e}")
                return "", errors

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            errors.append(
                "pypdf 패키지가 설치되지 않았습니다. "
                "`pip install pypdf` 또는 `pip install -r requirements.txt` 를 실행하세요."
            )
            return "", errors

        try:
            reader = PdfReader(str(file_path))
            pages_text: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                pages_text.append(page_text)
            raw_text = "\n".join(pages_text).strip()

            if not raw_text:
                # 텍스트 레이어 없음 → 스캔 PDF 의심 → OCR로 재시도
                errors.append(
                    f"{file_path.name}: PDF 텍스트 레이어 비어 있음 — 스캔 PDF로 판단하여 OCR 시도 중."
                )
                ocr_text, ocr_errs = _ocr_pdf_as_images(file_path)
                errors.extend(ocr_errs)
                return ocr_text, errors

            if len(raw_text) < 50:
                errors.append(
                    f"{file_path.name}: PDF 추출 텍스트가 너무 짧습니다 ({len(raw_text)}자). "
                    "스캔 PDF 여부를 확인하세요."
                )
            return raw_text, errors

        except Exception as e:
            errors.append(f"{file_path.name}: PDF 파싱 오류 — {e}")
            return "", errors

    if suffix in (".jpg", ".jpeg", ".png"):
        return _ocr_image(file_path)

    # 미지원 확장자
    errors.append(
        f"{file_path.name}: 지원하지 않는 파일 형식 ({suffix}). "
        "현재 지원: .txt, .pdf, .jpg, .jpeg, .png"
    )
    return "", errors


# ══════════════════════════════════════════════════════════════════
# 마스킹 필드 가명 처리
# ══════════════════════════════════════════════════════════════════

# 가명 풀 — 순번별 자동 부여
_PSEUDONYM_POOL = [
    "홍길동", "김영희", "이철수", "박지수", "최민준",
    "정하은", "강태현", "윤서연", "한동우", "조은비",
    "임재혁", "서지원", "오승희", "신동훈", "권유진",
    "백수진", "나영진", "하정우", "장은서", "문재원",
]

# 모듈 수준 카운터 (스레드 안전 — itertools.count 사용)
_pseudonym_counter = itertools.count()


def _handle_masked_fields(fields: dict) -> dict:
    """
    Vision OCR이 'masked' 또는 빈 값으로 반환한 개인정보 필드를
    순번별 가명으로 자동 대체한다.

    처리 대상 필드:
      - patient_name    → "홍길동(가칭)" 등 순번별 가명
      - patient_id      → "MASKED-001" 등 순번
      - receipt_no      → "RCP-MASKED-001"
      - resident_number → "******-*******"

    가명 매핑 테이블은 fields["masked_field_map"]에 저장.

    Returns:
        fields dict (제자리 수정)
    """
    _MASKED_VALUES = {"masked", "MASKED", "Masked", ""}

    # 가명 매핑 테이블
    mapping: dict[str, str] = {}

    # ── patient_name ──
    pname = fields.get("patient_name")
    if pname is not None and (pname in _MASKED_VALUES or (isinstance(pname, str) and "masked" in pname.lower())):
        seq = next(_pseudonym_counter)
        idx = seq % len(_PSEUDONYM_POOL)
        pseudonym = f"{_PSEUDONYM_POOL[idx]}(가칭)"
        fields["patient_name"] = pseudonym
        mapping["patient_name"] = pseudonym

    # ── patient_id (환자등록번호) ──
    pid = fields.get("patient_id")
    if pid is not None and (pid in _MASKED_VALUES or (isinstance(pid, str) and "masked" in pid.lower())):
        seq = next(_pseudonym_counter)
        masked_id = f"MASKED-{seq:03d}"
        fields["patient_id"] = masked_id
        mapping["patient_id"] = masked_id

    # ── receipt_no (영수증 번호) ──
    rno = fields.get("receipt_no")
    if rno is not None and (rno in _MASKED_VALUES or (isinstance(rno, str) and "masked" in rno.lower())):
        seq = next(_pseudonym_counter)
        masked_rno = f"RCP-MASKED-{seq:03d}"
        fields["receipt_no"] = masked_rno
        mapping["receipt_no"] = masked_rno

    # ── resident_number (주민번호) ──
    rnum = fields.get("resident_number")
    if rnum is not None and (rnum in _MASKED_VALUES or (isinstance(rnum, str) and "masked" in rnum.lower())):
        fields["resident_number"] = "******-*******"
        mapping["resident_number"] = "******-*******"

    # 매핑 테이블 저장
    if mapping:
        fields["masked_field_map"] = mapping

    return fields


# ══════════════════════════════════════════════════════════════════
# Vision OCR — GPT 멀티모달로 이미지 직접 분석
# ══════════════════════════════════════════════════════════════════

# 진료비 계산서·영수증 전용 Vision 프롬프트
_RECEIPT_VISION_PROMPT = """이 이미지는 한국 병원의 '진료비 계산서·영수증'입니다.
아래 JSON 형식으로 정보를 추출해 주세요.

## 표 읽기 방법 (중요)
한국 진료비 영수증 표는 다음 컬럼 구조를 가집니다:
  | 항목 | 급여 - 일부본인부담 | 급여 - 전액본인부담 | 비급여 |
또는:
  | 항목 | 급여 - 공단부담 | 급여 - 본인부담 | 비급여 |

1. 표를 행 단위로 위→아래, 각 행을 좌→우 순서로 읽으세요.
2. "급여 본인부담" 컬럼이 2개(일부본인부담 + 전액본인부담)로 나뉠 수 있습니다 — 합산하세요.
3. 금액의 쉼표(,)를 제거하고 정수로 변환하세요. "없음", "-", 빈칸 = 0.
4. 숫자가 흐리거나 불확실하면 가장 가능성 높은 값으로 추출하고, ocr_notes에 기록하세요.

## 산술 검증 (반드시 확인)
- 각 컬럼의 항목별 합을 계산하여 소계 행과 비교하세요.
- covered(급여 본인부담) 합 ≈ receipt_summary.covered_self_pay
- non_covered(비급여) 합 ≈ receipt_summary.non_covered_subtotal
- 10% 이상 불일치 시 해당 행을 재확인하고 ocr_notes에 "산술 불일치" 기록.

## 추출 규칙
1. 검은 블록으로 마스킹된 필드(환자 성명, 등록번호, 주민번호 등)는 "masked"로 표기하세요.
2. 금액은 정수(원 단위)로 변환하세요. 쉼표 제거. 없는 항목은 0.
3. 날짜는 "YYYY-MM-DD" 형식으로 통일하세요.
4. 이미지에서 읽을 수 없는 값은 null로 반환하세요.

## 출력 JSON
```json
{
  "patient_name": "환자 성명 또는 masked",
  "patient_id": "환자등록번호 또는 masked",
  "department": "진료과",
  "admission_date": "입원일 YYYY-MM-DD",
  "discharge_date": "퇴원일 YYYY-MM-DD",
  "hospital_days": 입원일수(정수),
  "receipt_line_items": [
    {"category": "진찰료", "covered": 급여본인부담금, "non_covered": 비급여, "subtotal": 합계},
    {"category": "입원료", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "식대", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "투약및조제료", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "주사료", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "마취료", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "처치및수술료", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "검사료", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "영상진단료", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "방사선치료료", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "치료재료대", "covered": 0, "non_covered": 0, "subtotal": 0},
    {"category": "기타", "covered": 0, "non_covered": 0, "subtotal": 0}
  ],
  "receipt_summary": {
    "covered_subtotal": 급여진료비총액,
    "covered_self_pay": 급여본인부담금합계,
    "non_covered_subtotal": 비급여총액,
    "public_insurance": 공단부담금,
    "elective_care_fee": 선택진료료(없으면 0),
    "total_self_pay": 최종본인납부액
  },
  "special_items": [
    {"item_name": "도수치료/체외충격파/주사료/MRI 등 특수항목", "amount": 금액, "sessions": 횟수}
  ],
  "ocr_notes": "이미지 품질 이슈나 불확실한 추출 사항 메모"
}
```

JSON만 반환하세요."""

# 범용 서류 Vision 프롬프트
_GENERIC_DOC_VISION_PROMPT = """이 이미지는 한국 보험 청구 관련 서류입니다.
아래 JSON 형식으로 정보를 추출해 주세요.

## 추출 규칙
1. 검은 블록으로 마스킹된 필드는 "masked"로 표기하세요.
2. 금액은 정수(원 단위), 날짜는 "YYYY-MM-DD"로 통일하세요.
3. 읽을 수 없는 값은 null로 반환하세요.

## 출력 JSON
```json
{
  "doc_type": "진단서|입원확인서|수술확인서|진료비영수증|진료비세부내역서|보험금청구서|기타",
  "patient_name": "환자 성명 또는 masked",
  "kcd_code": "KCD 코드 (예: K35.8) 또는 null",
  "diagnosis": "진단명 또는 null",
  "hospital_days": 입원일수(정수 또는 null),
  "admission_date": "입원일 또는 null",
  "discharge_date": "퇴원일 또는 null",
  "accident_date": "발병/사고일 또는 null",
  "covered_self_pay": 급여본인부담금(정수 또는 null),
  "non_covered": 비급여본인부담금(정수 또는 null),
  "total_self_pay": 최종본인납부액(정수 또는 null),
  "surgery_name": "수술명 또는 null",
  "surgery_code": "수술코드 또는 null",
  "ocr_notes": "이미지 품질 이슈나 불확실한 추출 사항 메모"
}
```

JSON만 반환하세요."""


# ══════════════════════════════════════════════════════════════════
# Vision OCR용 Structured Output JSON 스키마
# ══════════════════════════════════════════════════════════════════

_RECEIPT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "receipt_ocr",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "patient_name": {"type": ["string", "null"]},
                "patient_id": {"type": ["string", "null"]},
                "department": {"type": ["string", "null"]},
                "admission_date": {"type": ["string", "null"]},
                "discharge_date": {"type": ["string", "null"]},
                "hospital_days": {"type": ["integer", "null"]},
                "receipt_line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "covered": {"type": "integer"},
                            "non_covered": {"type": "integer"},
                            "subtotal": {"type": "integer"},
                        },
                        "required": ["category", "covered", "non_covered", "subtotal"],
                        "additionalProperties": False,
                    },
                },
                "receipt_summary": {
                    "type": "object",
                    "properties": {
                        "covered_subtotal": {"type": "integer"},
                        "covered_self_pay": {"type": "integer"},
                        "non_covered_subtotal": {"type": "integer"},
                        "public_insurance": {"type": "integer"},
                        "elective_care_fee": {"type": "integer"},
                        "total_self_pay": {"type": "integer"},
                    },
                    "required": [
                        "covered_subtotal", "covered_self_pay",
                        "non_covered_subtotal", "public_insurance",
                        "elective_care_fee", "total_self_pay",
                    ],
                    "additionalProperties": False,
                },
                "special_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_name": {"type": "string"},
                            "amount": {"type": "integer"},
                            "sessions": {"type": "integer"},
                        },
                        "required": ["item_name", "amount", "sessions"],
                        "additionalProperties": False,
                    },
                },
                "ocr_notes": {"type": ["string", "null"]},
            },
            "required": [
                "patient_name", "patient_id", "department",
                "admission_date", "discharge_date", "hospital_days",
                "receipt_line_items", "receipt_summary",
                "special_items", "ocr_notes",
            ],
            "additionalProperties": False,
        },
    },
}

_GENERIC_DOC_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "generic_doc_ocr",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "doc_type": {"type": "string"},
                "patient_name": {"type": ["string", "null"]},
                "kcd_code": {"type": ["string", "null"]},
                "diagnosis": {"type": ["string", "null"]},
                "hospital_days": {"type": ["integer", "null"]},
                "admission_date": {"type": ["string", "null"]},
                "discharge_date": {"type": ["string", "null"]},
                "accident_date": {"type": ["string", "null"]},
                "covered_self_pay": {"type": ["integer", "null"]},
                "non_covered": {"type": ["integer", "null"]},
                "total_self_pay": {"type": ["integer", "null"]},
                "surgery_name": {"type": ["string", "null"]},
                "surgery_code": {"type": ["string", "null"]},
                "ocr_notes": {"type": ["string", "null"]},
            },
            "required": [
                "doc_type", "patient_name", "kcd_code", "diagnosis",
                "hospital_days", "admission_date", "discharge_date",
                "accident_date", "covered_self_pay", "non_covered",
                "total_self_pay", "surgery_name", "surgery_code", "ocr_notes",
            ],
            "additionalProperties": False,
        },
    },
}


# ══════════════════════════════════════════════════════════════════
# Vision OCR용 이미지 전처리
# ══════════════════════════════════════════════════════════════════

def _preprocess_image_for_vision(image_path: Path) -> bytes:
    """
    Vision API 전송 전 이미지 전처리.

    1. EXIF 기반 자동 회전
    2. 해상도 정규화 (장변 1500~3000px)
    3. 대비 향상
    4. JPEG 품질 95로 재인코딩 (파일 크기 최적화)

    Returns:
        전처리된 이미지의 바이트 데이터
    """
    try:
        from PIL import Image, ImageEnhance, ImageOps
        import io

        img = Image.open(image_path)

        # 1. EXIF 회전 보정
        img = ImageOps.exif_transpose(img)

        # 2. RGBA/P → RGB 변환
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        # 3. 해상도 정규화 — 장변이 3000px 초과 시 축소, 1500px 미만 시 확대
        w, h = img.size
        long_side = max(w, h)
        if long_side > 3000:
            scale = 3000 / long_side
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        elif long_side < 1500:
            scale = 1500 / long_side
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        # 4. 대비 향상 (factor 1.3 — 미약하게)
        img = ImageEnhance.Contrast(img).enhance(1.3)

        # 5. JPEG로 재인코딩
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=95)
        return buffer.getvalue()

    except ImportError:
        # PIL 없으면 원본 바이트 반환
        return image_path.read_bytes()
    except Exception:
        # 전처리 실패 시 원본 바이트 반환
        return image_path.read_bytes()


# ══════════════════════════════════════════════════════════════════
# 영수증 OCR 산술 교차검증
# ══════════════════════════════════════════════════════════════════

def _validate_receipt_arithmetic(fields: dict, errors: list[str]) -> float:
    """
    영수증 OCR 결과의 산술적 일관성을 검증한다.

    검증 항목:
      - sum(line_items.covered) ≈ receipt_summary.covered_self_pay
      - sum(line_items.non_covered) ≈ receipt_summary.non_covered_subtotal

    Returns:
        신뢰도 보정값 (0.0 ~ 1.0). 일치하면 1.0, 불일치 심하면 0.7까지 하락.
    """
    line_items = fields.get("receipt_line_items", [])
    summary = fields.get("receipt_summary", {})

    if not line_items or not summary:
        return 1.0  # 검증 불가 — 보정 없음

    confidence_penalty = 1.0

    # 급여 본인부담금 합계 검증
    sum_covered = sum(item.get("covered", 0) for item in line_items)
    expected_covered = summary.get("covered_self_pay", 0)
    if expected_covered > 0 and sum_covered > 0:
        ratio = abs(sum_covered - expected_covered) / expected_covered
        if ratio > 0.1:  # 10% 이상 차이
            errors.append(
                f"산술 검증 경고: 급여 항목합({sum_covered:,}) ≠ "
                f"소계({expected_covered:,}), 차이율 {ratio:.1%}"
            )
            confidence_penalty = min(confidence_penalty, 0.7)
        elif ratio > 0.01:  # 1~10% 차이
            confidence_penalty = min(confidence_penalty, 0.9)

    # 비급여 합계 검증
    sum_non_covered = sum(item.get("non_covered", 0) for item in line_items)
    expected_non_covered = summary.get("non_covered_subtotal", 0)
    if expected_non_covered > 0 and sum_non_covered > 0:
        ratio = abs(sum_non_covered - expected_non_covered) / expected_non_covered
        if ratio > 0.1:
            errors.append(
                f"산술 검증 경고: 비급여 항목합({sum_non_covered:,}) ≠ "
                f"소계({expected_non_covered:,}), 차이율 {ratio:.1%}"
            )
            confidence_penalty = min(confidence_penalty, 0.7)
        elif ratio > 0.01:
            confidence_penalty = min(confidence_penalty, 0.9)

    return confidence_penalty


def _parse_image_with_vision(
    image_path: Path,
    doc_type_hint: str = "auto",
) -> tuple[dict, str, list[str]]:
    """
    GPT 멀티모달(Vision)으로 이미지에서 직접 필드를 추출한다.

    Args:
        image_path:    이미지 파일 경로
        doc_type_hint: "진료비영수증" 등 서류 유형 힌트. "auto"이면 LLM이 판별.

    Returns:
        (fields_dict, detected_doc_type, errors)
    """
    import base64
    import json as _json

    errors: list[str] = []

    try:
        from src.llm.client import chat as llm_chat, is_available as llm_available
        from config.settings import AGENT_LLM_MODEL
    except ImportError as e:
        errors.append(f"LLM 모듈 임포트 실패: {e}")
        return {}, "미분류", errors

    if not llm_available():
        errors.append("Vision OCR: LLM 클라이언트 미사용 가능 (API 키 확인)")
        return {}, "미분류", errors

    # 이미지 전처리 → base64
    try:
        img_bytes = _preprocess_image_for_vision(image_path)
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        errors.append(f"이미지 파일 읽기 실패: {e}")
        return {}, "미분류", errors

    # 전처리 후 MIME type은 JPEG 고정 (전처리가 JPEG로 재인코딩)
    mime_type = "image/jpeg"

    # 영수증 힌트면 전용 프롬프트 + 스키마, 아니면 범용
    is_receipt = doc_type_hint in ("진료비영수증", "receipt")
    prompt_text = _RECEIPT_VISION_PROMPT if is_receipt else _GENERIC_DOC_VISION_PROMPT
    response_fmt = _RECEIPT_RESPONSE_FORMAT if is_receipt else _GENERIC_DOC_RESPONSE_FORMAT

    # 멀티모달 메시지 구성
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{img_b64}",
                        "detail": "high",
                    },
                },
            ],
        }
    ]

    # Vision 모델 결정: VISION_OCR_MODEL > AGENT_LLM_MODEL > 기본 모델
    vision_model = VISION_OCR_MODEL if VISION_OCR_MODEL else AGENT_LLM_MODEL

    try:
        response = llm_chat(
            messages=messages,
            model=vision_model,
            max_tokens=4096,
            response_format=response_fmt,
        )
        raw_content = response.choices[0].message.content or ""

        # Structured Output으로 JSON이 보장되지만, 안전장치 유지
        json_text = raw_content.strip()
        if json_text.startswith("```"):
            lines = json_text.split("\n")
            start = next((i for i, l in enumerate(lines) if l.strip().startswith("{")), 1)
            end = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip().startswith("}")), len(lines) - 1)
            json_text = "\n".join(lines[start : end + 1])

        parsed = _json.loads(json_text)

    except _json.JSONDecodeError as e:
        errors.append(f"Vision OCR JSON 파싱 실패: {e}")
        return {}, "미분류", errors
    except Exception as e:
        errors.append(f"Vision OCR API 호출 실패: {e}")
        return {}, "미분류", errors

    # 서류 유형 결정
    if is_receipt:
        detected_type = "진료비영수증"
    else:
        detected_type = parsed.pop("doc_type", "미분류")
        if detected_type not in (
            "진단서", "입원확인서", "수술확인서",
            "진료비영수증", "진료비세부내역서", "보험금청구서",
        ):
            detected_type = "미분류"

    # OCR 메모 추출
    ocr_notes = parsed.pop("ocr_notes", None)
    if ocr_notes:
        errors.append(f"Vision OCR 메모: {ocr_notes}")

    # null → 제거, "masked" 필드 보존
    fields = {k: v for k, v in parsed.items() if v is not None}

    # 영수증일 때 산술 교차검증
    if is_receipt:
        _validate_receipt_arithmetic(fields, errors)

    # 마스킹 필드 가명 처리
    fields = _handle_masked_fields(fields)

    return fields, detected_type, errors


def parse_receipt_image(image_path: Path) -> ParsedDocument:
    """
    진료비 영수증 이미지 1장을 Vision OCR로 파싱하여 ParsedDocument를 반환.
    2차 심사 전용 진입점 — UI에서 추가 영수증 업로드 시 호출.

    Args:
        image_path: 영수증 이미지 파일 경로 (.jpg/.jpeg/.png)

    Returns:
        ParsedDocument (doc_type="진료비영수증", parse_mode="vision")
    """
    fields, doc_type, errors = _parse_image_with_vision(
        image_path, doc_type_hint="진료비영수증"
    )

    # receipt_summary → 기존 표준 키 호환 매핑
    summary = fields.get("receipt_summary", {})
    if summary:
        if "covered_self_pay" not in fields and "covered_self_pay" in summary:
            fields["covered_self_pay"] = summary["covered_self_pay"]
        if "non_covered" not in fields:
            fields["non_covered"] = summary.get("non_covered_subtotal", 0)
        if "total_self_pay" not in fields and "total_self_pay" in summary:
            fields["total_self_pay"] = summary["total_self_pay"]

    # 마스킹 필드 가명 처리 (이미 _parse_image_with_vision에서 1차 처리되지만 안전 재호출)
    fields = _handle_masked_fields(fields)

    # confidence 계산: 핵심 필드(covered_self_pay) 추출 여부 기반
    if fields.get("covered_self_pay") is not None:
        confidence = 0.9  # Vision OCR 성공 — regex(0.8)보다 높은 신뢰도
    elif summary:
        confidence = 0.7  # summary는 있지만 핵심 필드 누락
    else:
        confidence = 0.3  # 추출 실패에 가까움

    # raw_text는 Vision 추출 결과를 텍스트로 직렬화 (후속 regex 호환)
    import json as _json
    raw_text = _json.dumps(fields, ensure_ascii=False, indent=2)

    return ParsedDocument(
        doc_type=doc_type,
        raw_text=raw_text,
        fields=fields,
        parse_mode="vision",
        confidence=round(confidence, 2),
        parse_errors=errors,
    )


def _ocr_image(image_path: Path) -> tuple[str, list[str]]:
    """
    단일 이미지 파일(.jpg/.jpeg/.png)에 pytesseract OCR을 적용한다.
    언어: kor+eng (dual-pass)

    전처리 파이프라인:
      1. RGBA/P 모드 → RGB 변환
      2. 그레이스케일 (L 모드) → 노이즈 감소
      3. 300 DPI 기준 업스케일 (원본 해상도가 낙다면)
      4. 대비(Contrast) 향상
      5. 샤플닝(LANCZOS) 재샘플링
    """
    errors: list[str] = []

    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError as e:
        errors.append(
            f"OCR 의존성 누락: {e}. "
            "`pip install pytesseract pillow` 또는 `pip install -r requirements.txt`"
        )
        return "", errors

    try:
        pytesseract.get_tesseract_version()  # Tesseract 엔진 없으면 여기서 예외
    except pytesseract.TesseractNotFoundError:
        errors.append(
            "Tesseract OCR 엔진이 설치되지 않았습니다. "
            "macOS: `brew install tesseract tesseract-lang`"
        )
        return "", errors

    try:
        img = Image.open(image_path)

        # 1. 모드 정규화
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        # 2. 그레이스케일 전환 (텍스트 판별에 유리)
        img_gray = img.convert("L")

        # 3. 해상도 보정: 단방향 300 DPI 기준 2048px 미만이면 업스케일
        w, h = img_gray.size
        min_side = min(w, h)
        if min_side < 1000:
            scale = max(2.0, 1000 / min_side)
            new_w = int(w * scale)
            new_h = int(h * scale)
            img_gray = img_gray.resize((new_w, new_h), Image.LANCZOS)

        # 4. 대비 향상 (factor 1.5 — 시안성 유지)
        img_gray = ImageEnhance.Contrast(img_gray).enhance(1.5)

        # 5. 연합된 OEM 3 PSM 6으로 OCR
        config = "--oem 3 --psm 6"
        raw_text: str = pytesseract.image_to_string(img_gray, lang="kor+eng", config=config)
        raw_text = raw_text.strip()

        if not raw_text:
            errors.append(
                f"{image_path.name}: OCR 결과가 비어 있습니다. "
                "이미지 해상도나 방향을 확인하세요."
            )
        elif len(raw_text) < 30:
            errors.append(
                f"{image_path.name}: OCR 추출 텍스트가 너무 짧습니다 ({len(raw_text)}자). "
                "저해상도 이미지일 수 있습니다."
            )

        return raw_text, errors

    except Exception as e:
        errors.append(f"{image_path.name}: OCR 실패 — {e}")
        return "", errors


def _ocr_pdf_as_images(pdf_path: Path) -> tuple[str, list[str]]:
    """
    스캔 PDF(텍스트 레이어 없음)를 페이지별 이미지로 렌더링 후 OCR.
    pypdf2 / pymupdf(fitz) 중 사용 가능한 것을 자동 선택한다.
    """
    errors: list[str] = []

    # pymupdf(fitz)를 우선 시도 (PDF 페이지 → 이미지 렌더링 정확도 높음)
    try:
        import fitz  # pymupdf
    except ImportError:
        fitz = None

    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError as e:
        errors.append(f"스캔 PDF OCR 의존성 누락: {e}")
        return "", errors

    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        errors.append("Tesseract OCR 엔진 미설치 — `brew install tesseract tesseract-lang`")
        return "", errors

    pages_text: list[str] = []
    config = "--oem 3 --psm 6"

    if fitz is not None:
        try:
            doc = fitz.open(str(pdf_path))
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                text = pytesseract.image_to_string(img, lang="kor+eng", config=config)
                pages_text.append(text.strip())
            doc.close()
            raw_text = "\n".join(pages_text).strip()
            if raw_text:
                return raw_text, errors
            errors.append(f"{pdf_path.name}: pymupdf+OCR 결과 비어 있음")
            return "", errors
        except Exception as e:
            errors.append(f"{pdf_path.name}: pymupdf OCR 실패 — {e}, pypdf 폴백 시도")

    # pypdf 폴백: 각 페이지를 PyMuPDF 없이 이미지화할 수 없으므로
    # 자원이 없다는 안내만 반환
    errors.append(
        f"{pdf_path.name}: 스캔 PDF 이미지 OCR에 pymupdf가 필요합니다. "
        "`pip install pymupdf` 를 실행하세요."
    )
    return "", errors


# ══════════════════════════════════════════════════════════════════
# 서류 유형 판별
# ══════════════════════════════════════════════════════════════════

_DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    # 우선순위 높은 것부터 — 고유 키워드 기준으로 최우선 매칭
    "보험금청구서":      ["청구 담보", "청구인 서명", "접수번호"],
    "수술확인서":       ["수술확인서", "집도의", "수술 시간", "수술시간",
                         "수술일시", "수술코드", "마취방법"],
    # 입원확인서를 진단서보다 먼저: 입원확인서에 "주 상병명" 라벨이 포함될 수 있어
    # 진단서 키워드("주 상병명")로 오탐 방지
    # "입원 일수"는 진단서에도 등장하므로 제외 — "입원 사유" 라벨로만 구분
    "입원확인서":       ["입원확인서", "입원 사유"],
    "진단서":           ["질병분류기호", "주 상병명", "주 상병",
                         "주상병명", "KCD 코드", "KCD코드",
                         "질병코드", "상병코드"],
    # 영수증을 세부내역서보다 먼저: 영수증에 "진료비 세부내역서를 참고" 문구가 있어
    # "세부내역서" 키워드로 오탐하는 것을 방지
    # 영수증: "영수증", "납부금액" 등 영수증 고유 키워드 포함
    "진료비영수증":     ["공단 부담금", "급여 소계", "급여 합계",
                         "급여 진료비 총액", "영수증", "납부금액"],
    # 세부내역서: "항목코드", "단가", "횟수" 등 항목 테이블 고유 키워드
    "진료비세부내역서": ["항목코드", "세부내역서", "급여구분", "단가", "횟수"],
}


def detect_doc_type(text: str) -> str:
    """
    텍스트 내용으로 서류 유형 판별. 키워드 가중치 스코어링 방식.

    공백 정규화:
      실제 병원 서류는 장식용 스페이싱(‘수 술 확 인 서’, ‘집 도 의’)이나
      라벨 변형(‘주상병명’ vs ‘주 상병명’)이 흔하므로,
      원본·정규화·공백제거 텍스트 3종으로 매칭한다.
    """
    # 공백 정규화 변환
    normalized = re.sub(r'\s+', ' ', text)   # 연속 공백 → 단일 공백
    collapsed = re.sub(r'\s+', '', text)     # 모든 공백 제거 (장식 스페이싱 대응)

    # 문서 상단 제목 영역 (공백 제거 기준 ~300자)
    title_area = collapsed[:300]
    _TITLE_BONUS = 3

    scores: dict[str, int] = {}
    for doc_type, keywords in _DOC_TYPE_KEYWORDS.items():
        score = 0
        # 제목 영역에 문서 유형명이 포함되면 가산점
        type_collapsed = doc_type.replace(' ', '')
        if type_collapsed in title_area:
            score += _TITLE_BONUS
        # 키워드 매칭
        for kw in keywords:
            kw_no_space = kw.replace(' ', '')
            # 원본·정규화·공백제거 텍스트 중 하나에서 매칭되면 인정
            if kw in text or kw in normalized or kw_no_space in collapsed:
                score += 1
        if score > 0:
            scores[doc_type] = score
    if not scores:
        return "미분류"
    # 최고 스코어 유형 반환 (동점 시 dict 삽입 순서 — 우선순위 높은 유형 반환)
    return max(scores, key=scores.get)


# ══════════════════════════════════════════════════════════════════
# 날짜 유틸리티
# ══════════════════════════════════════════════════════════════════

def _to_iso_date(year: str, month: str, day: str) -> str:
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _extract_date_after_label(text: str, label_pattern: str) -> Optional[str]:
    """
    'label_pattern : 2024년 11월 09일' 형태에서 날짜 추출.
    label_pattern 은 re 패턴 문자열.
    """
    pattern = label_pattern + r'\s*[：:]\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일'
    m = re.search(pattern, text)
    if m:
        return _to_iso_date(m.group(1), m.group(2), m.group(3))
    return None


# ══════════════════════════════════════════════════════════════════
# 개별 필드 추출 함수
# ══════════════════════════════════════════════════════════════════

def extract_kcd_code(text: str) -> Optional[str]:
    """KCD 코드 추출 (예: K35.8, K70.3). 첫 번째 매칭 반환."""
    m = re.search(r'\b([A-Z]\d{2}(?:\.\d{1,2})?)\b', text)
    return m.group(1) if m else None


def extract_diagnosis(text: str) -> Optional[str]:
    """진단명 추출 (주 상병명 또는 진단명 라벨 기준)."""
    patterns = [
        r'주\s*상병명\s*[：:]\s*(.+?)(?:\n|$)',
        r'진단명\s*[：:]\s*(.+?)(?:\n|$)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = m.group(1).strip()
            # 괄호 안 영문 제거 후 정리
            val = re.sub(r'\s*\(.*?\)', '', val).strip()
            if val:
                return val
    return None


def extract_hospital_days(text: str) -> Optional[int]:
    """총 입원 일수 추출."""
    patterns = [
        r'총\s*입원\s*기간\s*[：:]\s*(\d+)\s*일',
        r'입원\s*일\s*수\s*[：:]\s*(\d+)\s*일',
        # 주의: \s* 대신 [ \t]* 사용하여 줄바꿈 넘어 매칭 방지
        # "05일\n입원일" 같은 날짜+라벨 오매칭 차단
        r'(\d+)[ \t]*일[ \t]*(?:간[ \t]*)?입원',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return None


def extract_accident_date(text: str) -> Optional[str]:
    """
    발병/사고일 추출.
    1) 정상 날짜 패턴 우선 추출 (다양한 라벨 지원)
    2) 비정형 만성질환 표현 감지 시 'CHRONIC_UNKNOWN' 반환
    """
    # 1차: 정상 날짜 추출 (다양한 라벨 패턴 지원)
    label_patterns = [
        r'발병.*?일',        # 발병일, 발병(사고)일, 발병일(추정)
        r'사고.*?일자?',       # 사고일, 사고일자
        r'최초\s*진단일',    # 최초진단일
        r'수술일',              # 수술일 (수술 케이스 폴백)
    ]
    for lp in label_patterns:
        result = _extract_date_after_label(text, lp)
        if result:
            return result

    # 2차: 비정형 만성질환 표현 감지
    chronic_pat = r'발병.*?일.*?[：:] *(수년|수개월|오래전|만성|불명|불상|미상|정확.*?불명)'
    if re.search(chronic_pat, text):
        return "CHRONIC_UNKNOWN"

    return None


def extract_admission_date(text: str) -> Optional[str]:
    """입원일 추출."""
    return _extract_date_after_label(text, r'입원일')


def extract_discharge_date(text: str) -> Optional[str]:
    """퇴원일 추출."""
    return _extract_date_after_label(text, r'퇴원일')


def extract_money_fields(text: str) -> dict[str, int]:
    """
    진료비영수증에서 금액 필드 추출.
    반환 키: covered_self_pay, non_covered, total_self_pay
    """
    result: dict[str, int] = {}
    patterns = {
        "covered_self_pay": r'급여\s*본인부담금\s*[：:]\s*([\d,]+)원',
        "non_covered":      r'비급여\s*본인부담금\s*[：:]\s*([\d,]+)원',
        "total_self_pay":   r'최종\s*본인\s*납부액\s*[：:]\s*([\d,]+)원',
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            result[key] = int(m.group(1).replace(",", ""))
    return result


def extract_surgery_info(text: str) -> dict:
    """
    수술확인서에서 수술명, 수술코드 추출.
    반환 키: surgery_name (str), surgery_code (str, optional)
    """
    result: dict = {}

    # 수술명 추출 — "수술명", "수 술 명" 등 장식 공백 포함 대응
    m_name = re.search(r'수\s*술\s*명\s*[：:]\s*(.+?)(?:\n|$)', text)
    if m_name:
        name = m_name.group(1).strip()
        # 괄호 안 영문 설명 제거
        name = re.sub(r'\s*\(.*?\)', '', name).strip()
        if name:
            result["surgery_name"] = name

    # 수술 코드 추출 (수술코드 또는 수술 코드 라벨) — 장식 공백 대응
    m_code = re.search(r'수\s*술\s*(?:코\s*드|분\s*류\s*코\s*드)\s*[：:]\s*([A-Z0-9]+)', text)
    if m_code:
        result["surgery_code"] = m_code.group(1).strip()

    return result


def extract_billing_items(text: str) -> list[dict]:
    """
    진료비세부내역서에서 항목코드·항목명·급여여부·금액·횟수 추출.
    반환: [{"item_code": str, "item_name": str, "is_noncovered": bool, "amount": int, "sessions": int | None}, ...]
    """
    items: list[dict] = []
    # 항목코드 패턴: 영문2자+숫자2~4자 (예: AA100, GH910, MX121)
    code_pattern = re.compile(r"^[ \t]*([A-Z]{2}\d{2,4}[A-Z0-9]*)\s+")
    # 금액: 쉼표 있는 숫자 + optional '원'
    amount_pattern = re.compile(r"([\d,]+)\s*원?\s*$|([\d,]+)\s*원?(?=\s|$)")
    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped or "항목코드" in line_stripped or "──" in line_stripped or "합계" in line_stripped:
            continue
        # 주석 필터링: ←, ※, (참고) 뒤 텍스트 제거 (금액 오인식 방지)
        line_clean = re.sub(r'[←※].*$', '', line_stripped).strip()
        if not line_clean:
            continue
        m_code = code_pattern.match(line_clean)
        if not m_code:
            continue
        item_code = m_code.group(1).strip()
        rest = line_clean[len(m_code.group(0)):].strip()
        is_noncovered = "비급여" in rest
        # 금액: 행에서 마지막으로 등장하는 숫자(쉼표 제거)
        numbers = re.findall(r"[\d,]+", rest)
        amount = 0
        if numbers:
            try:
                amount = int(numbers[-1].replace(",", ""))
            except ValueError:
                pass
        # 횟수: "N회" 또는 "N일" 추출 (선택)
        sessions = None
        sm = re.search(r"(\d+)\s*(?:회|일)\s*", rest)
        if sm:
            try:
                sessions = int(sm.group(1))
            except ValueError:
                pass
        items.append({
            "item_code": item_code,
            "item_name": rest.split()[0] if rest.split() else "",
            "is_noncovered": is_noncovered,
            "amount": amount,
            "sessions": sessions,
        })
    return items


def extract_claimed_coverages(text: str) -> list[str]:
    """
    보험금청구서에서 청구한 담보 유형 추출.
    [✓] 체크된 항목만 인식.
    반환: ["IND", "SIL", "SUR"] 조합
    """
    claimed: list[str] = []
    # 순서 보장을 위해 순차 확인
    if re.search(r'\[✓\][^\n]*입원일당', text):
        claimed.append("IND")
    if re.search(r'\[✓\][^\n]*수술비', text):
        claimed.append("SUR")
    if re.search(r'\[✓\][^\n]*실손의료비', text):
        claimed.append("SIL")
    return claimed


# ══════════════════════════════════════════════════════════════════
# LLM 파싱 (hybrid 모드 fallback)
# ══════════════════════════════════════════════════════════════════

def _parse_with_llm(raw_text: str, doc_type: str) -> dict:
    """
    LLM API를 이용한 서류 파싱.
    regex로 추출 실패한 필드를 LLM이 보완한다.
    중앙 LLM 클라이언트(src.llm.client)를 사용하므로 OpenAI / Azure 모두 지원.
    """
    try:
        from src.llm.client import chat as llm_chat, is_available as llm_available
        from config.settings import DOC_PARSE_LLM_MODEL
        import json as _json

        if not llm_available():
            return {"_llm_error": "LLM 클라이언트 미사용 가능 (API 키 확인)"}

        prompt = f"""다음은 보험 청구 서류({doc_type})의 텍스트입니다.
아래 JSON 형식으로 정보를 추출해 주세요. 없는 필드는 null로 반환하세요.

서류 텍스트:
{raw_text[:3000]}

추출할 JSON:
{{
  "kcd_code": "KCD 코드 (예: K35.8)",
  "diagnosis": "진단명",
  "hospital_days": 입원일수(정수 또는 null),
  "accident_date": "발병일 YYYY-MM-DD 형식",
  "admission_date": "입원일 YYYY-MM-DD 형식",
  "discharge_date": "퇴원일 YYYY-MM-DD 형식",
  "covered_self_pay": 급여본인부담금(정수 또는 null),
  "non_covered": 비급여본인부담금(정수 또는 null),
  "total_self_pay": 최종본인납부액(정수 또는 null),
  "surgery_name": "수술명",
  "surgery_code": "수술코드",
  "claimed_coverage_types": ["IND", "SIL", "SUR"] 중 청구된 것 목록
}}

JSON만 반환하세요."""

        response = llm_chat(
            messages=[{"role": "user", "content": prompt}],
            model=DOC_PARSE_LLM_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        parsed = _json.loads(raw)
        # null → None 처리 및 타입 정규화
        return {k: v for k, v in parsed.items() if v is not None}

    except Exception as e:
        return {"_llm_error": str(e)}

    return {}


# ══════════════════════════════════════════════════════════════════
# 단일 서류 파싱
# ══════════════════════════════════════════════════════════════════

def parse_document(file_path: Path, mode: str = None) -> ParsedDocument:
    """
    단일 서류 파일 파싱.
    mode: "regex" | "llm" | "hybrid" (None이면 settings.DOC_PARSE_MODE 사용)
    """
    if mode is None:
        mode = DOC_PARSE_MODE

    # OCR 파일(이미지/스캔 PDF)는 parse_mode를 'ocr'로 자동 주기함
    _suffix = file_path.suffix.lower()
    _is_ocr_source = _suffix in (".jpg", ".jpeg", ".png")

    # ── Vision OCR 경로: 이미지 파일 + OCR_BACKEND가 vision/hybrid ──
    if _is_ocr_source and OCR_BACKEND in ("vision", "hybrid"):
        fields, doc_type, v_errors = _parse_image_with_vision(
            file_path, doc_type_hint="auto"
        )
        if fields:  # Vision 성공
            # receipt_summary → 기존 표준 키 호환
            summary = fields.get("receipt_summary", {})
            if summary:
                if "covered_self_pay" not in fields and "covered_self_pay" in summary:
                    fields["covered_self_pay"] = summary["covered_self_pay"]
                if "non_covered" not in fields:
                    fields["non_covered"] = summary.get("non_covered_subtotal", 0)
                if "total_self_pay" not in fields and "total_self_pay" in summary:
                    fields["total_self_pay"] = summary["total_self_pay"]

            # 마스킹 필드 가명 처리
            fields = _handle_masked_fields(fields)

            confidence = 0.9 if fields.get("covered_self_pay") is not None else 0.7
            import json as _json
            raw_text = _json.dumps(fields, ensure_ascii=False, indent=2)
            return ParsedDocument(
                doc_type=doc_type,
                raw_text=raw_text,
                fields=fields,
                parse_mode="vision",
                confidence=round(confidence, 2),
                parse_errors=v_errors,
            )
        # Vision 실패 + hybrid → tesseract 폴백
        if OCR_BACKEND == "hybrid":
            pass  # 아래 기존 OCR 경로로 진행
        else:
            # vision-only 모드에서 실패
            return ParsedDocument(
                doc_type="미분류",
                raw_text="",
                fields={},
                parse_mode="vision",
                confidence=0.0,
                parse_errors=v_errors,
            )

    raw_text, errors = extract_text_from_file(file_path)
    doc_type = detect_doc_type(raw_text) if raw_text else "미분류"

    # OCR 유래 파일: parse_mode 기록 처리
    if _is_ocr_source:
        mode = "ocr"

    fields: dict = {}

    # 텍스트 추출 실패 시 즉시 반환 (confidence=0)
    if not raw_text:
        return ParsedDocument(
            doc_type=doc_type,
            raw_text="",
            fields={},
            parse_mode=mode,
            confidence=0.0,
            parse_errors=errors,
        )

    # ── regex 추출 ────────────────────────────────────────────────
    kcd = extract_kcd_code(raw_text)
    if kcd:
        fields["kcd_code"] = kcd

    diagnosis = extract_diagnosis(raw_text)
    if diagnosis:
        fields["diagnosis"] = diagnosis

    days = extract_hospital_days(raw_text)
    if days is not None:
        fields["hospital_days"] = days

    accident_date = extract_accident_date(raw_text)
    if accident_date:
        fields["accident_date"] = accident_date

    admission_date = extract_admission_date(raw_text)
    if admission_date:
        fields["admission_date"] = admission_date

    discharge_date = extract_discharge_date(raw_text)
    if discharge_date:
        fields["discharge_date"] = discharge_date

    money = extract_money_fields(raw_text)
    fields.update(money)

    surgery = extract_surgery_info(raw_text)
    fields.update(surgery)

    if doc_type == "보험금청구서":
        claimed = extract_claimed_coverages(raw_text)
        if claimed:
            fields["claimed_coverage_types"] = claimed

    if doc_type == "진료비세부내역서":
        billing = extract_billing_items(raw_text)
        if billing:
            fields["billing_items"] = billing

    # ── regex 결과 신뢰도 평가 ────────────────────────────────────
    # 서류 유형별로 "핵심 필드" 정의 → 해당 필드 추출 여부로 confidence 계산
    _CORE_FIELDS_BY_DOC: dict[str, list[str]] = {
        "진단서":         ["kcd_code", "hospital_days"],
        "입원확인서":     ["kcd_code", "hospital_days"],
        "수술확인서":     ["surgery_name"],
        "진료비영수증":   ["covered_self_pay"],
        "진료비세부내역서": [],   # 항목 파싱은 Phase 2 — 현재 confidence 평가 대상 아님
        "보험금청구서":   ["claimed_coverage_types"],  # 담보 체크박스 추출 여부
    }
    core_fields = _CORE_FIELDS_BY_DOC.get(doc_type, ["kcd_code"])
    if not core_fields:
        confidence = 1.0  # 진료비세부내역서처럼 평가 필드 없으면 중립값
    else:
        extracted_core = sum(1 for f in core_fields if f in fields)
        confidence = extracted_core / len(core_fields)
    # OCR 유래 파일은 confidence 최대 0.8 제한
    # (구조화된 텍스트 베이스 대비 OCR 노이즈/오입력 가능성)
    if _is_ocr_source:
        confidence = min(confidence, 0.8)
        if errors:  # OCR 경고 있으면 저한되고 보수적
            confidence = min(confidence, 0.5)
    # ── LLM fallback (hybrid 또는 llm 모드) ───────────────────────
    if mode in ("llm", "hybrid"):
        if mode == "llm" or confidence < 0.5:
            llm_fields = _parse_with_llm(raw_text, doc_type)
            if "_llm_error" in llm_fields:
                errors.append(f"LLM 파싱 오류: {llm_fields['_llm_error']}")
            else:
                # LLM 결과로 누락 필드 보완 (기존 regex 결과 우선)
                for k, v in llm_fields.items():
                    if k not in fields and v is not None:
                        fields[k] = v
                        confidence = min(confidence + 0.1, 1.0)

    return ParsedDocument(
        doc_type=doc_type,
        raw_text=raw_text,
        fields=fields,
        parse_mode=mode,
        confidence=round(confidence, 2),
        parse_errors=errors,
    )


# 지원 확장자 목록 (우선순위 순)
_SUPPORTED_EXTENSIONS = (".txt", ".pdf", ".jpg", ".jpeg", ".png")


def parse_claim_documents(doc_dir: Path, mode: str = None) -> list[ParsedDocument]:
    """
    청구 서류 디렉토리의 모든 지원 파일(.txt, .pdf)을 파싱하여 목록으로 반환.

    동일 파일명의 .txt·.pdf 가 모두 있으면 .txt 우선 (텍스트가 더 신뢰성 있음).
    파일명 기준 정렬(번호순).
    """
    docs: list[ParsedDocument] = []
    seen_stems: set[str] = set()

    # 확장자 우선순위대로 수집 — .txt 를 먼저, 그다음 .pdf
    # 같은 stem 이 .txt / .pdf 모두 있으면 .txt 우선 처리 후 .pdf 건너뜀
    candidates: list[Path] = []
    for ext in _SUPPORTED_EXTENSIONS:
        candidates.extend(doc_dir.glob(f"*{ext}"))

    # 같은 stem 내에서 확장자 우선순위 적용 후, 파일명으로 정렬
    def _sort_key(p: Path) -> tuple:
        ext_rank = _SUPPORTED_EXTENSIONS.index(p.suffix.lower()) if p.suffix.lower() in _SUPPORTED_EXTENSIONS else 99
        return (p.stem, ext_rank)

    for f in sorted(candidates, key=_sort_key):
        if f.stem in seen_stems:
            continue  # 동일 stem의 .txt 가 먼저 처리됐으면 .pdf 건너뜀
        seen_stems.add(f.stem)
        docs.append(parse_document(f, mode=mode))

    return docs
