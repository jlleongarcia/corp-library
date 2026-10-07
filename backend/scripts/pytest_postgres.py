"""
Run the test suite against a throwaway local PostgreSQL (no Docker needed).

    uv run scripts/pytest_postgres.py [pytest args]

Uses the `pgserver` package (embedded PostgreSQL binaries) from the dev dependency group.
"""

import os
import subprocess
import sys
import tempfile

import pgserver

with tempfile.TemporaryDirectory(prefix="corplib-pg-") as data_dir:
    server = pgserver.get_server(data_dir, cleanup_mode="stop")
    uri = server.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)
    env = dict(os.environ, TEST_DATABASE_URL=uri)
    code = subprocess.call([sys.executable, "-m", "pytest", *sys.argv[1:]], env=env)
    server.cleanup()
sys.exit(code)
