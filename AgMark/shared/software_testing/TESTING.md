# AgMark operation-path tests

Run from the AgMark directory using the CI environment and normal `AgMark.*`
package layout:

- `python shared/software_testing/ci.py --all`: all centralized operation-path tests.
- `--head` / `--base` selects tests by Git impact; `--all` bypasses that selection.

## Provider-free lifecycle harness

`self_testing/` contains developer-only support for exercising the shared lifecycle
with synthetic registered inputs, the registered Mock Model process, and a test-only
scorer. Run it from the repository root (the directory containing `AgMark`):

```text
python -m AgMark.shared.software_testing.self_testing
```

The command emits a JSON diagnostic and exits nonzero when any check fails. Its
results are non-authoritative test evidence, not live-model measurements or a
production health check. End-to-end and GUI presentation-isolation tests reuse this
harness. Production code must not import it; the GUI's environment and startup
diagnostics remain independent of developer test support.

## Operational coverage

Tests protect registration/configuration authority, readiness, accepted execution
identity, scoring, process failure/timeout/cancellation, evidence retention and
Windows cleanup, archive integrity and safe import, history without provider
execution, automatic validation and report completion, explicit completion
failures, and byte-identical import/export/reopen. GUI coverage includes keyboard
access, action reachability, disabled controls and meaningful non-color status.
Tests should exercise meaningful execution paths. Static inventories validate
registration completeness and immutability without rerunning referenced tests.

## Collection and evidence

The collector loads TestCase classes only from their defining test module and
ignores imported fixture classes and duplicate aliases. Each operation test runs
in its owning module. The [coverage catalogue](Test_Coverage_Catalogue.md) indexes
current modules; executable test definitions determine coverage.

No live provider or paid benchmark is required locally. Genuine-backend and
wire-audit checks require independently supplied inputs. A local pass does not
establish native Windows execution or real-provider compatibility. Synthetic
fixtures verify controlled contracts, not observed provider behavior.

## Automatic report completion

The application completes source validation and report construction automatically
before publishing a report-ready archive. Generate, Verify and Re-verify are not
application operations. Tests preserve evidence tamper, registration,
synthetic-evidence, secret-safety and generation-isolation checks. Cover explicit
validation/report/publication failures, missing report context, and blocked or
unscored outcomes without a false ready state.

Import validates the supported archive and completion record and opens exact
retained report bytes without running a provider, scorer, generator or verifier.
Cover unsupported-format rejection, unsafe and duplicate entries, missing or
mismatched components, cross-generation bindings, stale GUI snapshots and
byte-identical restart/export, factual prerequisite outcomes and explicit
synthetic-versus-provider evidence classes.

## Independent adapter contracts

Mock Model uses its own registered adapter. Exercise its readiness, execution,
scenarios and normalized observations. A Codex-protocol fixture tests that
protocol; it is not the application mock adapter.

Adapter composition is registration-selected. Preserve common request identity,
terminal status, evidence, cancellation and secret-handling guarantees without
requiring identical controls, discovery or wire protocols across adapters.
Unsupported capability must fail explicitly rather than choose another adapter.
