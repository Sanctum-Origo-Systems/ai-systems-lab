import re
from importlib.metadata import version

import labkit


def test_labkit_exposes_installed_version():
    assert labkit.__version__ == version("labkit")


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", labkit.__version__)
