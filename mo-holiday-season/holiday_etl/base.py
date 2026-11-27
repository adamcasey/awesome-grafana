"""Shared plumbing: every source is fetch -> normalize -> validate -> write."""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CURATED_DIR = ROOT / "curated"
USER_AGENT = "awesome-grafana-mo-holiday-season/0.1 (+https://github.com/)"

log = logging.getLogger("holiday_etl")


class SourceUnavailable(Exception):
    """Upstream is down (5xx/timeouts after retries). The previous data file is kept and the run
    reports it, but the job does not fail: there is nothing in this repo to fix."""


class ValidationError(Exception):
    """Raised when a source fails a plausibility or golden-number check. Never swallowed."""


def http_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    retry = Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"{name} is not set (add it with `dotenvx set {name} <value>` at the repo root)")
    if val.startswith("encrypted:"):
        # dotenvx passes ciphertext through unchanged when it has no private key.
        raise RuntimeError(f"{name} is still encrypted: DOTENV_PRIVATE_KEY is missing or wrong")
    return val


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise ValidationError(msg)


class Source(ABC):
    name: str
    output: str  # file name under data/
    needs_env: tuple[str, ...] = ()

    @abstractmethod
    def fetch(self, session: requests.Session) -> Any: ...

    @abstractmethod
    def normalize(self, raw: Any) -> pd.DataFrame: ...

    @abstractmethod
    def validate(self, df: pd.DataFrame) -> None: ...

    def inspect(self, raw: Any) -> str:
        """Human-readable dump of the raw layout, for unverified files."""
        return repr(raw)[:5000]

    def write(self, df: pd.DataFrame) -> Path:
        DATA_DIR.mkdir(exist_ok=True)
        path = DATA_DIR / self.output
        df.to_csv(path, index=False)
        return path

    def run(self, session: requests.Session) -> Path:
        raw = self.fetch(session)
        df = self.normalize(raw)
        self.validate(df)
        path = self.write(df)
        log.info("%s: wrote %d rows -> %s", self.name, len(df), path.name)
        return path
