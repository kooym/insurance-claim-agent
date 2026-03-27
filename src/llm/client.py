"""
OpenAI / Azure OpenAI 클라이언트 싱글턴 + 토큰·비용 추적.

설계 원칙:
  - LLM_PROVIDER 에 따라 OpenAI 또는 Azure OpenAI 클라이언트를 생성한다.
  - .env 파일은 git에 절대 포함하지 않는다 (.gitignore 등록 확인 ✅).
  - 키가 없으면 클라이언트를 생성하지 않고 None 을 반환한다.
  - 호출 시마다 토큰 사용량을 누적하여 비용 추적을 지원한다.

공개 API:
  get_client()           → openai.OpenAI | openai.AzureOpenAI | None
  is_available()         → bool
  chat(messages, **kw)   → ChatCompletion (자동 토큰 추적)
  get_usage_stats()      → dict  (누적 토큰·비용 현황)
  reset_usage_stats()    → None

사용 예:
  from src.llm.client import chat, is_available
  if is_available():
      resp = chat([{"role": "user", "content": "안녕"}], model="gpt-4o")
"""
from __future__ import annotations

import logging
import threading
import traceback
from typing import Any, Optional

from config.settings import (
    OPENAI_API_KEY,
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# openai 패키지 import — lazy import (매 시도마다 재시도 가능)
# ══════════════════════════════════════════════════════════════════
_openai_available = False
_AzureOpenAI = None
_OpenAI = None


def _ensure_openai_imports() -> bool:
    """openai 패키지를 lazy import 한다. 실패 시 False."""
    global _openai_available, _AzureOpenAI, _OpenAI
    if _openai_available:
        return True
    try:
        from openai import AzureOpenAI as _Az, OpenAI as _Oi  # type: ignore
        _AzureOpenAI = _Az
        _OpenAI = _Oi
        _openai_available = True
        return True
    except ImportError:
        logger.warning("openai 패키지 미설치 — pip install openai>=1.40.0")
        return False

# ══════════════════════════════════════════════════════════════════
# GPT-4o 모델별 토큰 단가 (USD, 2024-12 기준)
# ══════════════════════════════════════════════════════════════════
_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4-turbo": {"input": 10.00 / 1_000_000, "output": 30.00 / 1_000_000},
    "gpt-5.3-chat": {"input": 2.00 / 1_000_000, "output": 8.00 / 1_000_000},
    "gpt-5-turbo": {"input": 3.00 / 1_000_000, "output": 12.00 / 1_000_000},
}

# ══════════════════════════════════════════════════════════════════
# 싱글턴 클라이언트
# ══════════════════════════════════════════════════════════════════
_client: Optional[Any] = None  # openai.OpenAI | openai.AzureOpenAI
_client_lock = threading.Lock()
_client_error: Optional[str] = None  # 마지막 초기화 실패 사유


def _is_azure() -> bool:
    """Azure OpenAI 공급자인지 판별."""
    return LLM_PROVIDER.lower() == "azure"


def get_client():
    """OpenAI / Azure OpenAI 클라이언트를 반환. 키가 없으면 None."""
    global _client, _client_error
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        # openai 패키지 lazy import (매 호출 시 재시도)
        if not _ensure_openai_imports():
            _client_error = "openai 패키지 미설치 (pip install openai>=1.40.0)"
            return None

        # API 키 유효성 검사
        if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-..."):
            _client_error = "OPENAI_API_KEY 미설정"
            logger.info("OPENAI_API_KEY 미설정 — LLM 클라이언트 비활성")
            return None

        try:
            if _is_azure():
                # ── Azure OpenAI ──────────────────────────────
                if not AZURE_OPENAI_ENDPOINT:
                    _client_error = "AZURE_OPENAI_ENDPOINT 미설정"
                    logger.error(
                        "LLM_PROVIDER=azure 이지만 AZURE_OPENAI_ENDPOINT 미설정. "
                        ".env에 AZURE_OPENAI_ENDPOINT를 추가하세요."
                    )
                    return None

                _client = _AzureOpenAI(
                    api_key=OPENAI_API_KEY,
                    azure_endpoint=AZURE_OPENAI_ENDPOINT,
                    api_version=AZURE_OPENAI_API_VERSION,
                    timeout=LLM_TIMEOUT_SECONDS,
                    max_retries=LLM_MAX_RETRIES,
                )
                _client_error = None  # 성공 시 에러 리셋
                logger.info(
                    "Azure OpenAI 클라이언트 초기화 완료 (endpoint=%s, deployment=%s)",
                    AZURE_OPENAI_ENDPOINT,
                    AZURE_OPENAI_DEPLOYMENT or LLM_MODEL,
                )
            else:
                # ── Standard OpenAI ───────────────────────────
                _client = _OpenAI(
                    api_key=OPENAI_API_KEY,
                    timeout=LLM_TIMEOUT_SECONDS,
                    max_retries=LLM_MAX_RETRIES,
                )
                _client_error = None
                logger.info("OpenAI 클라이언트 초기화 완료 (model=%s)", LLM_MODEL)

            return _client
        except Exception as exc:
            _client_error = f"클라이언트 초기화 실패: {exc}"
            logger.error("LLM 클라이언트 초기화 실패: %s", exc)
            traceback.print_exc()
            return None


