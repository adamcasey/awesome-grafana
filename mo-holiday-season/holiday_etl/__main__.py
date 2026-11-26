"""python -m holiday_etl run [--only a,b] [--allow-missing-keys]
   python -m holiday_etl inspect <source>
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from .base import SourceUnavailable, http_session
from .sources import REGISTRY


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="holiday_etl")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--only", default="", help="comma-separated source names")
    run.add_argument("--allow-missing-keys", action="store_true",
                     help="skip (not fail) sources whose API key secret is absent")
    ins = sub.add_parser("inspect")
    ins.add_argument("source", choices=sorted(REGISTRY))
    args = p.parse_args(argv)

    session = http_session()
    if args.cmd == "inspect":
        src = REGISTRY[args.source]()
        print(src.inspect(src.fetch(session)))
        return 0

    names = [n for n in args.only.split(",") if n] or list(REGISTRY)
    failed = []
    for name in names:
        src = REGISTRY[name]()
        missing = [e for e in src.needs_env if not os.environ.get(e)]
        if missing and args.allow_missing_keys:
            logging.warning("%s: skipped, missing %s", name, ",".join(missing))
            continue
        try:
            src.run(session)
        except SourceUnavailable as exc:
            logging.warning("%s UNAVAILABLE (previous data kept): %s", name, exc)
        except Exception as exc:  # report every source, then fail the job
            logging.error("%s FAILED: %s", name, exc)
            failed.append(name)
    if failed:
        logging.error("failed sources: %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
