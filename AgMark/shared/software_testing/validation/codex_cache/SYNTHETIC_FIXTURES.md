# Replay validation contract fixtures

`synthetic_probes.py` contains authored HTTP and WebSocket span trees, not
captured Codex sessions or exporter output.

The modeled runtime versions (including `0.159.0`, `0.166.0`, and future
versions), binary digests, validation UUIDs, request identities, and token
counters are synthetic inputs to the runtime-neutral capability-admission
contract. The selected version and binary must still match exactly. Current
capability/profile identifiers are required; legacy identifiers do not provide
a fallback. Tests check token tuples, warmup behavior, unsupported fields, privacy
allowlists, ambiguity rejection, runtime mismatch, and integrity/tamper handling.
Capability documents for file-loader tests are authored separately from
production admission output.

These tests verify controlled-input behavior, including re-admission of
serialized source bytes. Claims about actual binary output or provider cache
behavior require a separately performed and retained live experiment.
