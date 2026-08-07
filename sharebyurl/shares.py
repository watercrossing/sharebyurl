"""Creating, listing, removing and pruning shares on disk.

A share is a directory directly under ``public_html`` whose name is
unguessable, containing one symlink per shared file. Nothing in here writes
state; the caller owns the :class:`~sharebyurl.store.ShareStore`.
"""

from __future__ import annotations

import os
import re
import secrets
import string
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from slugify import slugify

from .store import Share, ShareStore

#: Kept from version 0.3: dots survive slugification so file extensions do.
ALLOWED_CHARS_PATTERN = re.compile(r"[^-a-z0-9\.]+")

#: 10 characters of [a-z0-9] is about 51.7 bits -- ample against online
#: guessing, and short enough to paste into a chat window.
TOKEN_LENGTH = 10
TOKEN_ALPHABET = string.ascii_lowercase + string.digits

#: A share name is always a single path component. Anything else would let
#: `-s ../elsewhere` write symlinks outside the web root.
SHARE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ShareError(Exception):
    """Any user-facing failure. The message is printed as-is."""


def generate_token() -> str:
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))


def validate_share_name(name: str) -> str:
    """Reject anything that is not a single, safe path component."""
    if not name:
        raise ShareError("Share name is empty.")
    if os.sep in name or (os.altsep and os.altsep in name) or "/" in name:
        raise ShareError(
            f"Share name {name!r} may not contain a path separator -- "
            f"a share is always a single directory under public_html."
        )
    if name in (".", "..") or not SHARE_NAME_PATTERN.match(name):
        raise ShareError(
            f"Share name {name!r} is not usable. Use letters, digits, dots, "
            f"dashes and underscores, starting with a letter or digit."
        )
    return name


def resolve_share_name(public_html: Path, requested: str | None) -> tuple[str, bool]:
    """Work out which share to write to.

    Returns the share name and whether it already existed. A ``requested`` name
    that matches an existing share is reused verbatim; anything else becomes a
    slug with a fresh token appended.
    """
    if not requested:
        return generate_token(), False

    if "/" in requested or os.sep in requested or Path(requested).is_absolute():
        raise ShareError(
            f"Share name {requested!r} may not contain a path separator -- "
            f"a share is always a single directory under public_html."
        )

    if SHARE_NAME_PATTERN.match(requested) and (public_html / requested).is_dir():
        return requested, True

    stem = slugify(requested)
    if not stem:
        raise ShareError(f"Share name {requested!r} slugifies to nothing usable.")
    return f"{stem}-{generate_token()}", False


def link_name_for(path: Path, use_slug: bool) -> str:
    """The name a shared file gets inside the share directory."""
    if use_slug:
        return slugify(path.name, regex_pattern=ALLOWED_CHARS_PATTERN)
    return path.name


@dataclass
class LinkResult:
    """What :func:`link_paths` did, so the caller can report it."""

    created: list[str]
    already_present: list[str]


def resolve_sources(paths: list[Path]) -> list[Path]:
    """Check every path exists, and resolve it.

    Called before the share directory is created so that a typo leaves no
    empty directory behind.
    """
    missing = [p for p in paths if not p.exists()]
    if missing:
        listing = ", ".join(str(p) for p in missing)
        raise ShareError(f"These paths do not exist, so nothing was shared: {listing}")
    return [p.resolve() for p in paths]


def link_paths(
    dest_dir: Path, paths: list[Path], use_slug: bool = False, force: bool = False
) -> LinkResult:
    """Symlink each of ``paths`` into ``dest_dir``.

    Every path is checked before anything is written, so a typo in the last
    argument does not leave a half-populated share.
    """
    resolved = resolve_sources(paths)

    names: dict[str, Path] = {}
    for source in resolved:
        name = link_name_for(source, use_slug)
        if name in names and names[name] != source:
            raise ShareError(
                f"Two different files would both be shared as {name!r}: {names[name]} and {source}."
            )
        names[name] = source

    created: list[str] = []
    already: list[str] = []
    for name, source in names.items():
        link = dest_dir / name
        if link.is_symlink() or link.exists():
            current = os.readlink(link) if link.is_symlink() else None
            if current == str(source):
                already.append(name)
                continue
            if not force:
                raise ShareError(
                    f"{name!r} is already in this share and points somewhere else "
                    f"({current or 'a real file'}). Re-run with --force to replace it."
                )
            link.unlink()
        link.symlink_to(source)
        created.append(name)

    return LinkResult(created=created, already_present=already)


def share_url(public_url: str, share: str, filename: str | None = None) -> str:
    """Build the URL for a share, or for one file inside it."""
    base = public_url.rstrip("/")
    parts = [base, share] if filename is None else [base, share, filename]
    return "/".join(parts)


@dataclass
class ShareRow:
    """One line of ``--list`` output."""

    name: str
    files: int
    expires: datetime | None
    tracked: bool


def list_shares(public_html: Path, store: ShareStore) -> list[ShareRow]:
    """Every share directory on disk, whether or not it is tracked."""
    rows = []
    for entry in sorted(public_html.iterdir()):
        if not entry.is_dir():
            continue
        record = store.get(entry.name)
        rows.append(
            ShareRow(
                name=entry.name,
                files=sum(1 for _ in entry.iterdir()),
                expires=record.expires if record else None,
                tracked=record is not None,
            )
        )
    return rows


def delete_share(public_html: Path, name: str) -> None:
    """Remove a share directory and the symlinks in it.

    Refuses anything that is not a direct child of ``public_html`` or that
    holds real files, on the grounds that this is the one operation here that
    destroys data.
    """
    validate_share_name(name)
    target = public_html / name

    if not target.is_dir():
        raise ShareError(f"No such share: {name}")
    if target.resolve().parent != public_html.resolve():
        raise ShareError(f"Refusing to delete {target}: it is not directly under {public_html}.")

    entries = list(target.iterdir())
    real_files = [e.name for e in entries if not e.is_symlink()]
    if real_files:
        raise ShareError(
            f"Refusing to delete share {name!r}: it contains real files, not just "
            f"symlinks ({', '.join(sorted(real_files))}). Remove it by hand."
        )

    for entry in entries:
        entry.unlink()
    target.rmdir()


def prune(
    public_html: Path, store: ShareStore, now: datetime, dry_run: bool = False
) -> tuple[list[str], list[tuple[str, str]]]:
    """Delete every tracked share whose expiry has passed.

    Untracked share directories are never touched -- an absent record means we
    do not know what the share was for, and deleting it would be a guess.
    Returns the names removed and a list of (name, reason) that were skipped.
    """
    removed: list[str] = []
    skipped: list[tuple[str, str]] = []

    for share in store.expired(now):
        target = public_html / share.name
        if not target.exists():
            # Directory already gone by hand; drop the stale record.
            if not dry_run:
                store.forget(share.name)
            skipped.append((share.name, "already gone, record dropped"))
            continue
        if dry_run:
            removed.append(share.name)
            continue
        try:
            delete_share(public_html, share.name)
        except ShareError as exc:
            skipped.append((share.name, str(exc)))
            continue
        store.forget(share.name)
        removed.append(share.name)

    return removed, skipped


def find_orphans(public_html: Path, store: ShareStore) -> list[Share]:
    """Tracked shares whose directory no longer exists."""
    return [s for s in store.shares.values() if not (public_html / s.name).is_dir()]
