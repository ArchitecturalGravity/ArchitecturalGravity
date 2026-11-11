<a id="ag-contextual-boundary"></a>
# Contextual Boundary

Defines the operating contract: scope, objectives, assumptions, audience, authority, permissions, exclusions, verifiable success criteria, etc. It establishes what the model is expected and allowed to address but does not enforce those conditions during execution.

<a id="ag-scope-enumerated-scope-fence"></a>
## Scope — Enumerated Scope Fence

The general operating scope that defines the *initial* context to work within by filtering infinite contextual possibility to a finite, *bounded* focus before any other instructions are defined.

```text
Scope:
- src/auth/*
- tests/auth/*
- Exclude deployment configuration
```

**Invariant:** work outside `Scope` is not performed unless the prompt explicitly expands it.

<a id="ag-authority-and-precedence-ranked-instruction-sources"></a>
## Authority and Precedence — Ranked Instruction Sources

Resolve competing instructions with a priority list.

```text
[Authority]:
P0. Safety and repository policy
P1. Explicit task constraints
P2. Local conventions
P3. General best practices
```

**Rule:** lower-priority guidance may refine, but never override, a higher-priority instruction.

<a id="ag-objectives-named-objective-set"></a>
## Objectives — Named Objective Set

Separate desired outcomes from execution steps so that alternative plans can still be evaluated against the same goal.

```text
[Objectives]:
- Preserve public behavior
- Remove duplicated validation
- Improve failure diagnostics
```

<a id="ag-audience-and-consumers-consumer-specific-output-boundary"></a>
## Audience and Consumers — Consumer-Specific Output Boundary

Name the intended consumer and the decisions they must make from the output.

```text
[Audience]:
- Maintainers reviewing a pull request
- Decisions:
  - Need risks
  - Changed behavior
  - Test evidence
```

<a id="ag-assumptions-visible-assumption-ledger"></a>
## Assumptions — Visible Assumption Ledger

State assumptions that materially affect the answer. Keep them revisable and distinguish them from known facts.

```text
[Assumptions]:
- Input files are UTF-8
- Missing fields are invalid, not optional
```

<a id="ag-success-criteria-verifiable-completion-contract"></a>
## Success Criteria — Verifiable Completion Contract

Define observable conditions rather than subjective quality claims.

```text
[Success]:
- Existing tests pass
- New invalid-input cases are covered
- No public API signature changes
```

<a id="ag-composite-pattern-boundary-contract"></a>
## Composite Pattern — Boundary Contract

Reduces implicit inference by making permission, purpose, and completion independently addressable.

```text
[Target]:
- Package manifests
- Lockfiles
- Migration tests

[Objectives]:
- Complete the migration without changing runtime behavior

[Assumptions]:
- The target version is already approved

[Success]:
- Dependency resolves
- Tests pass
- No unrelated edits

[Authority]:
P0. Repository instructions
P1. [Target] and [Success]
P2. Existing style
```
