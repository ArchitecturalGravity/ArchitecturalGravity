# SWE-rebench materials: rights exception and provenance review

This directory is NOT uniformly licensed by Architectural Gravity under CC BY
4.0 or Apache 2.0. It incorporates material associated with the separate
SWE-rebench July 2026 trajectories dataset.

The upstream dataset states that task text, repository-derived content and code
excerpts remain subject to the original repositories' licenses, while agent
trajectories and model outputs remain subject to the relevant agents' and
providers' terms. The dataset does not relicense third-party content.

Original dataset documentation:
https://huggingface.co/datasets/ibragim-bad/swe_rebench_07_2026_trajectories/blob/main/README.md

## File-level handling

- `trajectories/**`: External dataset content. No Architectural Gravity
  copyright license is granted for externally owned records or outputs. Verify
  applicable upstream license/terms and redistribution permissions.
- `schema.json`: Contains an upstream SWE-rebench schema identifier. Verify
  authorship/source/license before assigning any project license.
- `codex_operational_baseline.csv`: Derived from external trajectories. Confirm
  whether the particular output contains rights-bearing content or is subject
  to upstream terms; do not assume the project can relicense the source data.
- `generate_codex_operational_baseline.ps1`: The project's original script
  portions are under Apache-2.0 (root `LICENSE`), to the extent the project
  has authority to license them.
- `CSV_compatibility_plan.md`: Original project-authored explanatory prose is
  CC BY 4.0 (Research `LICENSE`) to the extent the project controls it.

**Release gate:** Confirm origins, source terms, and permissions of each
third-party dataset component before redistributing or publishing a release.
If that cannot be verified, do not redistribute the affected data files. This
exception does not change the licenses of the project's own authored works.
