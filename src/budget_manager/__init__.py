"""A self-hosted budget manager for the home network."""

from importlib.metadata import PackageNotFoundError, version

try:
    # The version in pyproject.toml, as installed by uv.
    __version__ = version("budget-manager")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "unknown"


def main() -> None:
    from budget_manager.cli import main as cli_main

    cli_main()
