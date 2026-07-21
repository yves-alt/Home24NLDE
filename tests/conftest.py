"""Pytest configuration — isolates the test suite from the shared dev database.

Tests must not depend on whatever glossary/TM state happens to be sitting in
database/localization.db (e.g. the ~14k-row official glossary imported for
manual QA on a developer's machine) — that makes results depend on
developer-machine state instead of the code. DB_PATH is overridden here, at
module import time, before any test module's own imports run (pytest always
imports conftest.py in a directory before collecting its test modules), so
every DB-backed module picks up the isolated test database via
`database.database.DB_PATH`, which is read from the environment at import time.
"""

import os
from pathlib import Path

_TEST_DB = str(Path(__file__).parent / "_test_localization.db")
os.environ["DB_PATH"] = _TEST_DB

for _suffix in ("", "-wal", "-shm"):
    _p = _TEST_DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)

from database.migrations import run_migrations  # noqa: E402

run_migrations()

from importers.seed_glossary import seed_glossary  # noqa: E402

seed_glossary()
