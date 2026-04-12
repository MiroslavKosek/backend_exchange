"""Pytest configuration ensuring project root is importable in tests."""

import sys
from pathlib import Path
from typing import Any, Generator

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Pylint in some environments does not resolve test-time sys.path changes.
# pylint: disable=import-error,wrong-import-position
from app.services.auth_service import AuthService


@pytest.fixture(autouse=True)
def reset_revoked_tokens() -> Generator[Any, Any, Any]:
    """Reset revoked token set before each test to ensure test isolation."""
    AuthService.clear_revoked_tokens()
    yield
    # Clean up after test
    AuthService.clear_revoked_tokens()
