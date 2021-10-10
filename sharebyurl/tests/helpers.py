import sys
from unittest import mock
from typing import List

from sharebyurl import main


def run_cli(args: List[str]) -> int:
    with mock.patch.object(sys, "argv", ["sharebyurl"] + args):
        return main.cli()
