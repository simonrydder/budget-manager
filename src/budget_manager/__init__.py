"""A self-hosted budget manager for the home network."""


def main() -> None:
    from budget_manager.cli import main as cli_main

    cli_main()
