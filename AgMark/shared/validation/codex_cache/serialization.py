"""Exact catalog-backed admission and semantic revalidation of replay bytes."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import get_type_hints, get_origin, get_args

from ..catalog import resolve_catalog_entry
from ..core import SchemaIdentity
from ..structure import validate_cataloged_document
from . import models as m


@lru_cache(maxsize=128)
def _dataclass_metadata(cls):
    # Only stable Python class metadata is cached. Documents, schema files and
    # retained evidence are still admitted and revalidated on every call.
    return frozenset(f.name for f in fields(cls)), get_type_hints(cls)


def _decode(cls, value):
    if isinstance(cls, type) and is_dataclass(cls):
        names, hints = _dataclass_metadata(cls)
        if not isinstance(value, Mapping) or set(value) != names:
            raise ValueError(f"exact {cls.__name__} fields required")
        return cls(**{k: _decode(hints[k], v) for k, v in value.items()})
    origin, args = get_origin(cls), get_args(cls)
    if origin is tuple:
        return tuple(_decode(args[0], v) for v in value)
    if origin is Mapping:
        return {k: _decode(args[1], v) for k, v in value.items()}
    return value


def admit_validation(document, *, schema_root=None):
    """Read a replay/treatment document; reject unsupported identities and grain."""
    if isinstance(document, bytes):
        document = json.loads(document.decode("utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("validation must be an object")
    identity = document.get("schema_id")
    cls = {m.SCHEMA_ID: m.ProviderRequestCacheValidation,
           m.TREATMENT_SCHEMA_ID: m.ProviderRequestCacheTreatmentSummary}.get(identity)
    if cls is None:
        raise ValueError("unsupported validation identity")
    root = Path(schema_root) if schema_root else Path(__file__).resolve().parents[2] / "schemas"
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    bootstrap = json.loads((root / "schema_catalog.schema.json").read_text(encoding="utf-8"))
    entry, issues = resolve_catalog_entry(catalog, expected=SchemaIdentity(identity, m.SCHEMA_VERSION), catalog_schema_document=bootstrap)
    if issues or entry is None:
        raise ValueError(f"validation catalog rejected: {issues}")
    schema = json.loads((root / Path(entry.file).name).read_text(encoding="utf-8"))
    issues = validate_cataloged_document(document, schema_document=schema, entry=entry, source_id="provider-request-validation")
    if issues:
        raise ValueError(f"validation schema rejected: {issues}")
    result = _decode(cls, document)
    from .metrics import replay_summary, treatment_summary, derive_request
    replays = (result,) if cls is m.ProviderRequestCacheValidation else result.replays
    for replay in replays:
        if any(derive_request(r).to_dict() != r.to_dict() for r in replay.requests):
            raise ValueError("request arithmetic or availability changed")
        expected = replay_summary(validation_id=replay.validation_id,
            validates_observation_id=replay.validates_observation_id, treatment_id=replay.treatment_id,
            repetition_id=replay.repetition_id, configuration_match=replay.configuration_match,
            runtime_equivalence=replay.runtime_equivalence, capabilities=replay.capabilities,
            requests=replay.requests, limitations=replay.replay_summary.limitations)
        if expected.to_dict() != replay.replay_summary.to_dict():
            raise ValueError("replay summary differs from normalized requests")
    if cls is m.ProviderRequestCacheTreatmentSummary:
        expected = treatment_summary(generation_id=result.generation_id, treatment_id=result.treatment_id,
            replays=result.replays, scored_observation_ids=result.scored_observation_ids,
            sampling_policy=result.sampling_policy, sampling_reason=result.sampling_reason)
        for name in ("coverage", "metrics", "sampled_observation_ids"):
            if m.to_value(getattr(expected, name)) != m.to_value(getattr(result, name)):
                raise ValueError("treatment statistics or coverage differ from retained replays")
    return result


def validation_bytes(value):
    document = value.to_dict()
    admit_validation(document)
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
