<a id="ag-resource-discovery"></a>
# Resource Discovery

Identifies, resolves, retrieves, and prioritizes the information resources required, including supplied context, conversation history, memory, files, tools, URLs, registries, external sources, etc. It determines what evidence is available and relevant but does not interpret or transform that evidence.

<a id="ag-tool-discovery-capability-enumeration"></a>
## Tool Discovery — Capability Enumeration

Inspect available tools before choosing an execution path.

```text
[Capabilities]:
=> Discover tools for repository reading and writing
=> Record required inputs and write limitations
```

**Rule:** do not assume a capability merely because the task would benefit from it.

<a id="ag-external-knowledge-sources-declared-source-set"></a>
## External Knowledge Sources — Declared Source Set

Name approved external sources and their purpose.

```text
[Sources]:
- Official documentation for current API behavior
- Repository files for local conventions
- User-provided text for requirements
```

<a id="ag-conversation-history-relevant-turn-retrieval"></a>
## Conversation History — Relevant-Turn Retrieval

Retrieve only prior turns that define constraints, decisions, unresolved questions, or reusable artifacts.

```text
[History]:
=> Retrieve prior decisions about authentication behavior
=> Exclude superseded proposals
```

<a id="ag-working-memory-named-active-context"></a>
## Working Memory — Named Active Context

Promote currently relevant facts into a compact symbolic reference.

```text
[WorkingSet]:
- Current task constraints
- Files already inspected
- Open validation failures
```

<a id="ag-session-memory-session-scoped-fact-set"></a>
## Session Memory — Session-Scoped Fact Set

Keep facts that remain valid across multiple steps, while avoiding permanent assumptions.

```text
[SessionFacts]:
- Target branch is main
- Output format is Markdown
- Git history is out of scope
```

<a id="ag-file-and-directory-resolution-resolve-before-read"></a>
## File and Directory Resolution — Resolve Before Read

Convert ambiguous file references into canonical repository-relative paths.

```text
[Patterns]:
- /Guide/Patterns/

[Files]:
=> Resolve all Markdown files under [Patterns]
=> Exclude generated and vendored directories
```

<a id="ag-url-resolution-url-to-resource-mapping"></a>
## URL Resolution — URL-to-Resource Mapping

Determine whether a URL denotes a file, directory, issue, document, or registry entry before choosing a fetch operation.

```text
[TargetURL]:
- https://example.test/repo/tree/main/Patterns

[ResolvedTarget]:
=> Classify [TargetURL]
=> Resolve:
  - Repository
  - Branch
  - Directory path
```

<a id="ag-resource-registries-registry-lookup"></a>
## Resource Registries — Registry Lookup

Use a named registry when resources are addressable by logical identifiers rather than direct paths.

```text
[Registry]:
- Pattern: Guide/Patterns/contextual-boundary.md
- Schema: Schemas/result-v1.json
```

<a id="ag-file-backed-context-indirect-resource-anchor"></a>
## File-Backed Context — Indirect Resource Anchor

Represent a reusable file or external resource through a symbolic anchor that is resolved before its contents are applied.

```text
[ValidationStandard]:
- Guide/Standards/validation.md

Task:
1. Resolve [ValidationStandard]
2. Verify the resolved resource
3. Apply its context
```

<a id="ag-dependency-resolution-resolve-then-bind"></a>
## Dependency Resolution — Resolve-Then-Bind

Separate locating a reusable component from binding the context that the component requires and provides.

```text
[AuditorModule]:
- Resolves: Guide/Auditors/content-auditor.md
- Requires:
  - [PatternSchema]
  - [ValidationRules]
- Provides:
  - [AuditResult]

Task:
1. Resolve [AuditorModule]
2. Verify its dependencies
3. Bind the required context
4. Execute the resolved module
```

<a id="ag-retrieval-rag-query-then-ground"></a>
## Retrieval (RAG) — Query-Then-Ground

Separate retrieval from synthesis and preserve the retrieved evidence.

```text
[Evidence]:
=> Retrieve passages matching [Question]
=> Retain source identifiers and exact locations
=> Exclude low-relevance results
```

<a id="ag-resource-contribution-distinct-contribution-test"></a>
## Resource Contribution — Distinct Contribution Test

Retain a resource only when it contributes unique information, authority, provenance, or an independent verification path used by the workflow.

```text
[ResolvedResources]:
=> For each [Resource]:
  1. Identify its contribution
  2. Compare its contribution with existing context
  3. Confirm a downstream operation uses it
  4. Exclude it when it adds nothing distinct
```

<a id="ag-composite-pattern-discovery-pipeline"></a>
## Composite Pattern — Discovery Pipeline

Prevents reasoning over guessed resources and makes discovery an explicit, inspectable stage.

```text
[Need]:
- Current pattern definitions and target directory contents

[Capabilities]:
=> Discover repository read and write tools

[Resources]:
=> Resolve [Need] into files, URLs, and registries
=> Retrieve current contents only
=> Preserve canonical paths AS [ResolvedResources]

Task:
- Operate exclusively on [ResolvedResources]
```
