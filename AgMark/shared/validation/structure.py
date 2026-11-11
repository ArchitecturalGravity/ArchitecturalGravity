"""Fail-closed structural validation for cataloged shared JSON Schemas.

The shared schema catalog currently publishes Draft 2020-12 schemas using a
bounded vocabulary. This module implements that vocabulary with the standard
library and rejects unsupported schema keywords instead of silently weakening
validation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import math
import re
from typing import Any

from .catalog import (
    CatalogEntry,
    validate_cataloged_schema_document,
    validate_exact_schema_identity,
)
from .core import SchemaIdentity, ValidationIssue


_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
_SCHEMA_ANNOTATIONS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "schema_id",
        "schema_version",
        "x-arcgrav-extension-policy",
    }
)
_SCHEMA_KEYWORDS = frozenset(
    {
        "$defs",
        "$ref",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "propertyNames",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "pattern",
        "format",
        "minimum",
        "enum",
        "const",
        "allOf",
        "oneOf",
        "not",
        "if",
        "then",
        "else",
    }
)
_JSON_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)
_DATE_TIME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[Tt]"
    r"(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"(?P<zone>[Zz]|[+-]\d{2}:\d{2})$"
)
_MISSING = object()


def validate_cataloged_document(
    document: Any,
    *,
    schema_document: Mapping[str, Any],
    entry: CatalogEntry,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate one document against one exact catalog-resolved shared schema.

    The schema binding is checked before its structure is trusted. The input is
    never mutated or repaired, and unsupported schema vocabulary fails closed.
    """

    _require_source_id(source_id)
    if type(entry) is not CatalogEntry:
        raise TypeError("entry must be a CatalogEntry")
    schema_issues = list(
        validate_cataloged_schema_document(
            schema_document,
            entry=entry,
            source_id=entry.file,
        )
    )
    schema_issues.extend(
        _schema_definition_issues(
            schema_document,
            root=schema_document,
            identity=entry.schema,
            source_id=entry.file,
            schema_pointer="",
        )
    )
    if schema_issues:
        return _normalize(schema_issues)

    return _cataloged_instance_issues(document, schema_document, entry, source_id)


def prepare_cataloged_validator(*, schema_document: Mapping[str, Any], entry: CatalogEntry):
    """Prepare an isolated schema snapshot for one caller-owned operation.

    Only schema preparation is reused. Every document receives fresh identity
    and structural validation; no document result or global authority is cached.
    The closure owns its schema copy, so later caller mutation cannot alter it.
    """
    if type(entry) is not CatalogEntry:
        raise TypeError("entry must be a CatalogEntry")

    def snapshot(value):
        if isinstance(value, Mapping):
            return {key: snapshot(child) for key, child in value.items()}
        if isinstance(value, list):
            return [snapshot(child) for child in value]
        return value

    schema = snapshot(schema_document)
    issues = list(validate_cataloged_schema_document(schema, entry=entry, source_id=entry.file))
    issues.extend(_schema_definition_issues(schema, root=schema, identity=entry.schema,
                                           source_id=entry.file, schema_pointer=""))
    prepared_issues = _normalize(issues)

    def validate(document, *, source_id):
        _require_source_id(source_id)
        if prepared_issues:
            return prepared_issues
        return _cataloged_instance_issues(document, schema, entry, source_id)

    return validate


def _cataloged_instance_issues(document, schema_document, entry, source_id):
    issues: list[ValidationIssue] = []
    if isinstance(document, Mapping):
        issues.extend(
            validate_exact_schema_identity(
                document,
                expected=entry.schema,
                source_id=source_id,
            )
        )
    issues.extend(
        _instance_issues(
            document,
            schema_document,
            root=schema_document,
            identity=entry.schema,
            source_id=source_id,
            pointer="",
            ref_stack=(),
        )
    )
    return _normalize(issues)


