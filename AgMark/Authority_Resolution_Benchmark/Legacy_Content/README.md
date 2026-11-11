# Legacy Content

This directory contains historical benchmark artifacts and the Golden implementation explicitly selected by the current benchmark registration. Directory placement alone does not define execution or scoring authority.

`Authority_Resolution_Benchmark.py` and its specification `ARB_Spec.md` are updated for benchmark revision 2.0.0: the standalone Golden reads the registered separate case JSON by default, while `run_orchestration(source_text)` retains its explicit argument. This is an authorized functional revision, not an archival hash repair. The V2 registration binds the selected implementation directly; no previous ARB registration or evaluator is retained as an alternative.

The `Bench_Context_*` files remain preserved provenance for treatment construction. Do not rewrite those archived prompts merely to make current validation pass. Active prompt revisions belong in a new treatment-set version.
