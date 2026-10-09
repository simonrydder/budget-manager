"""BudgetManager.cmd, the one file a friend downloads to run the app on their own computer."""

from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "BudgetManager.cmd"


def test_it_is_a_windows_batch_file_with_crlf_line_endings():
    # GitHub's "Download raw file" gives the bytes as stored, and cmd.exe misreads some lines
    # of a batch file with bare LF line endings, so the file is stored with CRLF.
    data = SCRIPT.read_bytes()
    assert data.count(b"\r\n") == data.count(b"\n")


def test_it_installs_the_newest_prod_and_only_accepts_this_computer():
    text = SCRIPT.read_text()
    assert "https://github.com/simonrydder/budget-manager/archive/refs/heads/prod.zip" in text
    assert 'set "BUDGET_ALLOWED_NETWORKS=127.0.0.0/8,::1/128"' in text
    assert "budget-manager serve --host 127.0.0.1" in text
    assert "%USERPROFILE%\\BudgetManager" in text


def test_it_needs_no_login_and_asks_before_a_major_update():
    text = SCRIPT.read_text()
    assert 'set "BUDGET_LOCAL_ONLY=1"' in text
    assert "budget-manager check-update" in text
    assert "if errorlevel 4 goto ask" in text
    assert 'choice /C YN /M "Install this major update now"' in text
