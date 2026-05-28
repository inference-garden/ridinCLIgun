# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for secret mode

"""Tests for secret mode guards — ensures no data leaks to AI when active.

Audit T01: these tests exercise the REAL app methods (`_trigger_ai_review`,
`_do_ai_review`, `action_toggle_secret`) via Textual headless mode and a mock
provider. They are written so that silently removing a guard in `app.py` makes
a test fail — the previous versions re-implemented ("mirrored") the guard logic
locally and would have stayed green through a real regression.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import ridincligun.app as appmod
from ridincligun.app import RidinCLIgunApp
from ridincligun.config import Config, ProviderSettings
from ridincligun.state import Phase


def _test_config(tmp_path) -> Config:
    config_dir = tmp_path / "ridincligun"
    config_dir.mkdir()
    (config_dir / ".env").write_text("# empty\n")
    (config_dir / "config.toml").write_text("[general]\nai_enabled_default = false\n")
    return Config(
        config_dir=config_dir,
        ai_enabled_default=False,
        api_key="",
        provider=ProviderSettings(),
        language="en",
    )


@pytest.fixture
def app_config(tmp_path):
    return _test_config(tmp_path)


def _mock_provider() -> MagicMock:
    """A configured provider whose review() is awaitable and counted."""
    provider = MagicMock()
    provider.is_configured = True
    provider.provider_name = "mock"
    provider.review = AsyncMock(return_value=MagicMock(success=False, error_message=""))
    return provider


# ── Secret mode blocks review dispatch (real app path) ────────────


@pytest.mark.asyncio
async def test_secret_mode_blocks_real_review_dispatch(app_config, monkeypatch):
    """With secret mode ON, F2/_trigger_ai_review must never reach the provider.

    A real command is forced via extract_current_command so that the ONLY thing
    preventing dispatch is the secret-mode guard — if that guard is removed, the
    provider would be called and this test fails.
    """
    monkeypatch.setattr(appmod, "extract_current_command", lambda screen: "echo hi")
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        app._provider = _mock_provider()
        app.state.ai_enabled = True
        app.state.secret_mode = True

        app._trigger_ai_review()
        await pilot.pause()

        app._provider.review.assert_not_called()


@pytest.mark.asyncio
async def test_review_dispatched_when_secret_mode_off(app_config, monkeypatch):
    """Control: with secret mode OFF the real dispatch path DOES call the provider.

    Without this, the block-test above could pass simply because the path is
    unreachable. This proves the path is live.
    """
    monkeypatch.setattr(appmod, "extract_current_command", lambda screen: "echo hi")
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        app._provider = _mock_provider()
        app.state.ai_enabled = True
        app.state.secret_mode = False

        app._trigger_ai_review()
        await pilot.pause()

        app._provider.review.assert_awaited()


# ── In-flight review is cancelled when secret mode is toggled on ──


@pytest.mark.asyncio
async def test_secret_toggle_cancels_inflight_review(app_config, monkeypatch):
    """Toggling secret mode ON cancels the in-flight review task and bumps generation."""
    monkeypatch.setattr(appmod, "extract_current_command", lambda screen: "echo hi")
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_review(*args, **kwargs):
            started.set()
            await release.wait()
            return MagicMock(success=False, error_message="")

        provider = _mock_provider()
        provider.review = slow_review
        app._provider = provider
        app.state.ai_enabled = True
        app.state.secret_mode = False

        app._trigger_ai_review()
        await asyncio.wait_for(started.wait(), timeout=2)
        assert app._review_task is not None and not app._review_task.done()
        gen_in_flight = app._review_generation

        # F5 — toggle secret mode ON
        app.action_toggle_secret()

        assert app.state.secret_mode
        assert app._review_generation == gen_in_flight + 1
        assert app._review_task is None, "in-flight review task was not cancelled/cleared"

        release.set()
        await pilot.pause()


# ── Stale / suppressed results are discarded in _do_ai_review ─────


@pytest.mark.asyncio
async def test_do_ai_review_discards_stale_generation(app_config):
    """_do_ai_review must not render a result whose generation no longer matches."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        app._provider = _mock_provider()
        app._review_generation = 5

        # Launched at generation 4, but a newer review (or toggle) advanced to 5.
        await app._do_ai_review("echo hi", generation=4, system_prompt="")
        await pilot.pause()

        app._provider.review.assert_awaited()  # the call happened
        assert app.state.phase == Phase.TYPING  # but the result was discarded
        assert not app._ai_review_showing


@pytest.mark.asyncio
async def test_do_ai_review_discards_when_secret_mode_on(app_config):
    """Even at the matching generation, a result is discarded if secret mode is on."""
    app = RidinCLIgunApp(config=app_config)
    async with app.run_test(size=(120, 40)) as pilot:
        app._provider = _mock_provider()
        app._review_generation = 5
        app.state.secret_mode = True

        await app._do_ai_review("echo hi", generation=5, system_prompt="")
        await pilot.pause()

        assert app.state.phase == Phase.TYPING
        assert not app._ai_review_showing


# ── Secret mode does not affect local advisory ────────────────────


def test_secret_mode_does_not_block_local_advisory():
    """Secret mode only blocks AI (network) calls.
    The local advisory engine should still work."""
    from ridincligun.advisory.engine import AdvisoryEngine
    from ridincligun.state import AppState

    state = AppState()
    state.secret_mode = True

    # The local engine has no secret_mode check — it's purely offline.
    engine = AdvisoryEngine()
    result = engine.analyze("rm -rf /")
    assert result is not None
    assert len(result.warnings) > 0
