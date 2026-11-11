<a id="ag-process-orchestration"></a>
# Process Orchestration

Coordinates execution structure by decomposing work, assigning responsibilities, ordering dependencies, routing operations, managing parallel or iterative work, limiting retries, handling recovery, defining termination conditions, etc. It determines when and in what order operations occur, not their internal semantics.

<a id="ag-workflow-management-phase-oriented-workflow"></a>
## Workflow Management — Phase-Oriented Workflow

Organize work into named phases with explicit entry and exit conditions.

```text
[Workflow]:
1. Discover
2. Derive
3. Render
4. Validate
5. Publish
```

<a id="ag-task-decomposition-atomic-task-split"></a>
## Task Decomposition — Atomic Task Split

Decompose goals into independently verifiable tasks.

```text
[Tasks]:
- Resolve current source files
- Extract reusable mechanisms
- Classify patterns
- Create category files
- Verify coverage
```

<a id="ag-recursive-traversal-hierarchy-walk"></a>
## Recursive Traversal — Hierarchy Walk

Traverse nested resources while preserving parent-child context.

```text
[Files]:
=> Recursively traverse /Patterns/
=> Include Markdown files
=> Exclude generated directories
```

<a id="ag-worklists-and-queues-explicit-pending-set"></a>
## Worklists and Queues — Explicit Pending Set

Maintain a visible queue for scalable or interruptible work.

```text
[Queue]:
- unresolved resources
- unclassified patterns
- unrendered categories
```

<a id="ag-dependency-ordering-topological-work-order"></a>
## Dependency Ordering — Topological Work Order

Order tasks from prerequisites to dependents.

```text
[Order]:
=> Build dependency graph for [Tasks]
=> Execute ready nodes first
```

<a id="ag-routing-and-dispatch-capability-based-routing"></a>
## Routing and Dispatch — Capability-Based Routing

Send work to the tool or reasoning path that satisfies its requirements.

```text
[Route]:
- Repository reads:
  => File retrieval
- Repository writes:
  => Create or update operation
- Semantic grouping:
  => Model reasoning
```

<a id="ag-conditional-execution-branch-on-evidence"></a>
## Conditional Execution — Branch on Evidence

State conditions and actions explicitly.

```text
Task:
- IF target file exists: update it
- ELSE: create it
```

<a id="ag-conditional-dispatch-condition-based-selection"></a>
## Conditional Dispatch — Condition-Based Selection

Select an operation by mapping conditions directly to their corresponding actions.

```text
[Switch]:
- Condition 1:
  => Do thing 1
- Condition 2:
  => Do thing 2
- Condition 3:
  => Do thing 3
```

Use when execution should be routed according to mutually exclusive or otherwise explicitly defined conditions.

When selection precedence matters, use an ordered list:

```text
[Switch]:
1. Condition 1:
  => Do thing 1
2. Condition 2:
  => Do thing 2
3. Condition 3:
  => Do thing 3
```

When utilizing symbolic references:

```text
[Switch]:
- [Value] is positive:
  => Run [Positive]
- [Value] is neutral:
  => Output "Value was Neutral"
- [Value] is negative:
  => Run [Negative]
```

<a id="ag-sequential-execution-dependency-sequence"></a>
## Sequential Execution — Dependency Sequence

Use ordered lists when each step depends on the prior result.

```text
Task:
1. Resolve [Files]
2. Parse [Files] AS [Parsed]
3. Classify [Parsed] AS [Derived]
4. Render [Derived]
```

<a id="ag-parallel-execution-independent-work-set"></a>
## Parallel Execution — Independent Work Set

Run independent tasks concurrently while isolating their outputs.

```text
[Parallel]:
- Render contextual-boundary.md
- Render transformation.md
- Render examination.md
```

<a id="ag-iteration-bounded-refinement-loop"></a>
## Iteration — Bounded Refinement Loop

Repeat an operation with an explicit bound and progress condition.

```text
[Refinement]:
=> Repeat up to 3 times:
  => Validate [Draft]
  => Correct failed assertions only
  => Stop when all assertions pass
```

<a id="ag-retry-and-recovery-bounded-retry"></a>
## Retry and Recovery — Bounded Retry

Retry only transient or independent failures and preserve completed work.

```text
[Recovery]:
- Retry a failed write once after refreshing target state
- Do not replay successful writes
- Record persistent failures
```

<a id="ag-replay-plans-deterministic-re-execution"></a>
## Replay Plans — Deterministic Re-execution

Record sufficient inputs and ordering to reproduce a workflow.

```text
[ReplayPlan]:
- Source paths
- Category taxonomy
- Transformation chain
- Output paths
- Validation assertions
```

<a id="ag-termination-conditions-explicit-stop-contract"></a>
## Termination Conditions — Explicit Stop Contract

Define completion and non-progress stopping rules.

```text
[Terminate]:
- Stop successfully when all postconditions pass
- Stop with partial result when no ready work remains
- Never loop without changed state
```

<a id="ag-maintenance-convergence-minimal-idempotent-update"></a>
## Maintenance Convergence — Minimal Idempotent Update

Apply only the changes required to reach the desired state and verify that repeating the same operation produces no additional changes.

```text
[Maintenance]:
1. Inspect the current artifact
2. Identify the smallest required changes
3. Preserve valid existing content
4. Apply changes deterministically
5. Verify the result
6. Repeat against the updated result
7. Confirm no additional changes are produced
```

<a id="ag-workflow-extension-replaceable-strategy-pipeline"></a>
## Workflow Extension — Replaceable Strategy Pipeline

Route workflow responsibilities through stable stages whose implementations may be replaced without changing unrelated stages.

```text
[Workflow]:
1. Apply [DiscoveryStrategy]
2. Apply [TransformationStrategy]
3. Apply [ValidationStrategy]
4. Apply [PublicationStrategy]
```

<a id="ag-composite-pattern-orchestrated-work-graph"></a>
## Composite Pattern — Orchestrated Work Graph

Turns a broad task into a visible, recoverable execution system rather than an implicit chain of guesses.

```text
[Plan]:
=> Decompose [Goal]
=> Build dependencies
=> Dispatch independent ready tasks in parallel
=> Execute dependent tasks sequentially
=> Retry bounded transient failures
=> Validate after each phase
=> Terminate on [Postconditions] or no-progress condition
```
