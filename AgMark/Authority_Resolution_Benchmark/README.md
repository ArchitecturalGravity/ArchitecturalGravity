# Authority Resolution Benchmark

The sole ARB authority is `registrations/v2.0.0/benchmark-core.json`. It runs
Golden once for the selected case, retains its structured result, and compares
each treatment and repetition against that same result using **ARB field
accuracy**. The registration selects the complete execution and scoring resource
closure.

## Default source and execution

The single source file is `cases/v1.0.0/arb-core-001.json`. It contains the four
record occurrences and two relations used by all five treatment prompts. The
registration binds this case as the benchmark input.

From the repository root, run:

```text
python AgMark/Authority_Resolution_Benchmark/Legacy_Content/Authority_Resolution_Benchmark.py
```

The standalone entry point resolves the UTF-8 source file relative to its own
benchmark package, passes its text to `run_orchestration(source_text)`, and prints
one JSON object. It requires no command-line input or stdin. The processing API
continues to require an explicit source argument. Missing, unreadable, or invalid
UTF-8 input fails without substituting a source.

The accepted harness declares `registered_file` input transport. It verifies the
registered implementation and case file, checks that the file bytes equal the
accepted case input, and executes a private snapshot preserving their relative
paths. The retained Golden observation identifies the actual input artifact,
hash, and byte length. Other benchmarks may continue to use stdin.

For the current single-case benchmark, admission executes Golden once before any
treatment begins. Every treatment and repetition uses its retained stdout for
scoring. Rescoring and report generation consume retained evidence and do not
execute Golden. A new accepted run gets its own Golden observation.

## Granular accuracy

The metric is `arcgrav.authority-resolution.metric.field-accuracy@1.0.0`, on the
separate `arcgrav.authority-resolution.field-accuracy` comparison track:

```text
correct_units / (expected_units + unexpected_units)
```

Expected units come from the captured Golden, with equal weight per field:

| Component | Unit | Units for the default case |
| --- | --- | ---: |
| Records | `id`, `value`, `status`, `authority`, `derivation`, `confidence` per record | 18 |
| Findings | `id`, `category`, `evidence`, `resolution`, `confidence` per occurrence | 25 |
| Uncertainties | One ordered entry | 1 |
| Execution | `processed`, `resolved`, `findings`, `validated` | 4 |
| Total | Derived from Golden, never hard-coded by the scorer | 48 |

Records match the first occurrence of their exact ID. Findings match exact ID
and occurrence ordinal, preserving duplicate finding IDs. Uncertainties match by
position. Nested values count as one field regardless of size. No fuzzy or
best-match alignment is performed.

Comparisons preserve types: `8`, `8.0`, `"8"`, and `true` are distinct, as are a
missing field, JSON `null`, and the string `"unresolved"`. Object member order
and JSON whitespace are immaterial; nested array order and signed floating zero
are preserved. Python-compatible non-finite constants match the same constant
and sign. Comparison evidence represents them with finite JSON annotations.

Missing or incorrect fields receive no credit for those fields while correct
fields retain credit. A missing or wrongly shaped section loses its expected
units while preserving credit elsewhere. Unparseable treatment JSON or duplicate
JSON member names produce an explicit malformed zero. Invalid Golden output
produces no score. `execution.validated` is one compared field, not proof of
correctness or a gate that discards all other credit.

Unexpected output adds denominator units: six per unmatched record, five per
unmatched finding, one per extra uncertainty, and one per unknown schema key.
Unknown keys on unmatched rows also add units. A wrong ID can create both a
missing expected row and an unexpected row. Extra content inside a known `value`
or `status` field is compared as that field, not as extra schema keys.

| Outcome, with other units correct | Calculation | Field accuracy |
| --- | --- | ---: |
| Exact result | 48 / 48 | 100% |
| One wrong field | 47 / 48 | 97.92% |
| One missing finding | 43 / 48 | 89.58% |
| One missing record | 42 / 48 | 87.50% |
| One extra record | 48 / 54 | 88.89% |

Record and finding order are separate diagnostics. A response can receive 100%
field content accuracy while violating ordering. Reports expose schema validity,
ordering, exact-result match, section counts, record value/status accuracy, and
expected/actual values and dispositions for every comparison unit. Equal field
weights are the registered initial policy, not an empirical importance weighting.

