"""Full transient labels guard identity when retained release labels are minimized."""
import unittest
from types import SimpleNamespace
from AgMark.gui.requests.runner_boundary import _revalidate_runner_execution_readiness, _PLANNING_PROBE
from AgMark.gui.composition import RepositoryCompositionError
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef, ProviderRuntimeIdentity
from pathlib import Path


class RuntimeVersionBindingTests(unittest.TestCase):
    def test_nonnumeric_labels_require_exact_transient_binding(self):
        runtime = {'runtime_id': 'fixture', 'access_method': 'cli', 'runtime_version': 'privateFixtureA',
                   'provider': None, 'model': None}
        boundary = ExecutionBoundary.build(boundary_id='fixture', framework=IdentityRef('framework', '1.0.0'),
            runner=IdentityRef('runner', '1.0.0'), provider_runtime=ProviderRuntimeIdentity(**runtime))
        self.assertIsNone(boundary.to_dict()['provider_runtime']['runtime_version'])
        self.assertNotIn('privateFixtureA', str(boundary.to_dict()))
        source = SimpleNamespace(registration={'extensions': {_PLANNING_PROBE: 'fixture'}})
        for actual, binding, allowed in (('privateFixtureA', 'privateFixtureA', True),
                                         ('privateFixtureB', 'privateFixtureA', False),
                                         ('privateFixtureA', None, False)):
            with self.subTest(actual=actual, binding=binding):
                def probe(*_):
                    return {'provider_submitted': False, 'status': 'ready',
                            'provider_runtime': {**runtime, 'runtime_version': actual}}
                def validate():
                    _revalidate_runner_execution_readiness(source, repository_root=Path('.'),
                        execution_boundary=boundary, runner_transient_values=None, planning_probe=probe,
                        launch_selection={'expected_runtime_version': binding} if binding else {})
                if allowed:
                    validate()
                else:
                    with self.assertRaisesRegex(RepositoryCompositionError, 'transient runtime identity'):
                        validate()
