# Third-party material and redistribution review

**Status:** Pending provenance and distribution audit. This file is a tracking
record, not a representation that every third-party license has been cleared.

Architectural Gravity's Apache-2.0 and CC BY 4.0 grants cover only rights that
the relevant licensors control. Existing third-party copyright licenses and
provider terms are not changed by inclusion in the repository.

## Identified or probable third-party materials

| Material | Evidence from repository | Action before distribution |
| --- | --- | --- |
| SWE-rebench July 2026 dataset | `Research/swe_rebench_07_2026_trajectories/trajectories/`; upstream dataset says third-party source and agent/provider rights remain applicable | Obtain/review source and redistribution rights; maintain dataset-specific notices or remove affected data from distribution |
| SWE-rebench schema/derived CSV | `Research/swe_rebench_07_2026_trajectories/schema.json`, `codex_operational_baseline.csv` | Review provenance and derivative-content obligations; see local `RIGHTS.md` |
| PySide6/Qt runtime | Declared by `AgMark/gui/requirements.txt` and `AgStudio/gui/requirements.txt` | At binary packaging time review actual Qt/PySide6 licenses, bundled DLLs/plugins, corresponding notices and relinking/source obligations if applicable |
| Hunspell dictionary/backend | AgStudio README describes a packaged spelling backend and dictionary | Identify every redistributed library/dictionary, the underlying license, and required notices |
| External logos, icons, fonts, screenshots or quotations | Asset locations include root and application `Images/` and `AgStudio/gui/icons/` | Identify original creator/license; verify the project owns or has redistribution/adaptation permission |
| Embedded provider outputs, agent traces or third-party benchmark cases | Research and benchmark datasets may contain imported material | Verify source, provider/platform terms and privacy constraints for each bundled artifact |

The presence of a dependency in `requirements.txt` does not, by itself, mean
its binary is vendored into this source repository. Obligations for a release
must be evaluated on what the distribution actually contains.

## Maintain this record

For each included third-party component, record its name, version, origin URL,
exact upstream license, files included, required notices, source offer/relink
requirements if any, and distribution(s) in which it is bundled. Include the
actual third-party license text wherever its terms require it.

Never present externally owned content as exclusively copyrighted by
Architectural Gravity. Do not replace third-party notices with the project's
NOTICE attribution.
