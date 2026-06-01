from __future__ import annotations

from pathlib import Path

HOST_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "opensquilla"
    / "cli"
    / "tui"
    / "opentui"
    / "package"
    / "src"
    / "main.mjs"
)


def test_opentui_host_uses_fullscreen_scrollbox_layout() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert 'screenMode: "alternate-screen"' in source
    assert "ScrollBoxRenderable" in source
    assert 'stickyStart: "bottom"' in source
    assert "viewportCulling" in source
    assert 'id: "composer-box"' in source
    assert 'id: "router-plugin"' in source
    assert 'screenMode: "split-footer"' not in source
    assert "writeToScrollback" not in source


def test_opentui_host_locks_recommended_daily_visual_preset() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "OPENTUI_DAILY_THEME" in source
    assert 'preset: "daily"' in source
    assert 'frameStyle: "card"' in source
    assert 'frame: "#5a6b7a"' in source
    assert "#77B7FF" in source
    assert "class TurnView" in source
    assert "conversationBox.add" in source
    assert "TextRenderable(renderer" in source
    assert "`sb-${scrollbackSeq++}`" in source
    assert "STATUS_PULSE_FRAMES" in source


def test_opentui_host_has_turnview_with_inplace_tool_nodes() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "class TurnView" in source
    assert "addTool" in source
    assert "finishTool" in source
    assert "appendAnswer" in source
    assert "setUsage" in source
    assert "STATUS_PULSE_FRAMES" in source
    assert "✓" in source and "✗" in source


def test_opentui_host_draws_continuous_tool_timeline_rail() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    set_prompt_body = source.split("  setPrompt(text) {", 1)[1].split(
        "  addTool(", 1
    )[0]
    add_tool_body = source.split("  addTool(toolId, name, summary) {", 1)[1].split(
        "  finishTool(", 1
    )[0]
    append_answer_body = source.split("  appendAnswer(delta) {", 1)[1].split(
        "  demoteAnswerToTimeline(", 1
    )[0]

    assert "rail-top" not in set_prompt_body
    assert "`rail-tool-${toolId}`" in add_tool_body
    assert '"│", OPENTUI_DAILY_THEME.faint' in add_tool_body
    assert add_tool_body.index("rail-tool") < add_tool_body.index("tool-${toolId}")
    assert 'this._line("a-gap", "│", OPENTUI_DAILY_THEME.faint)' in append_answer_body


def test_opentui_host_uses_lines_not_backgrounds_for_visual_separation() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "backgroundColor" not in source
    assert "routerBackground" not in source


def test_opentui_host_removes_regex_timeline_classifier() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "decorateDailyTimelineScrollback" not in source
    assert "classifyDailyTimelineLine" not in source
    assert "colorForDailyScrollback" not in source
    assert "conversationBox" in source


def test_opentui_footer_revives_status_and_composer_and_router_color() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "syncPulseTimer" in source
    assert "setInterval" in source
    assert "composerDisabledBorder" in source
    assert "colorForStyle(routerState.style)" in source
    assert "backgroundColor" not in source


def test_opentui_answer_uses_markdown_renderable() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "MarkdownRenderable" in source
    assert "SyntaxStyle" in source
    assert "streaming" in source


def test_opentui_promotes_only_final_answer_run_to_card() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    add_tool_body = source.split("  addTool(toolId, name, summary) {", 1)[1].split(
        "  finishTool(", 1
    )[0]
    finish_answer_body = source.split("  finishAnswer(cancelled) {", 1)[1].split(
        "  setUsage(", 1
    )[0]
    demote_answer_body = source.split("  demoteAnswerToTimeline() {", 1)[1].split(
        "  finishAnswer(", 1
    )[0]

    assert "this.answerTop = null;" in source
    assert "this.box.remove(this.answerTop.id)" in source
    assert "this.box.remove(this.answerMd.id)" in source
    assert "demoteAnswerToTimeline" in source
    assert "this.demoteAnswerToTimeline();" in add_tool_body
    assert "OPENTUI_DAILY_THEME.modelText" in demote_answer_body
    assert "promoteAnswerToCard" in source
    assert "this.promoteAnswerToCard()" in finish_answer_body
    # The answer card header runs a long rule; the footer stays short (top > bottom).
    assert "╭─ answer ─ squilla ${CARD_RULE_LONG}" in source
    assert "╰${CARD_RULE_SHORT}" in source


def test_opentui_input_region_and_scroll_routing() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "inputHistory" in source
    assert "cursorVisible" in source
    assert "scrollBy" in source
    assert 'name === "pageup"' in source or 'name === "pagedown"' in source
