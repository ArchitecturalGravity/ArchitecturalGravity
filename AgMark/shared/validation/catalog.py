"""Exact shared-schema identity and catalog validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .core import SchemaIdentity, ValidationIssue


CATALOG_SCHEMA = SchemaIdentity(
    "arcgrav.shared.schema.catalog",
    "1.0.0",
)
_CATALOG_SCHEMA_URN = "urn:arcgrav:shared:schema:catalog:1.0.0"
_CATALOG_SCHEMA_FILE = "AgMark/shared/schemas/schema_catalog.schema.json"


@dataclass(frozen=True)
class CatalogEntry:
    """Catalog binding for one exact shared schema version."""

    schema: SchemaIdentity
    urn: str
    file: str

    def __post_init__(self) -> None:
        if type(self.schema) is not SchemaIdentity:
            raise ValueError("catalog entry schema must be a SchemaIdentity")
        if not isinstance(self.urn, str) or not self.urn:
            raise ValueError("catalog entry urn must be a non-empty string")
        if not isinstance(self.file, str) or not self.file:
            raise ValueError("catalog entry file must be a non-empty string")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CatalogEntry":
        schema_id = value.get("schema_id")
        schema_version = value.get("schema_version")
        urn = value.get("urn")
        file = value.get("file")
        required = (schema_id, schema_version, urn, file)
        if not all(isinstance(item, str) and item for item in required):
            raise ValueError(
                "catalog entry requires non-empty schema_id, schema_version, urn, and file"
            )
        return cls(
            schema=SchemaIdentity(schema_id, schema_version),
            urn=urn,
            file=file,
        )


def validate_exact_schema_identity(
    document: Mapping[str, Any],
    *,
    expected: SchemaIdentity,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate exact schema ID and version without inferring either value."""

    _require_source_id(source_id)
    _require_schema_identity(expected, parameter="expected")
    issues: list[ValidationIssue] = []
    _check_exact_field(
        document,
        field="schema_id",
        expected=expected.schema_id,
        missing_code="SCHEMA_ID_MISSING",
        mismatch_code="SCHEMA_ID_MISMATCH",
        source_id=source_id,
        schema=expected,
        issues=issues,
    )
    _check_exact_field(
        document,
        field="schema_version",
        expected=expected.schema_version,
        missing_code="SCHEMA_VERSION_MISSING",
        mismatch_code="SCHEMA_VERSION_MISMATCH",
        source_id=source_id,
        schema=expected,
        issues=issues,
    )
    return tuple(sorted(issues, key=ValidationIssue.sort_key))


