"""
Tests for Milestone 1's fail-fast configuration behavior.

Runs `import app.main` in a fresh subprocess, in a temporary empty working
directory. This is deliberate: pydantic-settings looks for a `.env` file
relative to the current working directory, not just at real environment
variables. If we ran the subprocess from the project root, it would find
the real local .env file (which has valid DATABASE_URL/JWT_SECRET for
local development) and "succeed" even after we remove those keys from the
subprocess's environment — testing nothing. Running from an empty temp
directory guarantees no .env is picked up, so these tests actually
exercise the "no config present" path regardless of what's in the
developer's local .env.

The subprocess environment is still built by copying the full parent
environment (not a stripped-down one) — see the comment below on Windows'
asyncio/_overlapped requirement.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_import_in_subprocess(overrides: dict[str, str], remove: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for key in remove:
        env.pop(key, None)
    env.update(overrides)

    # `import app.main` needs the project root on PYTHONPATH even though
    # we're running from a different (empty) cwd.
    env["PYTHONPATH"] = str(_PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    with tempfile.TemporaryDirectory() as tmp_cwd:
        return subprocess.run(
            [sys.executable, "-c", "import app.main"],
            cwd=tmp_cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )


def test_app_fails_to_start_without_database_url():
    result = _run_import_in_subprocess(
        overrides={"JWT_SECRET": "test-secret-do-not-use-in-production"},
        remove=["DATABASE_URL", "JWT_SECRET"],
    )

    assert result.returncode != 0, result.stdout
    assert "database_url" in result.stderr.lower()


def test_app_fails_to_start_without_jwt_secret():
    result = _run_import_in_subprocess(
        overrides={
            "DATABASE_URL": "postgresql+asyncpg://fsp:dev_password_change_me@localhost:5433/field_service"
        },
        remove=["DATABASE_URL", "JWT_SECRET"],
    )

    assert result.returncode != 0, result.stdout
    assert "jwt_secret" in result.stderr.lower()


def test_app_starts_with_both_required_vars_present():
    result = _run_import_in_subprocess(
        overrides={
            "DATABASE_URL": "postgresql+asyncpg://fsp:dev_password_change_me@localhost:5433/field_service",
            "JWT_SECRET": "test-secret-do-not-use-in-production",
        },
        remove=["DATABASE_URL", "JWT_SECRET"],
    )

    assert result.returncode == 0, result.stderr