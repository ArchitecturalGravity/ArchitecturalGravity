"""Static inventory of independently collected reporting conformance cases."""

from __future__ import annotations

import unittest

from AgMark.shared.software_testing.integration.test_reporting_publication import (
    ReportingPublicationIntegrationTests,
)
from AgMark.shared.software_testing.integration.test_reporting_revalidation import (
    ReportingRevalidationIntegrationTests,
)
from AgMark.shared.software_testing.integration.test_reporting_runtime_handoff import (
    ReportingRuntimeHandoffIntegrationTests,
)
from AgMark.shared.software_testing.integration.test_reporting_completion import (
    ReportingCompletionIntegrationTests,
)


_REPORTING_CONFORMANCE_CASES = (
    ReportingRevalidationIntegrationTests,
    ReportingRuntimeHandoffIntegrationTests,
    ReportingCompletionIntegrationTests,
    ReportingPublicationIntegrationTests,
)


class ReportingConformanceBatchIntegrationTests(unittest.TestCase):
    """Check the reporting frontier inventory without duplicate execution."""

    def test_reporting_conformance_inventory_is_unique_and_resolves(self) -> None:
        # Operational cases run once in their owning modules. This inventory
        # check must not execute them again as a nested test suite.
        self.assertEqual(len(_REPORTING_CONFORMANCE_CASES),
                         len(set(_REPORTING_CONFORMANCE_CASES)))
        loader = unittest.defaultTestLoader
        for case in _REPORTING_CONFORMANCE_CASES:
            with self.subTest(case=case.__name__):
                self.assertTrue(loader.getTestCaseNames(case))
                self.assertTrue(case.__module__.startswith(
                    "AgMark.shared.software_testing.integration.test_reporting_"))


if __name__ == "__main__":
    unittest.main()
