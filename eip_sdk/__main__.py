"""Allow running the EIP CLI with `python -m eip_sdk`."""

from eip_sdk.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
