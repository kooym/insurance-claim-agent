"""
Agent 일일 사용량 추적기 — JSON 파일 기반.

하루 단위로 Agent 호출 횟수를 추적하고, 일일 한도 초과 시
자동으로 룰 기반 모드로 폴백하기 위한 유틸리티.

설계 원칙:
  - 파일 기반 (data/agent_usage.json) — DB 불필요.
  - 날짜가 바뀌면 자동 리셋.
  - thread-safe (Lock 사용).
  - git에 추적 데이터가 포함되지 않도록 .gitignore 에 등록.

공개 API:
  can_use()          → bool       (일일 한도 이내인지)
  record_usage()     → int        (사용 후 남은 건수)
  get_today_usage()  → dict       (오늘 사용량 현황)
  get_remaining()    → int        (남은 건수)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date
from pathlib import Path

from config.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────────────────────
# settings.py 에서 가져오기 (TASK-E1에서 추가됨)
try:
    from config.settings import AGENT_DAILY_LIMIT, AGENT_UNLIMITED_MODE
except ImportError:
    AGENT_DAILY_LIMIT = 50
    AGENT_UNLIMITED_MODE = False


def _is_unlimited() -> bool:
    """무제한 모드 여부를 런타임에 판별 (모듈 상수 + env 직접 재확인)."""
    if AGENT_UNLIMITED_MODE:
        return True
    # 모듈 로드 시 .env 적용 전이었을 수 있으므로 env 직접 체크
    return os.getenv("AGENT_UNLIMITED_MODE", "false").lower() == "true"

_USAGE_FILE = PROJECT_ROOT / "data" / "agent_usage.json"
_lock = threading.Lock()


def _today_str() -> str:
    return date.today().isoformat()


def _load() -> dict:
    """사용량 파일 로드. 날짜가 다르면 리셋."""
    if not _USAGE_FILE.exists():
        return {"date": _today_str(), "count": 0, "history": []}

    try:
        data = json.loads(_USAGE_FILE.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"date": _today_str(), "count": 0, "history": []}

    # 날짜 변경 → 리셋
    if data.get("date") != _today_str():
        # 이전 날짜 기록을 히스토리에 보존
        history = data.get("history", [])
        if data.get("date") and data.get("count", 0) > 0:
            history.append({
                "date": data["date"],
                "count": data["count"],
            })
            # 최근 30일만 보존
            history = history[-30:]
        return {"date": _today_str(), "count": 0, "history": history}

    return data


def _save(data: dict) -> None:
    """사용량 파일 저장."""
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def can_use() -> bool:
    """일일 한도 이내인지 확인. AGENT_UNLIMITED_MODE=true 시 항상 True."""
    if _is_unlimited():
        return True
    with _lock:
        data = _load()
        return data["count"] < AGENT_DAILY_LIMIT


def record_usage() -> int:
    """
    사용 1건 기록하고 남은 건수를 반환.

    Returns:
        남은 건수 (0이면 한도 도달)
    """
    with _lock:
        data = _load()
        data["count"] += 1
        _save(data)
        remaining = max(0, AGENT_DAILY_LIMIT - data["count"])
        logger.info(
            "Agent 사용 기록: %d/%d (잔여 %d건)",
            data["count"], AGENT_DAILY_LIMIT, remaining,
        )
        return remaining


def get_today_usage() -> dict:
    """오늘 사용량 현황 반환. AGENT_UNLIMITED_MODE=true 시 remaining=무한."""
    with _lock:
        data = _load()
        count = data.get("count", 0)
        if _is_unlimited():
            return {
                "date": data.get("date", _today_str()),
                "count": count,
                "limit": -1,  # -1 = 무제한
                "remaining": 999999,
                "unlimited": True,
            }
        return {
            "date": data.get("date", _today_str()),
            "count": count,
            "limit": AGENT_DAILY_LIMIT,
            "remaining": max(0, AGENT_DAILY_LIMIT - count),
            "unlimited": False,
        }


def get_remaining() -> int:
    """남은 건수. AGENT_UNLIMITED_MODE=true 시 999999."""
    if _is_unlimited():
        return 999999
    with _lock:
        data = _load()
        return max(0, AGENT_DAILY_LIMIT - data.get("count", 0))
