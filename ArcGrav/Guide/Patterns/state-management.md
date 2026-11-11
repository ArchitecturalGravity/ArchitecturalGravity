<a id="ag-state-management"></a>
# State Management

Tracks named values, decisions, dependencies, progress, checkpoints, blockers, temporary context, etc. that may change during execution. It defines state ownership, lifecycle, validity, transitions, invalidation, cleanup, etc. without determining the workflow sequence itself.

<a id="ag-session-state-session-bounded-configuration"></a>
## Session State — Session-Bounded Configuration

Store settings that apply throughout the task but should not be treated as permanent facts.

```text
[SessionState]:
- Repository: ArcGrav
- Branch: main
- Target: Guide/Patterns
```

<a id="ag-conversation-state-turn-state-summary"></a>
## Conversation State — Turn-State Summary

Compress the current interaction into decisions, open items, and active constraints.

```text
[ConversationState]:
- Decided: One file per category
- Active Constraint: ignore git history
- Open: Populate target directory
```

<a id="ag-working-variables-named-mutable-values"></a>
## Working Variables — Named Mutable Values

Use symbolic references for values that change during execution.

```text
[PendingFiles]:
- contextual-boundary.md
- resolution.md
```

**Rule:** update the named value rather than creating competing aliases.

<a id="ag-mutable-state-explicit-transition"></a>
## Mutable State — Explicit Transition

Describe state changes as operations with before-and-after conditions.

```text
[Remaining]:
=> Subtract [Completed] from [Requested]
```

<a id="ag-dependency-state-readiness-map"></a>
## Dependency State — Readiness Map

Track which tasks are blocked, ready, running, or complete.

```text
[DependencyState]:
- Resolve source files: "complete"
- Derive patterns: "complete"
- Render category files: "ready"
- Publish index: "blocked by file creation"
```

<a id="ag-state-lifecycle-initialize-use-retire"></a>
## State Lifecycle — Initialize, Use, Retire

Give each state object a clear lifecycle.

```text
[Lifecycle]:
1. Initialize [Derived]
2. Append categorized patterns
3. Publish files
4. Clear temporary extraction notes
```

<a id="ag-checkpoints-recoverable-snapshot"></a>
## Checkpoints — Recoverable Snapshot

Record a compact snapshot after a meaningful stage.

```text
[Checkpoint]:
- Resources resolved
- Category mapping complete
- Writes not yet started
```

<a id="ag-cleanup-and-reset-behavior-explicit-disposal"></a>
## Cleanup and Reset Behavior — Explicit Disposal

Define what must be removed or reset after completion or failure.

```text
[Cleanup]:
- Remove temporary aliases
- Do not delete source files
- Preserve published outputs and provenance
```

<a id="ag-composite-pattern-stateful-work-ledger"></a>
## Composite Pattern — Stateful Work Ledger

Avoids hidden state, accidental rework, stale assumptions, and ambiguous recovery behavior.

```text
[State]:
- `phase`: "discover" 
- `completed`: []
- `pending`: ["derive", "render", "publish"]
- `blockers`: []

Task:
1. Execute the next ready item from [State].pending
2. Append it to [State].completed
3. Update `phase` and `blockers`
4. Create [Checkpoint] after each publication stage
```