def validate_schema_catalog(
    catalog: Mapping[str, Any],
    *,
    schema_document: Mapping[str, Any],
    source_id: str = "shared-schema-catalog",
) -> tuple[ValidationIssue, ...]:
    """Validate the bootstrap schema catalog before any entry is authoritative."""

    _require_source_id(source_id)
    issues = list(
        validate_exact_schema_identity(
            catalog,
            expected=CATALOG_SCHEMA,
            source_id=source_id,
        )
    )
    raw_entries = catalog.get("entries")
    if not isinstance(raw_entries, list):
        issues.append(
            ValidationIssue(
                code="CATALOG_ENTRIES_INVALID",
                source_id=source_id,
                json_pointer="/entries",
                message="schema catalog entries must be an array",
                schema=CATALOG_SCHEMA,
            )
        )
        return _normalize(issues)

    matches: list[CatalogEntry] = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, Mapping):
            continue
        if (
            raw.get("schema_id") == CATALOG_SCHEMA.schema_id
            and raw.get("schema_version") == CATALOG_SCHEMA.schema_version
        ):
            try:
                matches.append(CatalogEntry.from_mapping(raw))
            except ValueError as exc:
                issues.append(
                    ValidationIssue(
                        code="CATALOG_ENTRY_INVALID",
                        source_id=source_id,
                        json_pointer=f"/entries/{index}",
                        message=str(exc),
                        schema=CATALOG_SCHEMA,
                    )
                )

    if not matches:
        issues.append(
            ValidationIssue(
                code="SCHEMA_NOT_CATALOGED",
                source_id=source_id,
                json_pointer="/entries",
                message="the shared schema catalog must catalog its own exact schema",
                schema=CATALOG_SCHEMA,
            )
        )
        return _normalize(issues)
    if len(matches) != 1:
        issues.append(
            ValidationIssue(
                code="SCHEMA_CATALOG_IDENTITY_AMBIGUOUS",
                source_id=source_id,
                json_pointer="/entries",
                message="the shared schema catalog schema identity must resolve exactly once",
                schema=CATALOG_SCHEMA,
            )
        )
        return _normalize(issues)

    catalog_entry = matches[0]
    if catalog_entry.urn != _CATALOG_SCHEMA_URN:
        issues.append(
            ValidationIssue(
                code="SCHEMA_URN_MISMATCH",
                source_id=source_id,
                json_pointer="/entries",
                message=f"catalog schema URN must equal {_CATALOG_SCHEMA_URN!r}",
                schema=CATALOG_SCHEMA,
            )
        )
    if catalog_entry.file != _CATALOG_SCHEMA_FILE:
        issues.append(
            ValidationIssue(
                code="CATALOG_SCHEMA_FILE_MISMATCH",
                source_id=source_id,
                json_pointer="/entries",
                message=f"catalog schema file must equal {_CATALOG_SCHEMA_FILE!r}",
                schema=CATALOG_SCHEMA,
            )
        )

    issues.extend(
        validate_cataloged_schema_document(
            schema_document,
            entry=catalog_entry,
            source_id=catalog_entry.file,
        )
    )
    if issues:
        return _normalize(issues)

    from .structure import validate_json_schema_structure

    issues.extend(
        validate_json_schema_structure(
            catalog,
            schema_document=schema_document,
            schema=CATALOG_SCHEMA,
            source_id=source_id,
        )
    )
    if issues:
        return _normalize(issues)
    issues.extend(_catalog_uniqueness_issues(catalog, source_id=source_id))
    return _normalize(issues)


def resolve_catalog_entry(
    catalog: Mapping[str, Any],
    *,
    expected: SchemaIdentity,
    catalog_schema_document: Mapping[str, Any],
    source_id: str = "shared-schema-catalog",
) -> tuple[CatalogEntry | None, tuple[ValidationIssue, ...]]:
    """Resolve exactly one catalog entry for expected or fail closed."""

    _require_source_id(source_id)
    _require_schema_identity(expected, parameter="expected")
    catalog_issues = validate_schema_catalog(
        catalog,
        schema_document=catalog_schema_document,
        source_id=source_id,
    )
    if catalog_issues:
        return None, catalog_issues

    raw_entries = catalog["entries"]
    matches: list[CatalogEntry] = []
    for raw in raw_entries:
        if (
            raw.get("schema_id") == expected.schema_id
            and raw.get("schema_version") == expected.schema_version
        ):
            matches.append(CatalogEntry.from_mapping(raw))

    if not matches:
        issues = (
            ValidationIssue(
                code="SCHEMA_NOT_CATALOGED",
                source_id=source_id,
                json_pointer="/entries",
                message=(
                    f"no catalog entry for {expected.schema_id} "
                    f"version {expected.schema_version}"
                ),
                schema=expected,
            ),
        )
        return None, issues
    if len(matches) != 1:
        issues = (
            ValidationIssue(
                code="SCHEMA_CATALOG_IDENTITY_AMBIGUOUS",
                source_id=source_id,
                json_pointer="/entries",
                message=(
                    f"catalog contains {len(matches)} entries for "
                    f"{expected.schema_id} version {expected.schema_version}"
                ),
                schema=expected,
            ),
        )
        return None, issues
    return matches[0], ()


