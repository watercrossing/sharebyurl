
import sys

from unittest import mock
from helpers import run_cli

import pytest


def test_help_text(monkeypatch, capsys):
    mock_exit = mock.Mock(side_effect=ValueError("raised in test to exit early"))
    with mock.patch.object(sys, "exit", mock_exit), pytest.raises(
        ValueError, match="raised in test to exit early"
    ):
        assert not run_cli(["--help"])
    captured = capsys.readouterr()
    assert "usage: sharebyurl" in captured.out

    