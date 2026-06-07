"""Placeholder integration tests — replaced by real tests as features are implemented."""

import pytest


@pytest.mark.integration
def test_agent_main_importable() -> None:
    import agent.main  # noqa: F401
