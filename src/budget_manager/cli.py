"""Command line: ``budget-manager serve`` runs the app, ``budget-manager check-update`` tells
whether a newer version is out, ``budget-manager manage ...`` runs any Django management
command."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
import urllib.request

from budget_manager import __version__


def _django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "budget_manager.web.settings")
    import django

    django.setup()


def serve(host: str, port: int, threads: int) -> None:
    _django()
    from django.conf import settings
    from django.core.management import call_command
    from waitress import serve as waitress_serve

    from budget_manager.web.wsgi import application

    call_command("migrate", interactive=False, verbosity=0)
    print(f"Budget Manager {__version__} is running on http://{host}:{port}/")
    print(f"Data is stored in {settings.DATA_DIR}")
    print(f"Accepting connections from: {', '.join(settings.ALLOWED_NETWORKS)}")
    waitress_serve(application, host=host, port=port, threads=threads)


#: Where the newest released version is published: the prod branch on GitHub.
UPDATE_SOURCE = "https://raw.githubusercontent.com/simonrydder/budget-manager/prod/"

#: Exit codes of ``check-update``, for scripts (BudgetManager.cmd).
UP_TO_DATE, UPDATE, MAJOR_UPDATE = 0, 3, 4


def _parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def _fetch(name: str) -> str:
    source = os.environ.get("BUDGET_UPDATE_SOURCE", UPDATE_SOURCE)
    with urllib.request.urlopen(source + name, timeout=15) as response:  # noqa: S310
        return response.read().decode("utf-8")


def changes_since(changelog: str, installed: tuple[int, ...]) -> str:
    """The parts of CHANGELOG.md for versions newer than ``installed``."""
    sections = re.split(r"(?m)^(?=## )", changelog)
    newer = [s.strip() for s in sections if s.startswith("## ") and _parse_version(s) > installed]
    return "\n\n".join(newer)


def check_update() -> int:
    """Compare the installed version with the newest one. A new first number (2.0.0 after
    1.x) means a change that may need something done by hand, so scripts ask before updating."""
    installed = _parse_version(__version__)
    try:
        newest_text = tomllib.loads(_fetch("pyproject.toml"))["project"]["version"]
    except Exception as error:  # offline, GitHub unavailable, ...
        print(f"Could not check for a new version ({error}).")
        return 1
    newest = _parse_version(newest_text)
    if newest <= installed:
        print(f"Budget Manager {__version__} is the newest version.")
        return UP_TO_DATE
    print(f"Budget Manager {newest_text} is available (you have {__version__}).")
    if newest[0] == installed[0]:
        return UPDATE
    try:
        changes = changes_since(_fetch("CHANGELOG.md"), installed)
    except Exception:
        changes = ""
    print("It is a major update: it changes how something works and may need you to do something.")
    if changes:
        print("\nWhat is new:\n\n" + changes + "\n")
    return MAJOR_UPDATE


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="budget-manager", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("serve", help="Run the web app on the local network.")
    run.add_argument("--host", default=os.environ.get("BUDGET_HOST", "0.0.0.0"))
    run.add_argument("--port", type=int, default=int(os.environ.get("BUDGET_PORT", "8000")))
    run.add_argument("--threads", type=int, default=4)
    commands.add_parser("manage", help="Run a Django management command.", add_help=False)
    commands.add_parser(
        "check-update",
        help=f"Check for a newer version. Exit code {UP_TO_DATE}: up to date, {UPDATE}: an "
        f"update, {MAJOR_UPDATE}: a major update, 1: could not check.",
    )

    if argv and argv[0] == "manage":
        _django()
        from django.core.management import execute_from_command_line

        execute_from_command_line(["budget-manager manage", *argv[1:]])
        return
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(args.host, args.port, args.threads)
    elif args.command == "check-update":
        sys.exit(check_update())
