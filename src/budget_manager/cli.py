"""Command line: ``budget-manager serve`` runs the app, ``budget-manager manage ...`` runs any
Django management command."""

from __future__ import annotations

import argparse
import os
import sys


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
    print(f"Budget Manager is running on http://{host}:{port}/")
    print(f"Data is stored in {settings.DATA_DIR}")
    print(f"Accepting connections from: {', '.join(settings.ALLOWED_NETWORKS)}")
    waitress_serve(application, host=host, port=port, threads=threads)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="budget-manager", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("serve", help="Run the web app on the local network.")
    run.add_argument("--host", default=os.environ.get("BUDGET_HOST", "0.0.0.0"))
    run.add_argument("--port", type=int, default=int(os.environ.get("BUDGET_PORT", "8000")))
    run.add_argument("--threads", type=int, default=4)
    commands.add_parser("manage", help="Run a Django management command.", add_help=False)

    if argv and argv[0] == "manage":
        _django()
        from django.core.management import execute_from_command_line

        execute_from_command_line(["budget-manager manage", *argv[1:]])
        return
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(args.host, args.port, args.threads)
