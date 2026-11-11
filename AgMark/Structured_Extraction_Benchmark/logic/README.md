# Structured Extraction Logic

This directory contains benchmark-owned Structured Extraction Benchmark logic resources governed by `SPECIFICATION.md`.

Logic resources are inert by presence. A logic set becomes accepted SEB authority only when an active versioned registration explicitly selects the logic-set manifest and integrity-binds its exact bytes together with the accepted case, requested-field, treatment, metric, golden, parser, scorer, and report authorities for the same generation.

## Core logic set 1.0.0

`v1.0.0/logic-set.json` defines candidate logic set `arcgrav.structured-extraction.logic-set.core@1.0.0`.

The candidate defines requested-field identity generically rather than hard-coding one case schema: each requested field is the exact object key named by accepted registered authority, and its required output is the exact JSON value carried by the same key in accepted case input. Missing source values are not inferred.

The candidate also makes no-inference, no-rewriting, exact JSON type/value preservation, strict single-object output, exact requested-field-set behavior, and explicit non-success states part of one treatment-preservation contract. Concrete treatment identities remain registration-owned; directory membership or this file's presence cannot activate them.

Golden source and case traceability remain registration-bound. Before this logic can influence accepted execution, the active registration must integrity-bind these exact logic bytes and the exact golden/resource identities it selects.

Any change to requested-field meaning, value preservation, output shape, treatment equivalence expectations, failure-state meaning, or traceability requires a new versioned logic set before it can become active authority.
