"""Cold-process boundaries for parser transport and lazy offline spellchecking."""
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]


class AnalysisImportTests(unittest.TestCase):
    def run_fresh(self, script):
        process = subprocess.run(
            [sys.executable, '-c', textwrap.dedent(script)], cwd=ROOT,
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_models_and_parser_transport_never_import_findings_or_spelling(self):
        for module in ('AgStudio.shared.lint', 'AgStudio.shared.lint.model',
                       'AgStudio.shared.lint.syntax', 'AgStudio.shared.analysis_snapshot'):
            with self.subTest(module=module):
                self.run_fresh(f'''
                    import importlib
                    import sys
                    importlib.import_module({module!r})
                    from AgStudio.shared.analysis_snapshot import (
                        AnalysisRequest, calculate_packed_parse, restore_analysis, unpack_analysis,
                    )
                    for configuration in ('{{}}', '{{"spellcheck": false}}'):
                        packed = calculate_packed_parse(AnalysisRequest(
                            'Task:\\n- 🌍 mispelled text\\r\\n', 'current', None, configuration))
                        analysis = restore_analysis(unpack_analysis(packed))
                        assert analysis.diagnostics.status == 'pending'
                        assert analysis.tree.nodes
                    for name in ('AgStudio.shared.lint.findings', 'AgStudio.shared.lint.rules',
                                 'AgStudio.shared.lint.spelling', 'hunspell', 'PySide6'):
                        assert name not in sys.modules, name
                ''')

    def test_importing_findings_and_spelling_does_not_load_the_dictionary(self):
        self.run_fresh('''
            import sys
            from AgStudio.shared.lint import findings, rules, spelling
            assert spelling._CHECKER is spelling._UNINITIALIZED
            assert 'hunspell' not in sys.modules
        ''')

    def test_named_rule_exports_remain_available_without_loading_dictionary(self):
        self.run_fresh('''
            import sys
            import AgStudio.shared.lint as lint
            assert 'AgStudio.shared.lint.rules' not in sys.modules
            from AgStudio.shared.lint import RULES, evaluate_with_admission
            from AgStudio.shared.lint import rules, spelling
            assert RULES is rules.RULES
            assert evaluate_with_admission is rules.evaluate_with_admission
            assert spelling._CHECKER is spelling._UNINITIALIZED
            assert 'hunspell' not in sys.modules
            try:
                lint.not_an_analysis_api
            except AttributeError:
                pass
            else:
                raise AssertionError('unknown attribute accepted')
        ''')

    def test_disabled_spellcheck_in_both_pipelines_never_initializes_dictionary(self):
        self.run_fresh('''
            import sys
            from unittest.mock import patch
            from AgStudio.shared.lint import analyze, spelling
            from AgStudio.shared.analysis_snapshot import (
                AnalysisRequest, calculate_packed_parse, calculate_analysis_snapshot,
            )
            source = 'Task:\\n- 🌍 mispelled text\\n'
            with patch.object(spelling, '_load_checker', side_effect=AssertionError('dictionary loaded')):
                synchronous = analyze(source, configuration={'spellcheck': False})
                staged = calculate_analysis_snapshot(calculate_packed_parse(
                    AnalysisRequest(source, 'current', None, '{"spellcheck": false}')))
            assert synchronous.diagnostics == staged.snapshot.diagnostics
            assert not any(f.rule_id.startswith('AG-SPELL') for f in synchronous.diagnostics.findings)
            assert spelling._CHECKER is spelling._UNINITIALIZED
            assert 'hunspell' not in sys.modules
        ''')

    def test_unsupported_version_and_protected_text_do_not_need_dictionary(self):
        self.run_fresh('''
            from unittest.mock import patch
            from AgStudio.shared.lint import analyze, spelling
            with patch.object(spelling, '_load_checker', side_effect=AssertionError('dictionary loaded')):
                assert not analyze('- mispelled\\n', arcgrav_version='future').diagnostics.findings
                for source in ('', '"mispelled"\\n', '"""\\nmispelled\\n"""\\n'):
                    assert not any(f.rule_id.startswith('AG-SPELL') for f in analyze(source).diagnostics.findings)
            assert spelling._CHECKER is spelling._UNINITIALIZED
        ''')

    def test_default_spelling_and_explicit_suggestions_initialize_only_once(self):
        self.run_fresh('''
            from unittest.mock import patch
            from AgStudio.shared.lint import analyze, spelling
            from AgStudio.shared.analysis_snapshot import (
                AnalysisRequest, calculate_parse_snapshot, calculate_analysis_snapshot,
            )
            source = 'Task:\\n- Please recieve the document\\n'
            with patch.object(spelling, '_load_checker', wraps=spelling._load_checker) as load:
                staged = calculate_analysis_snapshot(calculate_parse_snapshot(
                    AnalysisRequest(source, 'current', None, '{}')))
                synchronous = analyze(source)
                assert staged.snapshot.diagnostics == synchronous.diagnostics
                words = [f.source_range.span.extract(source) for f in synchronous.diagnostics.findings
                         if f.rule_id == 'AG-SPELLING']
                assert words == ['recieve'], words
                assert 'receive' in spelling.suggestions_for_word('recieve')
                assert load.call_count == 1, load.call_count
        ''')

    def test_missing_dictionary_is_cached_and_remains_an_exact_info_finding(self):
        for failure in ('missing_module', 'missing_resource', 'invalid_resource'):
            with self.subTest(failure=failure):
                self.run_fresh(f'''
                    import sys
                    import types
                    from unittest.mock import patch
                    from AgStudio.shared.lint import analyze, spelling
                    failure = {failure!r}
                    if failure == 'missing_module':
                        sys.modules['hunspell'] = None
                    else:
                        module = types.ModuleType('hunspell')
                        def unavailable(*args, **options):
                            raise (OSError if failure == 'missing_resource' else ValueError)('bad resource')
                        module.Hunspell = unavailable
                        sys.modules['hunspell'] = module
                    source = '- 🌍 mispelled text\\n'
                    with patch.object(spelling, '_load_checker', wraps=spelling._load_checker) as load:
                        first = analyze(source)
                        assert analyze(source).diagnostics == first.diagnostics
                        findings = [f for f in first.diagnostics.findings if f.rule_id.startswith('AG-SPELL')]
                        assert len(findings) == 1, findings
                        finding = findings[0]
                        assert (finding.rule_id, finding.severity) == ('AG-SPELLCHECK-UNAVAILABLE', 'information')
                        assert finding.source_range.span.extract(source) == 'mispelled'
                        assert spelling.suggestions_for_word('mispelled') == ()
                        assert load.call_count == 1, load.call_count
                    assert spelling._CHECKER is None
                ''')

    def test_concurrent_first_requests_share_one_dictionary_initialization(self):
        self.run_fresh('''
            from concurrent.futures import ThreadPoolExecutor
            from threading import Barrier
            import time
            from unittest.mock import patch
            from AgStudio.shared.lint import spelling
            checker = object()
            barrier = Barrier(8)
            def load():
                time.sleep(0.02)
                return checker
            def get(_):
                barrier.wait(timeout=5)
                return spelling._get_checker()
            with patch.object(spelling, '_load_checker', side_effect=load) as initialize:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = tuple(pool.map(get, range(8)))
                assert all(result is checker for result in results)
                assert initialize.call_count == 1, initialize.call_count
        ''')


if __name__ == '__main__':
    unittest.main()
