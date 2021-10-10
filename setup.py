#!/usr/bin/env python3

import sys

from setuptools import setup

if sys.version_info < (3, 6, 0):
    sys.exit(
        "Python 3.6 or later is required. "
        "See https://github.com/watercrossing/sharebyurl "
        "for installation instructions."
    )

setup()