from dataclasses import dataclass
from pathlib import Path

import pytest

from sharebyurl import shares


@dataclass
class Sandbox:
    """An isolated config dir, state dir, web root and source dir."""

    root: Path
    www: Path
    src: Path
    config: Path
    state: Path

    def file(self, name: str, content: str = "hello") -> Path:
        path = self.src / name
        path.write_text(content)
        return path

    @property
    def config_file(self) -> Path:
        return self.config / "sharebyurl.ini"

    @property
    def state_file(self) -> Path:
        return self.state / "sharebyurl" / "shares.json"

    def share_dirs(self) -> list[str]:
        return sorted(p.name for p in self.www.iterdir() if p.is_dir())

    def only_share(self) -> Path:
        dirs = [p for p in self.www.iterdir() if p.is_dir()]
        assert len(dirs) == 1, f"expected exactly one share, found {dirs}"
        return dirs[0]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point HOME and the XDG dirs at a throwaway tree.

    Everything reads these at call time rather than import time, so a test can
    run the real cli() without touching the developer's own config.
    """
    box = Sandbox(
        root=tmp_path,
        www=tmp_path / "www",
        src=tmp_path / "src",
        config=tmp_path / "config",
        state=tmp_path / "state",
    )
    for directory in (box.www, box.src, box.config, box.state):
        directory.mkdir()

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(box.config))
    monkeypatch.setenv("XDG_STATE_HOME", str(box.state))
    monkeypatch.delenv("SHAREBYURL_CONFIG", raising=False)
    # pytest's tmp_path sits under a mode-700 directory, so every source would
    # look unreachable to the webserver and be copied. Tests of the copying
    # path set this back to something else themselves.
    monkeypatch.setattr(shares, "readable_by_others", lambda path: True)
    return box


@pytest.fixture
def configured(sandbox):
    """A sandbox with public_html and public_url already saved."""
    sandbox.config_file.write_text(
        f"[config]\npublic_html = {sandbox.www}\npublic_url = https://example.com/s/\n"
    )
    return sandbox