def validate_cataloged_schema_document(
    schema_document: Mapping[str, Any],
    *,
    entry: CatalogEntry,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate schema identity fields against an exact catalog binding."""

    _require_source_id(source_id)
    _require_catalog_entry(entry)
    issues = list(
        validate_exact_schema_identity(
            schema_document,
            expected=entry.schema,
            source_id=source_id,
        )
    )
    schema_urn = schema_document.get("$id")
    if schema_urn is None:
        issues.append(
            ValidationIssue(
                code="SCHEMA_URN_MISSING",
                source_id=source_id,
                json_pointer="/$id",
                message=f"schema $id must equal {entry.urn!r}",
                schema=entry.schema,
            )
        )
    elif schema_urn != entry.urn:
        issues.append(
            ValidationIssue(
                code="SCHEMA_URN_MISMATCH",
                source_id=source_id,
                json_pointer="/$id",
                message=f"schema $id must equal {entry.urn!r}",
                schema=entry.schema,
            )
        )
    return tuple(sorted(issues, key=ValidationIssue.sort_key))


def _catalog_uniqueness_issues(
    catalog: Mapping[str, Any],
    *,
    source_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    identities: set[tuple[str, str]] = set()
    urns: set[str] = set()
    files: set[str] = set()
    for index, raw in enumerate(catalog["entries"]):
        identity = (raw["schema_id"], raw["schema_version"])
        if identity in identities:
            issues.append(
                ValidationIssue(
                    code="SCHEMA_CATALOG_IDENTITY_AMBIGUOUS",
                    source_id=source_id,
                    json_pointer=f"/entries/{index}/schema_id",
                    message=(
                        f"schema identity {identity[0]!r} version "
                        f"{identity[1]!r} is cataloged more than once"
                    ),
                    schema=SchemaIdentity(*identity),
                )
            )
        identities.add(identity)
        urn = raw["urn"]
        if urn in urns:
            issues.append(
                ValidationIssue(
                    code="SCHEMA_CATALOG_URN_AMBIGUOUS",
                    source_id=source_id,
                    json_pointer=f"/entries/{index}/urn",
                    message=f"schema URN {urn!r} is cataloged more than once",
                    schema=CATALOG_SCHEMA,
                )
            )
        urns.add(urn)
        file = raw["file"]
        if file in files:
            issues.append(
                ValidationIssue(
                    code="SCHEMA_CATALOG_FILE_AMBIGUOUS",
                    source_id=source_id,
                    json_pointer=f"/entries/{index}/file",
                    message=f"schema file {file!r} is cataloged more than once",
                    schema=CATALOG_SCHEMA,
                )
            )
        files.add(file)
    return issues


def _require_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id must be a non-empty string")


def _require_schema_identity(value: object, *, parameter: str) -> None:
    if type(value) is not SchemaIdentity:
        raise TypeError(f"{parameter} must be a SchemaIdentity")


def _require_catalog_entry(entry: object) -> None:
    if type(entry) is not CatalogEntry:
        raise TypeError("entry must be a CatalogEntry")


def _normalize(issues: list[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


def _check_exact_field(
    document: Mapping[str, Any],
    *,
    field: str,
    expected: str,
    missing_code: str,
    mismatch_code: str,
    source_id: str,
    schema: SchemaIdentity,
    issues: list[ValidationIssue],
) -> None:
    pointer = f"/{field}"
    if field not in document:
        issues.append(
            ValidationIssue(
                code=missing_code,
                source_id=source_id,
                json_pointer=pointer,
                message=f"{field} must be exactly {expected!r}; value is missing",
                schema=schema,
            )
        )
        return
    if document[field] != expected:
        issues.append(
            ValidationIssue(
                code=mismatch_code,
                source_id=source_id,
                json_pointer=pointer,
                message=f"{field} must be exactly {expected!r}",
                schema=schema,
            )
        )


__all__ = [
    "CATALOG_SCHEMA",
    "CatalogEntry",
    "resolve_catalog_entry",
    "validate_cataloged_schema_document",
    "validate_exact_schema_identity",
    "validate_schema_catalog",
]
