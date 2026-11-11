"""Adversarial Stage 00 gateway checks; not recognition or conformance fixtures.

These checks prove only the current source/authority boundary is passive.
Consumers added in Stages 01–04 need their own independent negative evidence.
"""

from contextlib import ExitStack
import glob
import json
import os
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch
import urllib.request

from AgStudio.shared import LanguageCore


ADVERSARIAL_SOURCE = (
    "Header:\r\n"
    '"""\n'
    "=> this apparent operation is quoted source, not an action\n"
    "../../private/**/*.arc\n"
    '"""\n'
    "**/*.arc ↳ [Target]\n"
    "__import__('os').system('echo document-text-must-not-run')\n"
    "https://example.invalid/execute?source=arc\n"
)


class Stage00GatewayGuaranteeTests(unittest.TestCase):
    def test_source_is_preserved_without_literal_or_wildcard_interpretation(self):
        session = LanguageCore.open_source(
            ADVERSARIAL_SOURCE, arcgrav_version="unknown", profile="safe"
        )
        self.assertEqual(session.source, ADVERSARIAL_SOURCE)
        self.assertEqual(
            session.with_source(ADVERSARIAL_SOURCE + "\r\n").source,
            ADVERSARIAL_SOURCE + "\r\n",
        )
        self.assertEqual(session.source, ADVERSARIAL_SOURCE)
        self.assertFalse(hasattr(session, "nodes"))
        self.assertFalse(hasattr(session, "diagnostics"))
        self.assertFalse(hasattr(session, "expanded_wildcards"))

    def test_document_cannot_induce_common_file_process_glob_or_network_sinks(self):
        # All patch targets are imported before interception; the check only
        # exercises source opening, contract access, and immutable snapshots.
        sinks = (
            "pathlib.Path.open", "pathlib.Path.glob", "pathlib.Path.rglob",
            "glob.glob", "glob.iglob", "os.system",
            "subprocess.Popen", "subprocess.run",
            "socket.socket", "socket.create_connection",
            "urllib.request.urlopen", "builtins.open",
        )
        with ExitStack() as stack:
            guards = [
                stack.enter_context(
                    patch(target, side_effect=AssertionError(
                        f"Stage 00 tried an external action: {target}"
                    ))
                )
                for target in sinks
            ]
            session = LanguageCore.open_source(
                ADVERSARIAL_SOURCE,
                arcgrav_version="unestablished",
                configuration={"nested": {"wildcard": "**/*.arc"}},
            )
            self.assertEqual(session.source, ADVERSARIAL_SOURCE)
            self.assertEqual(session.with_source('"""=> still just text').source,
                             '"""=> still just text')
            self.assertEqual(session.configuration["nested"]["wildcard"], "**/*.arc")
            for guard in guards:
                guard.assert_not_called()

    def test_nested_configuration_keys_cannot_collide_after_json_encoding(self):
        # JSON would otherwise serialize {1: "x"} and {"1": "x"} to the
        # same configuration identity. Nested keys must stay string-only.
        with self.assertRaisesRegex(TypeError, "keys must be strings"):
            LanguageCore.open_source(
                ADVERSARIAL_SOURCE, arcgrav_version="unknown",
                configuration={"scope": {1: "numeric"}},
            )
        with self.assertRaisesRegex(TypeError, "keys must be strings"):
            LanguageCore.open_source(
                ADVERSARIAL_SOURCE, arcgrav_version="unknown",
                configuration={"scope": {"1": "text", 1: "numeric"}},
            )
        for nested in ([{False: "boolean"}], ({2: "tuple member"},)):
            with self.subTest(nested=nested):
                with self.assertRaisesRegex(TypeError, "keys must be strings"):
                    LanguageCore.open_source(
                        ADVERSARIAL_SOURCE, arcgrav_version="unknown",
                        configuration={"scope": nested},
                    )

        accepted = LanguageCore.open_source(
            ADVERSARIAL_SOURCE, arcgrav_version="unknown",
            configuration={"scope": {"1": "text"}},
        )
        self.assertEqual(accepted.configuration, {"scope": {"1": "text"}})
        self.assertEqual(accepted.source, ADVERSARIAL_SOURCE)
        self.assertEqual(
            accepted.with_source("edited").configuration_key,
            accepted.configuration_key,
        )

        # Shared references are valid JSON data, while a true cycle still
        # fails closed at the JSON serialization boundary.
        shared = {"text": "safe"}
        repeated = LanguageCore.open_source(
            ADVERSARIAL_SOURCE, arcgrav_version="unknown",
            configuration={"first": shared, "second": shared},
        )
        self.assertEqual(repeated.configuration["first"], shared)
        self.assertEqual(repeated.configuration["second"], shared)
        cycle = {}
        cycle["self"] = cycle
        with self.assertRaises(ValueError):
            LanguageCore.open_source(
                ADVERSARIAL_SOURCE, arcgrav_version="unknown",
                configuration={"cycle": cycle},
            )

    def test_fixed_context_and_authority_policy_are_reproducible_and_detached(self):
        configuration = {
            "scope": {"wildcard": "*.arc", "items": [1, True, None]},
            "unicode": "λ",
        }
        differently_ordered = {
            "unicode": "λ",
            "scope": {"items": [1, True, None], "wildcard": "*.arc"},
        }
        first = LanguageCore.open_source(
            ADVERSARIAL_SOURCE, arcgrav_version="unknown",
            profile="default", configuration=configuration,
        )
        second = LanguageCore.open_source(
            ADVERSARIAL_SOURCE, arcgrav_version="unknown",
            profile="default", configuration=differently_ordered,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.configuration_key, second.configuration_key)
        configuration["scope"]["items"].append("later")
        first.configuration["scope"]["items"].append("detached")
        self.assertEqual(first.configuration["scope"]["items"], [1, True, None])
        self.assertEqual(first.with_source("edit").configuration_key,
                         second.configuration_key)



if __name__ == "__main__":
    unittest.main()