def get_client_error() -> Optional[str]:
    """마지막 클라이언트 초기화 실패 사유. 성공이면 None."""
    return _client_error


def is_available() -> bool:
    """LLM API 사용 가능 여부."""
    return get_client() is not None


def reset_client() -> None:
    """클라이언트 싱글턴을 완전 리셋한다 (재연결 시 사용)."""
    global _client, _client_error, _openai_available
    with _client_lock:
        _client = None
        _client_error = None
        _openai_available = False  # lazy import 가 다시 시도하도록
    logger.info("LLM 클라이언트 리셋 완료 — 다음 호출 시 재초기화")


# ══════════════════════════════════════════════════════════════════
# 토큰·비용 추적
# ══════════════════════════════════════════════════════════════════
_usage_lock = threading.Lock()
_usage: dict[str, Any] = {
    "total_calls": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cost_usd": 0.0,
    "by_model": {},  # model → {calls, input_tokens, output_tokens, cost_usd}
}


def _track_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """호출 후 토큰 사용량 누적."""
    pricing = _PRICING.get(model, _PRICING.get("gpt-4o-mini"))
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]

    with _usage_lock:
        _usage["total_calls"] += 1
        _usage["total_input_tokens"] += input_tokens
        _usage["total_output_tokens"] += output_tokens
        _usage["total_cost_usd"] += cost

        entry = _usage["by_model"].setdefault(model, {
            "calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        })
        entry["calls"] += 1
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens
        entry["cost_usd"] += cost


def get_usage_stats() -> dict:
    """현재 누적 토큰·비용 현황 반환."""
    with _usage_lock:
        return {**_usage, "by_model": {k: {**v} for k, v in _usage["by_model"].items()}}


def reset_usage_stats() -> None:
    """사용량 통계 초기화."""
    with _usage_lock:
        _usage["total_calls"] = 0
        _usage["total_input_tokens"] = 0
        _usage["total_output_tokens"] = 0
        _usage["total_cost_usd"] = 0.0
        _usage["by_model"].clear()


# ══════════════════════════════════════════════════════════════════
# 편의 API: chat()
# ══════════════════════════════════════════════════════════════════

def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
    response_format: Optional[dict] = None,
    **kwargs,
):
    """
    Chat Completion 호출 + 자동 토큰 추적.

    Azure OpenAI 사용 시 model 파라미터는 자동으로
    AZURE_OPENAI_DEPLOYMENT 으로 매핑된다.
    GPT-5 계열 등 신형 모델은 max_completion_tokens 를 사용하고,
    GPT-4 계열은 max_tokens 를 사용한다.

    멀티모달 지원:
      content 필드에 text + image_url 블록을 함께 전달 가능.
      예: {"role": "user", "content": [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
          ]}

    Args:
        messages:        대화 메시지 목록 (텍스트 또는 멀티모달 content)
        model:           사용 모델 (기본: settings.LLM_MODEL)
        temperature:     생성 온도 (기본: 0.1 — 결정적)
        max_tokens:      최대 출력 토큰
        response_format: JSON 모드 등 응답 포맷
        **kwargs:        OpenAI API 추가 파라미터

    Returns:
        ChatCompletion 객체

    Raises:
        RuntimeError: API 키 미설정 시
    """
    client = get_client()
    if client is None:
        raise RuntimeError(
            "LLM API 키가 설정되지 않았습니다. "
            ".env 파일에 OPENAI_API_KEY (및 Azure 사용 시 AZURE_OPENAI_ENDPOINT)를 입력하세요."
        )

    use_model = model or LLM_MODEL
    resolved_max_tokens = max_tokens if max_tokens is not None else LLM_MAX_TOKENS

    # Azure OpenAI: deployment name 을 model 로 사용
    if _is_azure() and AZURE_OPENAI_DEPLOYMENT:
        use_model = AZURE_OPENAI_DEPLOYMENT

    # GPT-5 계열 신형 모델: max_completion_tokens 사용
    # GPT-4 계열 구형 모델: max_tokens 사용
    _use_completion_tokens = any(
        s in use_model.lower()
        for s in ("gpt-5", "o1", "o3", "o4")
    )

    call_kwargs: dict[str, Any] = {
        "model": use_model,
        "messages": messages,
        **kwargs,
    }

    # GPT-5 / o-series 모델은 temperature 파라미터 미지원 (기본값 1만 허용)
    # → 명시적 temperature 설정 시 오류 발생하므로 제거
    if not _use_completion_tokens:
        call_kwargs["temperature"] = temperature
    # else: GPT-5/o-series — temperature 키 자체를 넣지 않음

    if _use_completion_tokens:
        call_kwargs["max_completion_tokens"] = resolved_max_tokens
    else:
        call_kwargs["max_tokens"] = resolved_max_tokens

    if response_format:
        call_kwargs["response_format"] = response_format

    response = client.chat.completions.create(**call_kwargs)

    # 토큰 추적
    usage = response.usage
    if usage:
        _track_usage(
            model=use_model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
        logger.debug(
            "chat(%s): %d in + %d out tokens",
            use_model, usage.prompt_tokens, usage.completion_tokens,
        )

    return response