Repetitions are averaged within a case. Treatment summaries average those case
means with equal case weight. These means are not pooled correct-field counts;
reports keep their score/observation or score/case denominators distinct from
per-observation field counts. Unavailable and non-comparable evidence retain
their registered states.

## Correlated resources

| Resource | Authority and maintenance obligation |
| --- | --- |
| `cases/v1.0.0/arb-core-001.json` and `case-set.json` | Exact accepted case; verify embedded prompt sources match, including occurrence and member order. |
| `Legacy_Content/Authority_Resolution_Benchmark.py` and `ARB_Spec.md` | Processing behavior, structured output, and standalone default-file interface. |
| `treatments/v2.0.0/treatment-set.json` and `prompts/` | Five selected invocation forms; ArcGrav binds its selected V4 provenance and uses a private construction recheck. Hash prompt and provenance independently. |
| `logic/v2.0.0/logic-set.json` | Structured-output atom, dependencies, treatment mappings, and retained-Golden prerequisites. |
| `evaluation/structured_parser.py` and `field_scorer.py` | Syntax decoding, baseline validation, granular comparisons, finite JSON evidence. |
| `registrations/v2.0.0/metric-field-accuracy.json` and `scorer-field-accuracy.json` | Formula, matching, extras, dispositions, companions, aggregation, and implementation identity. |
| `reporting/v2.0.0/report-configuration.json` | Field-accuracy interpretation and measurement limitations. |
| `registrations/v2.0.0/benchmark-core.json` | Selects and binds the resource closure; refresh hashes from leaves upward after changes. |

The selected prompts are byte-for-byte identical to their registered provenance
files. ArcGrav binds `Legacy_Content/Bench_Context_ArcGrav_V4.txt`. Its private
`[Check]` pass rechecks independent value and status choices, metadata, conflict
findings, and missing evidence before ordering and validation. It adds no
findings, output fields, or validation conditions and cannot invent source data
to make validation pass. The evaluator requires a single parseable UTF-8
Python-compatible JSON object. Malformed responses receive the registered zero
disposition. Evaluation consumes the response directly, without response repair
or automatic format conversion.

All prompts embed the selected case explicitly; they do not ask a model to read
the Golden's filesystem. Source text, including the instruction-like `note`,
remains data. All five treatments request execution of the embedded source.
The registered `Legacy_Content/Bench_Context_*` files supply independently
verified provenance identities for those treatments.

Hash validity establishes byte identity, not treatment equivalence. The selected
`cases/v1.0.0` JSON supplies the single input for the active registration.

## Developer validation

Developer tests live under `shared/software_testing/`. ARB unit and lifecycle
tests exercise default-file invocation, resource closure, granular mismatch
cases, malformed outputs, duplicate findings, typed values, and shared retained
Golden provenance. Shared runtime tests cover file-input integrity and snapshot
isolation. These checks are implementation evidence, not model performance data.

## Treatment contamination

The registered treatment-content policy permits different bytes only for prompt
artifacts identified by the intact registered treatment set. Missing files, unsafe
paths, changed treatment manifests, cases, code, and Golden authority still fail
their existing integrity checks.

Planning freezes the supplied prompt bytes alongside their actual hash and length
and the registered expected identity. Accepted execution uses these frozen bytes,
including cache validation replays, even if the source files subsequently change.
The canonical plan is retained in the run archive. Contamination is derived from
those identities rather than a mutable flag, score, or completion state.

Contaminated runs use the same Golden, parser, field scorer, aggregation, Results,
and diagnostics as matching runs. `schema_valid` and output `execution.validated`
remain output diagnostics; they do not certify the run. The desktop preserves a
Treatments Contaminated warning. Shared automatic report admission rejects
contaminated evidence and records failed completion instead of presenting a ready
report or offering a manual verification fallback. Diagnostic evidence remains
available for inspection when retained in a supported archive.

## Automatic report completion

After accepted scoring finishes, shared services validate retained evidence and
build the report as one completion operation. A successful supported archive
contains the exact report, canonical evidence, report manifest and completion
record. Report readiness is exposed only after publication succeeds. Validation
or report failure remains explicit and does not change the scored execution into
a successful report. There are no Generate, Verify or Re-verify commands.

Open and Export use the exact retained report bytes. Import validates the
supported archive and opens its saved report without calling a provider, scorer
or generator. Admission requires the supported archive format.
Reports retain each registered prerequisite outcome and concrete failure reasons,
alongside the runner evidence class and measurement limitations.
