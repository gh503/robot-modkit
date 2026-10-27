import pathlib
import re

import pytest

from modkit import __version__, cli


def test_console_script_and_version_are_declared():
    root = pathlib.Path(__file__).resolve().parents[1]
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^modkit = "modkit\.cli:main"$', text, re.M)
    assert __version__ in text


def test_cli_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out
