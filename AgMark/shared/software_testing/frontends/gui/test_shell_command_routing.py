"""Toolkit-independent tests for shell command routing and worker dispatch."""

from __future__ import annotations

from threading import Event, get_ident
import unittest

from AgMark.gui.shell.window import (
    ShellCommandRouter,
    SidebarInputSnapshot,
)


class ShellCommandRouterTests(unittest.TestCase):
    def test_default_dispatch_runs_caller_owned_operations_off_calling_thread(self) -> None:
        caller_thread = get_ident()
        snapshot = SidebarInputSnapshot(
            benchmark="Authority Resolution",
            runner="Codex CLI",
            model="gpt-5.6",
            credential="transient-secret",
            temperature=0.2,
            max_tokens=4096.0,
        )
        seen: dict[str, tuple[object, int]] = {}
        completed = {
            name: Event()
            for name in ("build", "select", "delete", "accept", "start")
        }

        def record(name: str, value: object) -> None:
            seen[name] = (value, get_ident())
            completed[name].set()

        router = ShellCommandRouter(
            on_build_plan=lambda value: record("build", value),
            on_run_selected=lambda value: record("select", value),
            on_delete_run=lambda value: record("delete", value),
            on_accept_plan=lambda: record("accept", "accepted"),
            on_start_benchmark=lambda: record("start", "started"),
        )
        router.build_plan(snapshot)
        router.select_run("run-b")
        router.delete_run("run-b")
        router.accept_plan()
        router.start_benchmark()

        for name, event in completed.items():
            self.assertTrue(event.wait(2.0), f"{name} command did not complete")

        self.assertEqual(seen["build"][0], snapshot)
        self.assertEqual(seen["select"][0], "run-b")
        self.assertEqual(seen["delete"][0], "run-b")
        self.assertEqual(seen["accept"][0], "accepted")
        self.assertEqual(seen["start"][0], "started")
        for _value, worker_thread in seen.values():
            self.assertNotEqual(worker_thread, caller_thread)

    def test_injected_dispatcher_receives_commands_before_operations_execute(self) -> None:
        submitted: list[object] = []
        calls: list[str] = []
        router = ShellCommandRouter(
            command_dispatcher=submitted.append,
            on_accept_plan=lambda: calls.append("accept"),
        )

        router.accept_plan()

        self.assertEqual(calls, [])
        self.assertEqual(len(submitted), 1)
        operation = submitted[0]
        self.assertTrue(callable(operation))
        operation()
        self.assertEqual(calls, ["accept"])

    def test_router_rejects_invalid_command_inputs(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "command_dispatcher must be callable or None",
        ):
            ShellCommandRouter(command_dispatcher=object())

        router = ShellCommandRouter()
        with self.assertRaisesRegex(ValueError, "snapshot must be SidebarInputSnapshot"):
            router.build_plan(object())
        with self.assertRaisesRegex(ValueError, "run_id must be a non-empty string"):
            router.select_run("")
        with self.assertRaisesRegex(ValueError, "run_id must be a non-empty string"):
            router.delete_run("")


if __name__ == "__main__":
    unittest.main()
