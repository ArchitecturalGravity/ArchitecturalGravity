"""Run the developer-only provider-free lifecycle diagnostic."""

from .dry_run import main


if __name__ == "__main__":
    raise SystemExit(main())
