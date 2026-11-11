# Synthetic session and cache contract tests

- `synthetic_cache_fixtures.py` authors raw rollout bytes and stdout directly,
  independently of the production extractor. Root/guardian labels distinguish
  deterministic input identities, not observed helper execution.
- `test_cache_evidence.py` verifies production extraction, retained-byte
  reconstruction and inferred namespace policy against those inputs.
- `test_session_parity.py` exercises 422 generated cases with independent literal
  cumulative counter expectations, invalid/subset counter handling, completeness,
  retained source hashes, extraction-version behavior, input immutability, JSON
  serialization/reconstruction, and retained-byte/counter/thread tamper rejection.

## Evidence boundaries

Synthetic tests establish controlled-input contract conformance. Actual provider
observations, native/WSL requests and observed Guardian behavior require genuine
backend evidence. `test_cache_wire.py` is the opt-in real-binary request audit.
Focused tool, timing, token, cache-policy and projection tests enforce the
corresponding production contracts without asserting provider cache efficiency.