def validate_json_schema_structure(
    document: Any,
    *,
    schema_document: Mapping[str, Any],
    schema: SchemaIdentity,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate structure against the supported shared Draft 2020-12 vocabulary."""

    _require_source_id(source_id)
    if type(schema) is not SchemaIdentity:
        raise TypeError("schema must be a SchemaIdentity")
    definition_issues = _schema_definition_issues(
        schema_document,
        root=schema_document,
        identity=schema,
        source_id=source_id,
        schema_pointer="",
    )
    if definition_issues:
        return _normalize(definition_issues)
    return _normalize(
        _instance_issues(
            document,
            schema_document,
            root=schema_document,
            identity=schema,
            source_id=source_id,
            pointer="",
            ref_stack=(),
        )
    )


def _schema_definition_issues(
    schema: object,
    *,
    root: Mapping[str, Any],
    identity: SchemaIdentity | None,
    source_id: str,
    schema_pointer: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(schema, bool):
        return issues
    if not isinstance(schema, Mapping):
        return [
            _definition_issue(
                identity,
                source_id,
                schema_pointer,
                "schema node must be an object or boolean",
            )
        ]

    unknown = sorted(
        key
        for key in schema
        if key not in _SCHEMA_ANNOTATIONS
        and key not in _SCHEMA_KEYWORDS
        and not key.startswith("x-")
    )
    for key in unknown:
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, key),
                f"unsupported schema keyword {key!r}",
            )
        )

    dialect = schema.get("$schema")
    if dialect is not None and dialect != _DRAFT_2020_12:
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, "$schema"),
                f"schema dialect must be exactly {_DRAFT_2020_12!r}",
            )
        )

    ref = schema.get("$ref")
    if ref is not None:
        if not isinstance(ref, str) or _resolve_local_ref(root, ref) is _MISSING:
            issues.append(
                _definition_issue(
                    identity,
                    source_id,
                    _join_pointer(schema_pointer, "$ref"),
                    "$ref must resolve to a local schema node",
                )
            )

    declared_type = schema.get("type")
    if declared_type is not None and not _valid_type_declaration(declared_type):
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, "type"),
                (
                    "type must be a JSON type name or a non-empty unique array "
                    "of JSON type names"
                ),
            )
        )

    for keyword in ("minItems", "maxItems", "minLength"):
        value = schema.get(keyword)
        if value is not None and (not _is_integer(value) or value < 0):
            issues.append(
                _definition_issue(
                    identity,
                    source_id,
                    _join_pointer(schema_pointer, keyword),
                    f"{keyword} must be a non-negative integer",
                )
            )

    if (
        _is_integer(schema.get("minItems"))
        and _is_integer(schema.get("maxItems"))
        and schema["minItems"] > schema["maxItems"]
    ):
        issues.append(
            _definition_issue(
                identity,
                source_id,
                schema_pointer,
                "minItems must not exceed maxItems",
            )
        )

    unique_items = schema.get("uniqueItems")
    if unique_items is not None and not isinstance(unique_items, bool):
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, "uniqueItems"),
                "uniqueItems must be boolean",
            )
        )

    minimum = schema.get("minimum")
    if minimum is not None and not _is_number(minimum):
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, "minimum"),
                "minimum must be a finite JSON number",
            )
        )

    pattern = schema.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            issues.append(
                _definition_issue(
                    identity,
                    source_id,
                    _join_pointer(schema_pointer, "pattern"),
                    "pattern must be a string",
                )
            )
        else:
            try:
                re.compile(pattern)
            except re.error:
                issues.append(
                    _definition_issue(
                        identity,
                        source_id,
                        _join_pointer(schema_pointer, "pattern"),
                        "pattern must compile as a regular expression",
                    )
                )

    format_name = schema.get("format")
    if format_name is not None and format_name != "date-time":
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, "format"),
                "only the cataloged shared 'date-time' format is supported",
            )
        )

    required = schema.get("required")
    if required is not None and not _unique_string_array(required):
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, "required"),
                "required must be an array of unique strings",
            )
        )

    enum = schema.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum):
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, "enum"),
                "enum must be a non-empty array",
            )
        )

    for keyword in ("$defs", "properties"):
        container = schema.get(keyword)
        if container is None:
            continue
        if not isinstance(container, Mapping) or any(
            not isinstance(key, str) for key in container
        ):
            issues.append(
                _definition_issue(
                    identity,
                    source_id,
                    _join_pointer(schema_pointer, keyword),
                    f"{keyword} must be an object with string keys",
                )
            )
            continue
        for name, child in container.items():
            issues.extend(
                _schema_definition_issues(
                    child,
                    root=root,
                    identity=identity,
                    source_id=source_id,
                    schema_pointer=_join_pointer(
                        _join_pointer(schema_pointer, keyword),
                        name,
                    ),
                )
            )

    additional = schema.get("additionalProperties")
    if additional is not None and not isinstance(additional, (bool, Mapping)):
        issues.append(
            _definition_issue(
                identity,
                source_id,
                _join_pointer(schema_pointer, "additionalProperties"),
                "additionalProperties must be boolean or a schema object",
            )
        )
    elif isinstance(additional, Mapping):
        issues.extend(
            _schema_definition_issues(
                additional,
                root=root,
                identity=identity,
                source_id=source_id,
                schema_pointer=_join_pointer(
                    schema_pointer,
                    "additionalProperties",
                ),
            )
        )

    for keyword in ("propertyNames", "items", "not", "if", "then", "else"):
        child = schema.get(keyword)
        if child is None:
            continue
        if not isinstance(child, (bool, Mapping)):
            issues.append(
                _definition_issue(
                    identity,
                    source_id,
                    _join_pointer(schema_pointer, keyword),
                    f"{keyword} must be a schema object or boolean",
                )
            )
            continue
        issues.extend(
            _schema_definition_issues(
                child,
                root=root,
                identity=identity,
                source_id=source_id,
                schema_pointer=_join_pointer(schema_pointer, keyword),
            )
        )

    for keyword in ("allOf", "oneOf"):
        children = schema.get(keyword)
        if children is None:
            continue
        if not isinstance(children, list) or not children:
            issues.append(
                _definition_issue(
                    identity,
                    source_id,
                    _join_pointer(schema_pointer, keyword),
                    f"{keyword} must be a non-empty array of schemas",
                )
            )
            continue
        for index, child in enumerate(children):
            if not isinstance(child, (bool, Mapping)):
                issues.append(
                    _definition_issue(
                        identity,
                        source_id,
                        _join_pointer(
                            _join_pointer(schema_pointer, keyword),
                            str(index),
                        ),
                        f"{keyword} entries must be schema objects or booleans",
                    )
                )
                continue
            issues.extend(
                _schema_definition_issues(
                    child,
                    root=root,
                    identity=identity,
                    source_id=source_id,
                    schema_pointer=_join_pointer(
                        _join_pointer(schema_pointer, keyword),
                        str(index),
                    ),
                )
            )

    return issues


def _instance_issues(
    value: Any,
    schema: object,
    *,
    root: Mapping[str, Any],
    identity: SchemaIdentity | None,
    source_id: str,
    pointer: str,
    ref_stack: tuple[str, ...],
) -> list[ValidationIssue]:
    if schema is True:
        return []
    if schema is False:
        return [
            _structure_issue(
                identity,
                source_id,
                pointer,
                "value is rejected by the schema",
            )
        ]
    if not isinstance(schema, Mapping):
        return [
            _structure_issue(
                identity,
                source_id,
                pointer,
                "schema definition is invalid",
            )
        ]

    issues: list[ValidationIssue] = []
    ref = schema.get("$ref")
    if isinstance(ref, str):
        target = _resolve_local_ref(root, ref)
        if target is _MISSING or ref in ref_stack:
            return [
                ValidationIssue(
                    code="SCHEMA_DEFINITION_INVALID",
                    source_id=source_id,
                    json_pointer=pointer,
                    message=f"schema reference {ref!r} cannot be resolved safely",
                    schema=identity,
                )
            ]
        issues.extend(
            _instance_issues(
                value,
                target,
                root=root,
                identity=identity,
                source_id=source_id,
                pointer=pointer,
                ref_stack=ref_stack + (ref,),
            )
        )

    for child in schema.get("allOf", ()):
        issues.extend(
            _instance_issues(
                value,
                child,
                root=root,
                identity=identity,
                source_id=source_id,
                pointer=pointer,
                ref_stack=ref_stack,
            )
        )

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = sum(
            not _instance_issues(
                value,
                child,
                root=root,
                identity=identity,
                source_id=source_id,
                pointer=pointer,
                ref_stack=ref_stack,
            )
            for child in one_of
        )
        if matches != 1:
            issues.append(
                _structure_issue(
                    identity,
                    source_id,
                    pointer,
                    f"value must satisfy exactly one oneOf branch; matched {matches}",
                )
            )

    if "not" in schema and not _instance_issues(
        value,
        schema["not"],
        root=root,
        identity=identity,
        source_id=source_id,
        pointer=pointer,
        ref_stack=ref_stack,
    ):
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                "value matches a prohibited not schema",
            )
        )

    condition = schema.get("if")
    if condition is not None:
        condition_matches = not _instance_issues(
            value,
            condition,
            root=root,
            identity=identity,
            source_id=source_id,
            pointer=pointer,
            ref_stack=ref_stack,
        )
        branch = schema.get("then") if condition_matches else schema.get("else")
        if branch is not None:
            issues.extend(
                _instance_issues(
                    value,
                    branch,
                    root=root,
                    identity=identity,
                    source_id=source_id,
                    pointer=pointer,
                    ref_stack=ref_stack,
                )
            )

    if "const" in schema and not _json_equal(value, schema["const"]):
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                "value does not equal required const",
            )
        )

    enum = schema.get("enum")
    if isinstance(enum, list) and not any(
        _json_equal(value, candidate) for candidate in enum
    ):
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                "value is not one of the allowed enum values",
            )
        )

    declared_type = schema.get("type")
    if declared_type is not None and not _matches_type(value, declared_type):
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                f"value does not match declared type {_type_label(declared_type)}",
            )
        )
        return issues

    if isinstance(value, Mapping):
        issues.extend(
            _object_issues(
                value,
                schema,
                root=root,
                identity=identity,
                source_id=source_id,
                pointer=pointer,
                ref_stack=ref_stack,
            )
        )
    elif isinstance(value, list):
        issues.extend(
            _array_issues(
                value,
                schema,
                root=root,
                identity=identity,
                source_id=source_id,
                pointer=pointer,
                ref_stack=ref_stack,
            )
        )
    elif isinstance(value, str):
        issues.extend(
            _string_issues(
                value,
                schema,
                identity,
                source_id,
                pointer,
            )
        )
    elif _is_number(value):
        minimum = schema.get("minimum")
        if _is_number(minimum) and value < minimum:
            issues.append(
                _structure_issue(
                    identity,
                    source_id,
                    pointer,
                    f"number must be greater than or equal to {minimum!r}",
                )
            )

    return issues


def _object_issues(
    value: Mapping[object, Any],
    schema: Mapping[str, Any],
    *,
    root: Mapping[str, Any],
    identity: SchemaIdentity | None,
    source_id: str,
    pointer: str,
    ref_stack: tuple[str, ...],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    properties = schema.get("properties")
    declared = properties if isinstance(properties, Mapping) else {}

    for key in value:
        if not isinstance(key, str):
            issues.append(
                _structure_issue(
                    identity,
                    source_id,
                    pointer,
                    "object keys must be strings",
                )
            )

    required = schema.get("required")
    if isinstance(required, list):
        for name in required:
            if name not in value:
                issues.append(
                    _structure_issue(
                        identity,
                        source_id,
                        _join_pointer(pointer, name),
                        f"required property {name!r} is missing",
                    )
                )

    property_names = schema.get("propertyNames")
    if property_names is not None:
        for key in value:
            if isinstance(key, str):
                issues.extend(
                    _instance_issues(
                        key,
                        property_names,
                        root=root,
                        identity=identity,
                        source_id=source_id,
                        pointer=_join_pointer(pointer, key),
                        ref_stack=ref_stack,
                    )
                )

    for key, child_value in value.items():
        if not isinstance(key, str):
            continue
        child_pointer = _join_pointer(pointer, key)
        if key in declared:
            issues.extend(
                _instance_issues(
                    child_value,
                    declared[key],
                    root=root,
                    identity=identity,
                    source_id=source_id,
                    pointer=child_pointer,
                    ref_stack=ref_stack,
                )
            )
            continue
        additional = schema.get("additionalProperties", True)
        if additional is False:
            issues.append(
                _structure_issue(
                    identity,
                    source_id,
                    child_pointer,
                    f"additional property {key!r} is not allowed",
                )
            )
        elif isinstance(additional, Mapping):
            issues.extend(
                _instance_issues(
                    child_value,
                    additional,
                    root=root,
                    identity=identity,
                    source_id=source_id,
                    pointer=child_pointer,
                    ref_stack=ref_stack,
                )
            )
    return issues


def _array_issues(
    value: list[Any],
    schema: Mapping[str, Any],
    *,
    root: Mapping[str, Any],
    identity: SchemaIdentity | None,
    source_id: str,
    pointer: str,
    ref_stack: tuple[str, ...],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    if _is_integer(min_items) and len(value) < min_items:
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                f"array must contain at least {min_items} items",
            )
        )
    if _is_integer(max_items) and len(value) > max_items:
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                f"array must contain at most {max_items} items",
            )
        )
    if schema.get("uniqueItems") is True:
        # Exact JSON strings have ordinary string equality. Preserve the
        # general JSON comparison for mixed arrays, numbers and containers.
        seen_strings = set() if all(type(item) is str for item in value) else None
        for index, item in enumerate(value):
            if seen_strings is not None:
                duplicate = item in seen_strings
                seen_strings.add(item)
            else:
                duplicate = any(
                    _json_equal(item, previous)
                    for previous in value[:index]
                )
            if duplicate:
                issues.append(
                    _structure_issue(
                        identity,
                        source_id,
                        _join_pointer(pointer, str(index)),
                        (
                            "array item duplicates an earlier item while "
                            "uniqueItems is true"
                        ),
                    )
                )
    items = schema.get("items")
    if items is not None:
        for index, item in enumerate(value):
            issues.extend(
                _instance_issues(
                    item,
                    items,
                    root=root,
                    identity=identity,
                    source_id=source_id,
                    pointer=_join_pointer(pointer, str(index)),
                    ref_stack=ref_stack,
                )
            )
    return issues


def _string_issues(
    value: str,
    schema: Mapping[str, Any],
    identity: SchemaIdentity | None,
    source_id: str,
    pointer: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    min_length = schema.get("minLength")
    if _is_integer(min_length) and len(value) < min_length:
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                f"string length must be at least {min_length}",
            )
        )
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and re.search(pattern, value) is None:
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                f"string does not match required pattern {pattern!r}",
            )
        )
    if schema.get("format") == "date-time" and not _valid_date_time(value):
        issues.append(
            _structure_issue(
                identity,
                source_id,
                pointer,
                "string is not a valid RFC 3339 date-time",
            )
        )
    return issues


def _definition_issue(
    identity: SchemaIdentity | None,
    source_id: str,
    schema_pointer: str,
    message: str,
) -> ValidationIssue:
    location = schema_pointer or "<root>"
    return ValidationIssue(
        code="SCHEMA_DEFINITION_INVALID",
        source_id=source_id,
        message=f"schema definition at {location}: {message}",
        schema=identity,
    )


def _structure_issue(
    identity: SchemaIdentity | None,
    source_id: str,
    pointer: str,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(
        code="SCHEMA_STRUCTURE_INVALID",
        source_id=source_id,
        json_pointer=pointer,
        message=message,
        schema=identity,
    )


def _require_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id must be a non-empty string")


def _normalize(
    issues: Sequence[ValidationIssue],
) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


def _valid_type_declaration(value: object) -> bool:
    if isinstance(value, str):
        return value in _JSON_TYPES
    if not isinstance(value, list) or not value:
        return False
    return (
        all(
            isinstance(item, str) and item in _JSON_TYPES
            for item in value
        )
        and len(set(value)) == len(value)
    )


def _unique_string_array(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and len(set(value)) == len(value)
    )


def _matches_type(value: Any, declared: object) -> bool:
    names = (declared,) if isinstance(declared, str) else tuple(declared)
    return any(_matches_single_type(value, name) for name in names)


def _matches_single_type(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return _is_integer(value)
    if name == "number":
        return _is_number(value)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, Mapping)
    return False


def _type_label(declared: object) -> str:
    if isinstance(declared, str):
        return repr(declared)
    return "[" + ", ".join(repr(item) for item in declared) + "]"


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _json_equal(left: Any, right: Any) -> bool:
    if _is_number(left) and _is_number(right):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(a, b)
            for a, b in zip(left, right)
        )
    if isinstance(left, Mapping):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key])
            for key in left
        )
    return left == right


def _resolve_local_ref(
    root: Mapping[str, Any],
    ref: str,
) -> object:
    if ref == "#":
        return root
    if not ref.startswith("#/"):
        return _MISSING
    current: object = root
    for raw_segment in ref[2:].split("/"):
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
            continue
        if (
            isinstance(current, list)
            and segment.isdigit()
            and int(segment) < len(current)
        ):
            current = current[int(segment)]
            continue
        return _MISSING
    return current


def _join_pointer(pointer: str, segment: str) -> str:
    escaped = segment.replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{escaped}" if pointer else f"/{escaped}"


def _valid_date_time(value: str) -> bool:
    if _DATE_TIME.fullmatch(value) is None:
        return False
    normalized = value.replace("t", "T").replace("z", "Z")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None


__all__ = [
    "prepare_cataloged_validator",
    "validate_cataloged_document",
    "validate_json_schema_structure",
]
