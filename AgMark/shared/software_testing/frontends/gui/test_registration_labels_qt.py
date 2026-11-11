"""Registration presentation must not change selections or canonical requests."""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel
from AgMark.gui.design_system.theme import arcgrav_application_icon
from AgMark.gui.shell.registration_choices import registration_choices
from AgMark.gui.shell.window import BenchmarkShellWindow, SidebarProjection
from AgMark.gui.widgets.inputs import SelectInput

BENCHMARKS = (
    "arcgrav.authority-resolution.benchmark.core@1.0.0",
    "arcgrav.custom.benchmark.core@1.0.0",
)
RUNNERS = ("arcgrav.mock-model.runner@1.0.0", "openai.codex-cli@2.0.0")


class RegistrationLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def test_exact_labels_and_canonical_selection_roundtrip(self):
        # Canonical strings from older saved state remain valid without migration.
        saved = json.loads(json.dumps({"selected_benchmark": BENCHMARKS[1],
                                       "selected_runner": RUNNERS[1]}))
        selected_benchmarks, selected_runners = [], []
        projection = SidebarProjection(benchmark_options=BENCHMARKS, runner_options=RUNNERS, **saved)
        window = BenchmarkShellWindow(
            application_icon=arcgrav_application_icon(),
            sidebar_projection=projection, console_preferences={},
            on_benchmark_selected=selected_benchmarks.append,
            on_runner_selected=selected_runners.append,
        )
        self.addCleanup(window.deleteLater)
        expected = (
            (window.benchmark_input, BENCHMARKS, ("Authority Resolution (v1.0.0)", "Custom Benchmark")),
            (window.runner_input, RUNNERS, ("Mock Model (Local Test)", "OpenAI Codex CLI")),
        )
        for control, values, labels in expected:
            self.assertEqual(control.options, values)
            self.assertEqual(control.value, values[1])
            self.assertEqual(control.combo_box.currentText(), labels[1])
            for index, (value, label) in enumerate(zip(values, labels)):
                self.assertEqual(control.combo_box.itemText(index), label)
                control.combo_box.setCurrentIndex(index)
                self.assertEqual(control.value, value)
            control.set_value(values[0])
        self.assertEqual(selected_benchmarks[-1], BENCHMARKS[0])
        self.assertEqual(selected_runners[-1], RUNNERS[0])
        intent = window.sidebar_input_snapshot()
        self.assertEqual((intent.benchmark, intent.runner), (BENCHMARKS[0], RUNNERS[0]))
        headings = {label.text() for label in window.findChildren(QLabel)}
        self.assertTrue({"Benchmark", "Runner"}.issubset(headings))
        window.set_sidebar_projection(projection)
        restored = window.sidebar_input_snapshot()
        self.assertEqual((restored.benchmark, restored.runner), (BENCHMARKS[1], RUNNERS[1]))

    def test_unknown_names_and_multiple_versions_are_unambiguous(self):
        values = (RUNNERS[1], "openai.codex-cli@3.0.0", "vendor.custom-runner@1.0.0", "Plain Demo")
        choices = registration_choices(values, "runner")
        self.assertEqual(choices["option_labels"], (
            "OpenAI Codex CLI (Adapter v2.0.0)", "OpenAI Codex CLI (Adapter v3.0.0)",
            "Vendor Custom Runner", "Plain Demo"))
        collisions = ("vendor.some-name@1.0.0", "vendor.some_name@1.0.0")
        labels = registration_choices(collisions, "runner")["option_labels"]
        self.assertEqual(len(set(labels)), 2)
        self.assertTrue(all(value in label for value, label in zip(collisions, labels)))
        reversed_labels = registration_choices(tuple(reversed(collisions)), "runner")["option_labels"]
        self.assertEqual(labels, tuple(reversed(reversed_labels)))
        benchmarks = (BENCHMARKS[0], BENCHMARKS[0].replace("1.0.0", "2.0.0"))
        self.assertEqual(registration_choices(benchmarks, "benchmark")["option_labels"],
                         ("Authority Resolution (v1.0.0)", "Authority Resolution (v2.0.0)"))
        self.assertEqual(registration_choices(("vendor.new-domain.benchmark.core@3.0.0",),
                                             "benchmark")["option_labels"],
                         ("New Domain (v3.0.0)",))

    def test_select_empty_state_and_metadata_validation(self):
        control = SelectInput("Runner", RUNNERS, option_labels=("Mock", "Live"))
        self.addCleanup(control.deleteLater)
        self.assertIsNone(control.value)
        control.set_value(RUNNERS[1])
        self.assertEqual(control.value, RUNNERS[1])
        control.set_value(None)
        with self.assertRaises(ValueError):
            control.set_value("Live")
        with self.assertRaises(ValueError):
            SelectInput("Runner", RUNNERS, option_labels=("only one",))
        with self.assertRaises(ValueError):
            SelectInput("Runner", RUNNERS, option_labels=("same", "same"))
