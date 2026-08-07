"""User configuration: where shares are written, and the URL they appear at.

This file holds *settings only*. Version 0.3 also wrote one section per share
into the same file, mixing user config with machine state; that state now lives
in :mod:`sharebyurl.store`, and :func:`load` migrates any leftovers out.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

SECTION = "config"


def default_config_path() -> Path:
    """The config file location.

    ``SHAREBYURL_CONFIG`` overrides everything, then ``XDG_CONFIG_HOME``.
    """
    override = os.environ.get("SHAREBYURL_CONFIG")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "sharebyurl.ini"


@dataclass
class Config:
    """Resolved settings, plus the path they were read from."""

    path: Path
    public_html: Path | None = None
    public_url: str = ""
    default_expiry: str | None = None

    #: Share sections found in an old-format config file, as {name: expiry}.
    #: :func:`sharebyurl.store.ShareStore.migrate_from_config` consumes these.
    legacy_shares: dict[str, str] | None = None

    def save(self) -> None:
        """Write the settings back, atomically, creating parents as needed."""
        parser = configparser.ConfigParser()
        parser.add_section(SECTION)
        if self.public_html is not None:
            parser.set(SECTION, "public_html", str(self.public_html))
        if self.public_url:
            parser.set(SECTION, "public_url", self.public_url)
        if self.default_expiry:
            parser.set(SECTION, "default_expiry", self.default_expiry)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w") as handle:
            parser.write(handle)
        tmp.replace(self.path)


def load(path: Path | None = None) -> Config:
    """Read the config file. A missing file yields an empty Config, not an error."""
    path = path or default_config_path()
    config = Config(path=path)

    if not path.exists():
        return config

    parser = configparser.ConfigParser()
    parser.read(path)

    public_html = parser.get(SECTION, "public_html", fallback="")
    config.public_html = Path(public_html).expanduser() if public_html else None
    config.public_url = parser.get(SECTION, "public_url", fallback="")
    config.default_expiry = parser.get(SECTION, "default_expiry", fallback="") or None

    legacy = {
        name: parser.get(name, "expiry", fallback="-1")
        for name in parser.sections()
        if name != SECTION
    }
    config.legacy_shares = legacy or None

    return config
