# Registration-selected runner adapters

AgMark's adapter boundary is open-ended. A validated runner registration selects
its implementation and declares its identity, capabilities, controls, limitations,
response retention, telemetry and secret handling. Shared application and runtime
code consume the generic runner invocation contract, not a closed list of named
runners and not a universal provider protocol.

## Distinct implementation authority

The Mock Model has a dedicated adapter boundary, separate from Codex CLI.
Selecting Mock Model must not instantiate `CodexCliRunner`, require a Codex
installation, discover Codex models, or fall back to Codex after a mock readiness
or execution failure. Mock-specific scenario setup and observations belong to
the registered mock implementation. Synthetic conformance remains diagnostic and
does not become independent model-performance evidence.

Codex CLI's native protocol, discovery, session capture and provider evidence
remain owned by the Codex adapter. A protocol fixture that imitates Codex for a
Codex integration test is not the production Mock Model adapter and must not
select the application's mock execution path.

Other adapters may implement CLI, HTTP, in-process or other registered execution
mechanisms. A shared process-launching utility or normalized observation type
is reusable infrastructure, not permission to reuse another adapter's protocol,
identity or provider assumptions.

## Common semantics, different capabilities

All adapters preserve the runner invocation contract's request identity,
accepted execution boundary, terminal statuses, exact response-byte provenance,
secret handling and explicit unsupported-control behavior. They do not have to
support identical controls, model catalogues, authentication, transports, tool
policies, retry mechanisms or wire protocols.

Readiness and request construction must use the selected registration's declared
capabilities. A control unsupported by one adapter must not be silently mapped to
a similarly named control in another adapter. Missing required capability or
implementation is an explicit unsupported or unavailable outcome, never a reason
to choose Codex or another fallback.

## Extension and regression checks

Adding an adapter must not require an adapter-name switch in benchmark logic or
a fake implementation of Codex discovery/session APIs. Registration-selected
composition and the generic contract remain the extension boundary.

Tests should exercise each concrete adapter's supported behavior and verify the
shared invariants through the normalized boundary. Mock tests should assert
independent selection and absence of Codex dependencies. Different protocols or
controls are expected when registered; cross-adapter wire parity is not a shared
contract requirement.
