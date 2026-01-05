from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


_ARXIV_VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)


def normalize_arxiv_id(arxiv_id: str, scope: str) -> str:
    scope = (scope or "").strip().lower()
    if scope not in ("base", "version"):
        raise ValueError("seen_scope 仅支持 'base' 或 'version'")
    if scope == "version":
        return arxiv_id
    return _ARXIV_VERSION_RE.sub("", arxiv_id)


@dataclass
class SeenDb:
    path: Path
    scope: str = "base"
    retention_days: int = 30
    ids: dict[str, str] | None = None

    def load(self) -> dict[str, str]:
        if self.ids is not None:
            return self.ids
        if not self.path.exists():
            self.ids = {}
            return self.ids
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.ids = {}
            return self.ids

        # 兼容两种格式：
        # 1) 旧：{"2601.00770": "2026-01-05", ...}
        # 2) 新：{"scope": "...", "ids": {...}}
        if isinstance(data, dict) and "ids" in data and isinstance(data["ids"], dict):
            ids = {str(k): str(v) for k, v in data["ids"].items()}
        elif isinstance(data, dict):
            ids = {str(k): str(v) for k, v in data.items()}
        else:
            ids = {}
        self.ids = ids
        return ids

    def prune(self, now_utc: datetime | None = None) -> None:
        ids = self.load()
        if self.retention_days <= 0:
            return
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        cutoff = (now_utc.date() - timedelta(days=self.retention_days)).isoformat()
        kept: dict[str, str] = {}
        for k, v in ids.items():
            if not v:
                continue
            try:
                d = date.fromisoformat(v[:10]).isoformat()
            except Exception:
                continue
            if d >= cutoff:
                kept[k] = d
        self.ids = kept

    def mark_processed(self, arxiv_ids: list[str], now_utc: datetime | None = None) -> None:
        ids = self.load()
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        stamp = now_utc.date().isoformat()
        for raw_id in arxiv_ids:
            if not raw_id:
                continue
            key = normalize_arxiv_id(raw_id, self.scope)
            ids[key] = stamp
        self.ids = ids

    def save(self) -> None:
        ids = self.load()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "scope": self.scope,
            "retention_days": self.retention_days,
            "ids": dict(sorted(ids.items(), key=lambda kv: kv[0])),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

