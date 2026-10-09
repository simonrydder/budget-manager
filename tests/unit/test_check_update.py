"""``budget-manager check-update``: the one-file start asks before a major update."""

import pytest

from budget_manager import cli

CHANGELOG = """# Changelog

## 2.0.0 (2027-01-01)

- Budgets are now kept per year.

## 1.9.0 (2026-12-01)

- Something new.

## 1.2.0 (2026-10-09)

- Already installed.
"""


@pytest.fixture
def github(monkeypatch):
    files = {}

    def fetch(name):
        if name not in files:
            raise OSError("offline")
        return files[name]

    monkeypatch.setattr(cli, "_fetch", fetch)
    monkeypatch.setattr(cli, "__version__", "1.2.0")
    return files


def published(github, version):
    github["pyproject.toml"] = f'[project]\nname = "budget-manager"\nversion = "{version}"\n'
    github["CHANGELOG.md"] = CHANGELOG


def test_up_to_date(github, capsys):
    published(github, "1.2.0")
    assert cli.check_update() == cli.UP_TO_DATE
    assert "1.2.0 is the newest version" in capsys.readouterr().out


def test_an_ordinary_update_installs_without_asking(github):
    published(github, "1.9.0")
    assert cli.check_update() == cli.UPDATE


def test_a_major_update_asks_and_shows_what_is_new(github, capsys):
    published(github, "2.0.0")
    assert cli.check_update() == cli.MAJOR_UPDATE
    out = capsys.readouterr().out
    assert "2.0.0 is available (you have 1.2.0)" in out
    assert "Budgets are now kept per year." in out and "Something new." in out
    assert "Already installed." not in out


def test_offline(github):
    assert cli.check_update() == 1


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.startswith("budget-manager ")
