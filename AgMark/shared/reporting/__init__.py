"""Benchmark-neutral accepted-evidence reporting primitives."""

from .generation import (
    REPORT_MANIFEST_SCHEMA_ID,
    REPORT_MANIFEST_SCHEMA_VERSION,
    GeneratedReportBundle,
    GeneratedReportComponent,
    generate_report_bundle,
)
from .model import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_VERSION,
    REPORT_STATUSES,
    REQUIRED_REPORT_SECTIONS,
    SECTION_AVAILABILITY,
    AcceptedReportingInput,
    CanonicalReportModel,
    CaseResultEntry,
    ObservationCounts,
    ObservationMatrixEntry,
    RegisteredReportMetric,
    ReportArtifactRef,
    ReportSection,
    TreatmentSummary,
    build_canonical_report_model,
)
from .revalidation import (
    ReportingInputRevalidationError,
    RevalidatedReportingInput,
    admit_finalized_run_for_reporting,
    revalidate_accepted_reporting_input,
)


__all__ = [
    "REPORT_MANIFEST_SCHEMA_ID",
    "REPORT_MANIFEST_SCHEMA_VERSION",
    "GeneratedReportBundle",
    "GeneratedReportComponent",
    "REPORT_SCHEMA_ID",
    "REPORT_SCHEMA_VERSION",
    "REPORT_STATUSES",
    "REQUIRED_REPORT_SECTIONS",
    "SECTION_AVAILABILITY",
    "AcceptedReportingInput",
    "CanonicalReportModel",
    "CaseResultEntry",
    "ObservationCounts",
    "ObservationMatrixEntry",
    "RegisteredReportMetric",
    "ReportArtifactRef",
    "ReportSection",
    "ReportingInputRevalidationError",
    "RevalidatedReportingInput",
    "TreatmentSummary",
    "admit_finalized_run_for_reporting",
    "build_canonical_report_model",
    "generate_report_bundle",
    "revalidate_accepted_reporting_input",
]
