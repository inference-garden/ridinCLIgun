# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 inference-garden
# ridinCLIgun — Tests for the advisory pane scroll indicator (S4-1)

"""The advisory pane can overflow (long tldr pages, multi-warning output).  A
1-cell scroll indicator in the rightmost column shows there is more content and
where the viewport sits.  The reserved column must never clobber content.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from ridincligun.i18n import set_locale
from ridincligun.ui.advisory_pane import _SB_THUMB, _SB_TRACK, AdvisoryPane


class _PaneApp(App):
    def compose(self) -> ComposeResult:
        yield AdvisoryPane(id="advisory-pane")


def _many(n: int) -> list[tuple[str, str]]:
    return [(f"line {i}", "") for i in range(n)]


@pytest.mark.asyncio
async def test_no_indicator_when_content_fits():
    set_locale("en")
    async with _PaneApp().run_test(size=(40, 20)) as pilot:
        pane = pilot.app.query_one(AdvisoryPane)
        pane.set_content([("alpha", ""), ("beta", "")])
        await pilot.pause()
        assert pane._scrollbar_char(0) is None
        strip = pane.render_line(0)
        assert _SB_THUMB not in strip.text and _SB_TRACK not in strip.text


@pytest.mark.asyncio
async def test_indicator_shown_when_content_overflows():
    set_locale("en")
    async with _PaneApp().run_test(size=(40, 20)) as pilot:
        pane = pilot.app.query_one(AdvisoryPane)
        pane.set_content(_many(100))
        await pilot.pause()
        assert len(pane._wrapped_lines) > pane.size.height
        assert pane._scrollbar_char(0) is not None
        # The rightmost cell of every visible row carries the indicator glyph.
        last = pane.render_line(0).text[-1]
        assert last in (_SB_THUMB, _SB_TRACK)


@pytest.mark.asyncio
async def test_thumb_tracks_scroll_offset():
    set_locale("en")
    async with _PaneApp().run_test(size=(40, 20)) as pilot:
        pane = pilot.app.query_one(AdvisoryPane)
        pane.set_content(_many(100))
        await pilot.pause()
        height = pane.size.height

        # Scrolled to the top → thumb sits at the top row.
        pane._scroll_offset = 0
        assert pane._scrollbar_char(0) == _SB_THUMB

        # Scrolled to the bottom → thumb sits at the bottom row.
        pane._scroll_offset = len(pane._wrapped_lines) - height
        assert pane._scrollbar_char(height - 1) == _SB_THUMB
        assert pane._scrollbar_char(0) == _SB_TRACK


@pytest.mark.asyncio
async def test_indicator_does_not_clobber_content():
    """Content is wrapped to width-1, so the indicator never overwrites text."""
    set_locale("en")
    async with _PaneApp().run_test(size=(40, 20)) as pilot:
        pane = pilot.app.query_one(AdvisoryPane)
        # A line long enough that, without reservation, it would fill the width.
        long_line = "x" * 200
        pane.set_content([(long_line, "")] + _many(100))
        await pilot.pause()
        for _text, _style in pane._wrapped_lines:
            assert len(_text) <= pane.size.width - 1
        strip = pane.render_line(0)
        # Full-width strip: content in [0, width-1), glyph in the last cell.
        assert len(strip.text) == pane.size.width
        assert strip.text[-1] in (_SB_THUMB, _SB_TRACK)
