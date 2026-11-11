"""Frontend executable defaults follow declarations, not adapter identities."""
import unittest
from AgMark.gui.readiness.controls import _effective_selected_control_values, _model_discovery_context_controls


class GenericRunnerControlsTests(unittest.TestCase):
    def resolve(self, selected=None):
        return _effective_selected_control_values(
            controls_raw=[{"name": "launch_mode"}, {"name": "engine_executable"}],
            fixed_values={},
            extensions={"arcgrav.adapters:launch_environment": {
                "supported_modes": ["native"],
                "default_mode_policy": {"windows": "native", "non_windows": "native_if_supported_else_unsupported"},
                "executable_control": "engine_executable",
                "native": {"executable_default": "third-party-engine"},
            }}, selected_control_values=selected or {"launch_mode": "native"},
        )

    def test_arbitrary_registered_executable_control_receives_own_default(self):
        controls = self.resolve()
        self.assertEqual("third-party-engine", controls["engine_executable"])
        self.assertNotIn("codex_binary", controls)

    def test_explicit_selected_executable_is_never_replaced(self):
        self.assertEqual("/selected/engine", self.resolve({
            "launch_mode": "native", "engine_executable": "/selected/engine"
        })["engine_executable"])

    def test_adapter_without_launch_declaration_gets_no_foreign_controls(self):
        self.assertEqual({"model_id": "local-model"}, _effective_selected_control_values(
            controls_raw=[{"name": "model_id"}], fixed_values={}, extensions={},
            selected_control_values={"model_id": "local-model"},
        ))

    def test_explicit_empty_catalog_context_is_valid_but_missing_is_not(self):
        self.assertEqual(((), None), _model_discovery_context_controls({"determining_controls": []}, set()))
        for invalid in ({}, {"determining_controls": None}, {"determining_controls": "none"}):
            self.assertIsNotNone(_model_discovery_context_controls(invalid, set())[1])

    def test_fixed_explicit_catalog_does_not_invent_selection_mode_control(self):
        from AgMark.gui.readiness.controls import _project_model_discovery
        choices, model, mode, diagnostic = _project_model_discovery(
            {"choice_projection": {"default_first": True, "normal_path_free_text": False,
                                   "selection_modes": ["explicit"]}},
            {"status": "ready", "provider_submitted": False, "effective_default_model_id": "local",
             "choices": [{"model_id": "local", "label": "Local", "selection_mode": "explicit"}]},
            [{"name": "model_id", "kind": "text"}],
        )
        self.assertIsNone(diagnostic)
        self.assertEqual("local", model)
        self.assertIsNone(mode)
        self.assertIsNone(choices[0].selection_mode_control_name)

    def test_numeric_control_defaults_are_presented_without_losing_value(self):
        from AgMark.gui.readiness.controls import _selected_control_projection
        from AgMark.gui.shell.projections import SidebarTextControlProjection
        projected = _selected_control_projection(
            SidebarTextControlProjection("timeout", "Timeout", "", required=True), {"timeout": 120000})
        self.assertEqual("120000", projected.value)
