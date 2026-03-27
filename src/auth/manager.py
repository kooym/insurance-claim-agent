"""
사용자 인증 관리 — JSON 파일 기반 인증/계정 관리.

- data/users.json 을 유일한 사용자 DB로 사용한다.
- 비밀번호는 SHA-256 + per-user salt 로 해시하여 저장한다.
- 최초 실행 시 admin 계정을 자동 생성한다.
- Streamlit 의존성 없음 (순수 데이터 계층).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from config.settings import PROJECT_ROOT

USERS_DB_PATH = PROJECT_ROOT / "data" / "users.json"

_ADMIN_USERNAME = "admin"
_ADMIN_PASSWORD = "ktinnovationhub1!"


class AuthManager:
    """JSON 파일 기반 사용자 인증 관리자."""

    def __init__(self, db_path: Path = USERS_DB_PATH) -> None:
        self._db_path = db_path
        self._ensure_db()

    # ── DB 파일 읽기/쓰기 ────────────────────────────────────

    def _ensure_db(self) -> None:
        """DB 파일이 없으면 admin 계정으로 초기화."""
        if not self._db_path.exists():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            salt = os.urandom(16).hex()
            password_hash = self._hash_password(_ADMIN_PASSWORD, salt)
            initial_data = {
                "users": {
                    _ADMIN_USERNAME: {
                        "username": _ADMIN_USERNAME,
                        "password_hash": password_hash,
                        "salt": salt,
                        "name": "관리자",
                        "role": "admin",
                        "status": "approved",
                        "created_at": datetime.now().isoformat(),
                        "reason": "시스템 관리자",
                    }
                }
            }
            self._save_db(initial_data)

    def _load_db(self) -> dict:
        with open(self._db_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_db(self, data: dict) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 비밀번호 해싱 ───────────────────────────────────────

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    @staticmethod
    def _strip_secrets(user: dict) -> dict:
        """password_hash, salt 제거한 사용자 정보 반환."""
        return {k: v for k, v in user.items() if k not in ("password_hash", "salt")}

    # ── Public API ───────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> tuple[dict | None, str]:
        """
        로그인 인증.

        Returns:
            (user_dict, "") on success
            (None, "not_found") — 존재하지 않는 아이디
            (None, "wrong_password") — 비밀번호 불일치
            (None, "pending") — 승인 대기 중
            (None, "rejected") — 요청 거절됨
        """
        data = self._load_db()
        user = data["users"].get(username)

        if user is None:
            return None, "not_found"

        if user["status"] == "pending":
            return None, "pending"

        if user["status"] == "rejected":
            return None, "rejected"

        expected = self._hash_password(password, user["salt"])
        if expected != user["password_hash"]:
            return None, "wrong_password"

        return self._strip_secrets(user), ""

    def register_request(
        self, username: str, password: str, name: str, reason: str
    ) -> tuple[bool, str]:
        """
        계정 등록 요청. status='pending'으로 저장.

        Returns:
            (True, "접수 완료 메시지") / (False, "에러 메시지")
        """
        username = username.strip()
        name = name.strip()
        reason = reason.strip()

        if len(username) < 3:
            return False, "아이디는 3자 이상이어야 합니다."
        if len(password) < 6:
            return False, "비밀번호는 6자 이상이어야 합니다."
        if not name:
            return False, "이름을 입력해 주세요."
        if not reason:
            return False, "사유를 입력해 주세요."

        data = self._load_db()
        if username in data["users"]:
            return False, "이미 존재하는 아이디입니다."

        salt = os.urandom(16).hex()
        data["users"][username] = {
            "username": username,
            "password_hash": self._hash_password(password, salt),
            "salt": salt,
            "name": name,
            "role": "user",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "reason": reason,
        }
        self._save_db(data)
        return True, "계정 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다."

    def get_pending_requests(self) -> list[dict]:
        """status='pending'인 사용자 목록 반환."""
        data = self._load_db()
        return [
            self._strip_secrets(u)
            for u in data["users"].values()
            if u.get("status") == "pending"
        ]

    def approve_user(self, username: str) -> bool:
        """사용자 승인 (status → 'approved')."""
        data = self._load_db()
        user = data["users"].get(username)
        if not user or user["status"] != "pending":
            return False
        user["status"] = "approved"
        self._save_db(data)
        return True

    def reject_user(self, username: str) -> bool:
        """사용자 거절 (status → 'rejected')."""
        data = self._load_db()
        user = data["users"].get(username)
        if not user or user["status"] != "pending":
            return False
        user["status"] = "rejected"
        self._save_db(data)
        return True

    def is_admin(self, username: str) -> bool:
        data = self._load_db()
        return data["users"].get(username, {}).get("role") == "admin"

    def get_all_users(self) -> list[dict]:
        """모든 사용자 목록 반환 (password_hash/salt 제외)."""
        data = self._load_db()
        return [self._strip_secrets(u) for u in data["users"].values()]
