"""The share database: what was created, when, and when it expires.

Kept separate from the config file so that settings stay hand-editable and
machine state stays disposable -- deleting this file loses expiry tracking but
breaks no live URL.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1


def default_store_path() -> Path:
    """The state file location, honouring ``XDG_STATE_HOME``."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "sharebyurl" / "shares.json"


@dataclass
class Share:
    """One tracked share. ``expires`` of ``None`` means it never expires.

    ``copies`` names the entries that are copies rather than symlinks, which is
    what lets prune delete them: a real file nobody recorded is left alone.
    """

    name: str
    created: datetime
    expires: datetime | None = None
    copies: list[str] = field(default_factory=list)

    def is_expired(self, now: datetime) -> bool:
        return self.expires is not None and self.expires <= now

    def to_json(self) -> dict[str, str | list[str] | None]:
        data: dict[str, str | list[str] | None] = {
            "created": self.created.isoformat(),
            "expires": self.expires.isoformat() if self.expires else None,
        }
        if self.copies:
            data["copies"] = sorted(self.copies)
        return data

    @classmethod
    def from_json(cls, name: str, data: dict) -> Share:
        return cls(
            name=name,
            created=_parse_time(data.get("created")) or _now(),
            expires=_parse_time(data.get("expires")),
            copies=list(data.get("copies") or []),
        )


class ShareStore:
    """A JSON-backed mapping of share name to :class:`Share`."""

    def __init__(self, path: Path, shares: dict[str, Share] | None = None):
        self.path = path
        self.shares: dict[str, Share] = shares or {}

    @classmethod
    def load(cls, path: Path | None = None) -> ShareStore:
        """Read the store. A missing or unreadable file yields an empty store.

        A corrupt file must not stop someone sharing a photo, so it is moved
        aside rather than raised -- the cost is losing expiry tracking for
        existing shares, which prune handles conservatively anyway.
        """
        path = path or default_store_path()
        if not path.exists():
            return cls(path)

        try:
            data = json.loads(path.read_text())
            raw = data["shares"]
        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            path.replace(path.with_suffix(".json.corrupt"))
            return cls(path)

        shares = {name: Share.from_json(name, entry) for name, entry in raw.items()}
        return cls(path, shares)

    def save(self) -> None:
        """Write the store out atomically."""
        payload = {
            "version": VERSION,
            "shares": {name: share.to_json() for name, share in sorted(self.shares.items())},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.replace(self.path)

    def get(self, name: str) -> Share | None:
        return self.shares.get(name)

    def record(self, name: str, expires: datetime | None, now: datetime | None = None) -> Share:
        """Create or update a share's record, preserving its original creation time."""
        now = now or _now()
        existing = self.shares.get(name)
        share = Share(
            name=name,
            created=existing.created if existing else now,
            expires=expires,
            copies=existing.copies if existing else [],
        )
        self.shares[name] = share
        return share

    def note_entries(self, name: str, copied: list[str], linked: list[str]) -> None:
        """Track which entries of a recorded share are copies.

        ``linked`` matters too: --force can replace a copy with a symlink.
        """
        share = self.shares[name]
        share.copies = sorted((set(share.copies) - set(linked)) | set(copied))

    def forget(self, name: str) -> None:
        self.shares.pop(name, None)

    def expired(self, now: datetime | None = None) -> list[Share]:
        now = now or _now()
        return sorted(
            (s for s in self.shares.values() if s.is_expired(now)),
            key=lambda s: s.name,
        )

    def migrate_from_config(
        self, legacy: dict[str, str] | None, now: datetime | None = None
    ) -> int:
        """Absorb ``[<share>]`` sections from a version 0.3 config file.

        Those sections only ever recorded ``expiry = -1`` because expiry was
        never implemented, so everything imported is treated as never expiring.
        Returns the number of shares imported.
        """
        if not legacy:
            return 0
        now = now or _now()
        imported = 0
        for name in legacy:
            if name not in self.shares:
                self.shares[name] = Share(name=name, created=now, expires=None)
                imported += 1
        return imported


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # Anything written by an older build without a timezone is read as UTC.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
