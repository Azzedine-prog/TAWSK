"""Minimal Firebase-backed authentication with local fallback.

Credentials are read from the ``FIREBASE_CREDENTIALS`` environment
variable (path to a service account JSON). When Firebase is unavailable,
credentials are stored locally under ``~/.study_tracker/users.json`` so
the login workflow remains functional offline.
"""
from __future__ import annotations

import json
import logging
import os
from hashlib import sha256
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:  # noqa: BLE001
    firebase_admin = None  # type: ignore
    credentials = None  # type: ignore
    firestore = None  # type: ignore


class FirebaseAuthManager:
    """Handle signup/login using Firebase when configured."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.local_users = storage_dir / "users.json"
        self._firestore = self._init_firestore()

    def _init_firestore(self):
        creds_path = os.getenv("FIREBASE_CREDENTIALS")
        if not creds_path or firebase_admin is None or credentials is None or firestore is None:
            return None
        try:
            if not firebase_admin._apps:  # type: ignore[attr-defined]
                firebase_admin.initialize_app(credentials.Certificate(creds_path))
            return firestore.client()
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to initialize Firebase; falling back to local auth")
            return None

    def _hash(self, password: str) -> str:
        return sha256(password.encode("utf-8")).hexdigest()

    def _local_load(self) -> dict:
        if self.local_users.exists():
            try:
                return json.loads(self.local_users.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to read local users file; resetting")
        return {}

    def _local_save(self, data: dict) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.local_users.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def sign_up(self, email: str, password: str) -> str:
        """Register a user in Firebase or locally; returns user id."""

        hashed = self._hash(password)
        if self._firestore:
            try:
                doc_ref = self._firestore.collection("users").document(email)
                doc_ref.set({"email": email, "password_hash": hashed})
                return email
            except Exception:  # noqa: BLE001
                LOGGER.exception("Firebase sign-up failed; falling back to local")

        data = self._local_load()
        data[email] = hashed
        self._local_save(data)
        return email

    def sign_in(self, email: str, password: str) -> Optional[str]:
        """Authenticate against Firebase or local store."""

        hashed = self._hash(password)
        if self._firestore:
            try:
                doc = self._firestore.collection("users").document(email).get()
                if doc.exists and doc.to_dict().get("password_hash") == hashed:
                    return email
            except Exception:  # noqa: BLE001
                LOGGER.exception("Firebase sign-in failed; trying local store")

        data = self._local_load()
        if data.get(email) == hashed:
            return email
        return None

