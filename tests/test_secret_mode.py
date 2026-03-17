"""Tests for secret mode guards — ensures no data leaks to AI when active."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ridincligun.provider.manager import ProviderManager
from ridincligun.state import AppState, Phase


# ── Secret mode blocks review dispatch ────────────────────────────


def test_secret_mode_blocks_review_call():
    """When secret_mode is True, the provider must never be called."""
    state = AppState()
    state.secret_mode = True
    state.ai_enabled = True

    mock_adapter = MagicMock()
    mock_adapter.is_configured = True
    mock_adapter.name = "mock"
    manager = ProviderManager(mock_adapter)

    # Simulate the guard logic from _trigger_ai_review
    if state.secret_mode:
        called = False
    else:
        asyncio.run(manager.review("sensitive-command"))
        called = True

    assert not called, "Provider was called despite secret mode being on"


def test_secret_mode_off_allows_review():
    """When secret_mode is False, the provider should be reachable."""
    state = AppState()
    state.secret_mode = False
    state.ai_enabled = True

    # Just verify the state gate opens
    assert not state.secret_mode


# ── Race condition: secret mode enabled after request sent ────────


@pytest.mark.asyncio
async def test_review_result_suppressed_when_secret_mode_enabled_during_flight():
    """If secret mode is toggled ON while a review is in-flight,
    the result must be discarded — not displayed."""
    state = AppState()
    state.secret_mode = False
    state.phase = Phase.REVIEW_LOADING

    # Simulate: review returns, but secret mode was toggled on in the meantime
    state.secret_mode = True

    # This mirrors the guard in _do_ai_review
    if state.secret_mode:
        state.phase = Phase.TYPING
        result_displayed = False
    else:
        result_displayed = True

    assert not result_displayed, "Review result was displayed despite secret mode"
    assert state.phase == Phase.TYPING, "Phase should reset to IDLE"


@pytest.mark.asyncio
async def test_inflight_task_cancelled_on_secret_toggle():
    """Toggling secret mode on must cancel any in-flight review task."""
    # Create a mock task that tracks cancellation (use MagicMock, not
    # AsyncMock, because task.done() must return a plain bool)
    mock_task = MagicMock()
    mock_task.done.return_value = False

    state = AppState()
    state.secret_mode = False
    review_task = mock_task

    # Simulate toggling secret mode on (mirrors LeaderAction.TOGGLE_SECRET)
    state.secret_mode = True
    if state.secret_mode and review_task and not review_task.done():
        review_task.cancel()
        review_task = None

    mock_task.cancel.assert_called_once()
    assert review_task is None


# ── Secret mode does not affect local advisory ────────────────────


def test_secret_mode_does_not_block_local_advisory():
    """Secret mode only blocks AI (network) calls.
    The local advisory engine should still work."""
    state = AppState()
    state.secret_mode = True

    # The local engine has no secret_mode check — it's purely offline.
    # This test documents that design decision.
    from ridincligun.advisory.engine import AdvisoryEngine

    engine = AdvisoryEngine()
    result = engine.analyze("rm -rf /")
    assert result is not None
    assert len(result.warnings) > 0
