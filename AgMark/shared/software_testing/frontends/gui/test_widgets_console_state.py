"""Conformance tests for widget-owned bottom-console projection state."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from AgMark.gui.widgets.console import (
    BottomConsoleState,
    CONSOLE_TABS,
    LAST_EXPANDED_HEIGHT_KEY,
)


class BottomConsoleStateTests(unittest.TestCase):
    def test_reference_view_order_and_snapshot_are_presentation_only(self) -> None:
        state = BottomConsoleState()

        self.assertEqual(
            CONSOLE_TABS,
            ("Live View", "Diagnostics", "Environment", "History"),
        )
        snapshot = state.snapshot()
        self.assertEqual(snapshot.active_tab, "Live View")
        self.assertEqual(snapshot.authority_semantics, "presentation-only")
        with self.assertRaises(FrozenInstanceError):
            snapshot.expanded = False  # type: ignore[misc]

    def test_history_retains_repeated_timestamped_messages_for_session(self) -> None:
        from datetime import datetime
        state = BottomConsoleState()
        state.append_history("Ready")
        state.append_history("Ready")
        state.bind_generation("first")
        state.bind_generation("second")
        state.detach_generation("second")
        state.select_tab("History")
        lines = state.visible_text.splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            timestamp, message = line.split("] ", 1)
            self.assertIsNotNone(datetime.fromisoformat(timestamp[1:]).tzinfo)
            self.assertEqual(message, "Ready")
        state.clear_visible()
        self.assertEqual(state.visible_text.splitlines(), lines)
        fresh = BottomConsoleState()
        fresh.select_tab("History")
        self.assertEqual(fresh.visible_text, "")

    def test_generation_binding_rejects_stale_live_and_diagnostic_events(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")
        self.assertTrue(state.set_live_view("generation-a", "one", "prompt", "first\n"))
        self.assertTrue(state.append_diagnostic("generation-a", "[redacted]\n"))

        self.assertFalse(state.append_live_output("generation-stale", "stale\n"))
        self.assertFalse(state.append_diagnostic("generation-stale", "secret\n"))

        state.select_tab("Live View")
        self.assertEqual(state.visible_text, "Input:\nprompt\n\nOutput:\nfirst\n")
        state.select_tab("Diagnostics")
        self.assertEqual(state.visible_text, "[redacted]\n")

        state.bind_generation("generation-b")
        self.assertEqual(state.active_generation_id, "generation-b")
        self.assertEqual(state.visible_text, "")

    def test_raw_response_preserves_exact_content_and_distinguishes_unavailable(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")
        state.select_tab("Raw Response")

        self.assertEqual(state.visible_text, "")
        self.assertFalse(state.raw_response_available)

        exact = '{\n  "answer": "verbatim  value"\n}\n'
        self.assertTrue(state.set_raw_response("generation-a", exact))
        self.assertTrue(state.raw_response_available)
        self.assertEqual(state.visible_text, "Input:\nInput unavailable.\n\nOutput:\n" + exact)
        self.assertEqual(state.retained_raw_response, exact)

        self.assertTrue(state.set_raw_response("generation-a", ""))
        self.assertTrue(state.raw_response_available)
        self.assertEqual(state.visible_text, "Input:\nInput unavailable.\n\nOutput:\n")
        self.assertEqual(state.retained_raw_response, "")

    def test_clear_raw_view_does_not_delete_retained_response_projection(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")
        state.set_raw_response("generation-a", "retained")
        state.select_tab("Raw Response")

        state.clear_visible()

        self.assertEqual(state.visible_text, "")
        self.assertTrue(state.raw_response_available)
        self.assertEqual(state.retained_raw_response, "retained")

    def test_clear_affects_only_visible_presentation_buffer(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")
        state.set_live_view("generation-a", "one", "prompt", "live")
        state.append_diagnostic("generation-a", "diag")

        state.select_tab("Live Output")
        state.clear_visible()
        self.assertEqual(state.visible_text, "")

        state.select_tab("Diagnostics")
        self.assertEqual(state.visible_text, "diag")

    def test_environment_is_session_scoped_refreshable_and_generation_independent(self) -> None:
        state = BottomConsoleState()
        self.assertIsNone(state.active_generation_id)

        state.set_environment("repository ready\n")
        state.select_tab("Environment")
        self.assertEqual(state.visible_text, "repository ready\n")

        state.bind_generation("generation-a")
        state.append_live_output("generation-a", "live-a")
        self.assertEqual(state.visible_text, "repository ready\n")

        state.bind_generation("generation-b")
        self.assertEqual(state.visible_text, "repository ready\n")
        state.select_tab("Live Output")
        self.assertEqual(state.visible_text, "")

        state.select_tab("Environment")
        state.clear_visible()
        self.assertEqual(state.visible_text, "")
        state.set_environment("repository refreshed\n")
        self.assertEqual(state.visible_text, "repository refreshed\n")

        fresh_session = BottomConsoleState()
        fresh_session.select_tab("Environment")
        self.assertEqual(fresh_session.visible_text, "")

    def test_resize_persists_only_last_nonzero_presentation_height(self) -> None:
        preferences: dict[str, int] = {}
        state = BottomConsoleState(preferences=preferences, default_expanded_height=240)

        state.resize(315)
        self.assertEqual(preferences, {LAST_EXPANDED_HEIGHT_KEY: 315})
        state.resize(0)
        self.assertFalse(state.expanded)
        self.assertEqual(preferences, {LAST_EXPANDED_HEIGHT_KEY: 315})

        restored = BottomConsoleState(preferences=preferences, default_expanded_height=240)
        self.assertEqual(restored.last_nonzero_expanded_height, 315)
        self.assertEqual(restored.expand(), 315)

    def test_presentation_actions_never_retarget_generation(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")

        state.select_tab("Diagnostics")
        state.resize(300)
        state.collapse()
        state.expand()
        state.clear_visible()

        self.assertEqual(state.active_generation_id, "generation-a")

    def test_generation_change_invalidates_prior_raw_projection(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")
        state.set_raw_response("generation-a", "old-response")
        state.bind_generation("generation-b")
        state.select_tab("Raw Response")

        self.assertFalse(state.set_raw_response("generation-a", "stale-response"))
        self.assertFalse(state.raw_response_available)
        self.assertIsNone(state.retained_raw_response)
        self.assertEqual(state.visible_text, "")


    def test_invocation_snapshots_replace_without_duplicates_or_interleaving(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")
        raw = "  plain prompt\n\nkeep whitespace\t雪🙂\n"
        state.set_live_view("generation-a", "one", input_text=raw)
        state.set_live_view("generation-a", "one", output_text="par")
        state.set_live_view("generation-a", "two", input_text="second", output_text="other")
        state.set_live_view("generation-a", "one", output_text="partial")
        state.set_live_view("generation-a", "one", output_text="partial")
        self.assertEqual(state.visible_text, "Input:\n" + raw + "\n\nOutput:\npartial\n\nInput:\nsecond\n\nOutput:\nother")
        self.assertEqual(state.visible_text.count("Input:"), 2)
        self.assertFalse(state.set_live_view("stale", "one", output_text="BAD"))
        self.assertNotIn("BAD", state.visible_text)
        state.append_live_output("generation-a", "progress log\n")
        self.assertNotIn("progress log", state.visible_text)
        state.select_tab("Diagnostics")
        self.assertEqual(state.visible_text, "progress log\n")

    def test_empty_snapshots_and_clear_do_not_invent_prompt_content(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")
        state.set_live_view("generation-a", "one", "", "")
        self.assertEqual(state.visible_text, "Input:\n\n\nOutput:\n")
        state.clear_visible()
        self.assertEqual(state.visible_text, "")
        state.set_live_view("generation-a", "one", output_text="later")
        self.assertEqual(state.visible_text, "Input:\n\n\nOutput:\nlater")
        state.bind_generation("generation-b")
        self.assertEqual(state.visible_text, "")

    def test_old_saved_tab_names_restore_live_view(self) -> None:
        state = BottomConsoleState()
        for old_label in ("Live Output", "Raw Response"):
            state.select_tab(old_label)
            self.assertEqual(state.active_tab, "Live View")

    def test_missing_historical_input_and_output_still_have_visible_section(self) -> None:
        state = BottomConsoleState()
        state.bind_generation("generation-a")
        state.set_live_view("generation-a", "one")
        self.assertEqual(
            state.visible_text,
            "Input:\nInput unavailable.\n\nOutput:\nOutput unavailable.",
        )

if __name__ == "__main__":
    unittest.main()
