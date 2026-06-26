"""Module entrypoint for `python -m ecfinder.pipeline`."""

from ecfinder.pipeline.orchestrator import main


if __name__ == "__main__":
    raise SystemExit(main())
