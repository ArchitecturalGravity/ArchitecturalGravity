# Architectural Gravity — licensing and rights map

This repository is distributed under more than one standard license. This file
identifies which license applies to each category of material. It is not an
additional restriction on either license. Refer to the complete license texts,
not this summary, for operative terms.

**Original project:** https://github.com/ArchitecturalGravity/ArchitecturalGravity

**Legal copyright holder:** Architectural Gravity LLC

**Designated attribution:** Architectural Gravity project, with a source link
where reasonably practicable. The legal copyright holder and the designated
attribution party might not be the same person or entity.

## 1. License allocation

| Material | Applicable copyright license | Location of full license |
| --- | --- | --- |
| AgStudio, including original source, configuration, application documentation, and owned media | Apache License 2.0 | `AgStudio/LICENSE` |
| AgMark, including original source, benchmark logic, owned prompt treatments/cases, configuration, application documentation, and owned media | Apache License 2.0 | `AgMark/LICENSE` |
| ArcGrav original specifications, guides, explanatory Markdown, and owned diagrams | Creative Commons Attribution 4.0 International (CC BY 4.0) | `ArcGrav/LICENSE` |
| ArcGrav Guide/Examples, including original `.arc` prompts and associated examples | Apache License 2.0 | `ArcGrav/Guide/Examples/LICENSE` |
| Original research prose, original explanatory graphics, and original research reference/annotation files under Research | CC BY 4.0 | `Research/LICENSE` |
| Original research utility source code, test programs, and scripts (`.py`, `.ps1`, `.bat`, `.sh`, etc.) | Apache License 2.0 | Root `LICENSE` |
| Root `README.md` and original, project-owned images under root `Images/` | CC BY 4.0 | `LICENSE-CC-BY-4.0` |
| Original code snippets expressly marked `SPDX-License-Identifier: Apache-2.0` | Apache License 2.0 | Root `LICENSE` |
| Third-party content or materials whose rights cannot be verified | Their own applicable rights/terms; NOT relicensed here | `THIRD_PARTY_NOTICES.md` and relevant source |

The specific file-level SPDX identifier, an explicitly identified third-party
license, or a directory-specific rights exception takes precedence over a broad
category in this map. The full standard license texts are unmodified.

In particular:

- The original content of `Research/swe_rebench_07_2026_trajectories/trajectories/`
  is **not** covered by the project's CC BY grant. See the local `RIGHTS.md`.
- The provenance of the same directory's `schema.json` and derived baseline
  CSV must be resolved before either is represented as project-owned CC BY
  material. See the local `RIGHTS.md`.
- Original research scripts (including the baseline generator) may be licensed
  as Apache-2.0 only to the extent the project's rights holder controls them.
- Third-party excerpts, citations, logos, dataset records, model outputs,
  dependencies, and other externally sourced materials are not relicensed by
  inclusion in this repository. Relevant exceptions and notices must be
  maintained in `THIRD_PARTY_NOTICES.md`.
- The public-license grants are limited to rights the licensor has authority to
  grant. Contributors retain rights in their own contributions unless a
  separate agreement says otherwise.

## 2. What downstream users must retain

**Apache-2.0 software:** Give recipients the license; indicate modified files;
retain applicable source-form copyright, patent, trademark and attribution
notices; and reproduce applicable attribution from any distributed `NOTICE`
in one of the locations permitted by Apache-2.0 §4(d). The license does not
require Architectural Gravity credit on the application's main screen or in
its new product name. See `NOTICE` and each application-level `NOTICE`.

**CC BY 4.0 documentation/research:** When sharing licensed material, provide
appropriate credit (including the designated Architectural Gravity attribution
supplied with the work), the applicable license information, a source link where
reasonably practicable, and modification indications. The format is flexible
according to CC BY 4.0 §3. No screen-placement or product-name requirement is
added here. See `ATTRIBUTION.md` and the component `ATTRIBUTION.md` files.

The conditions above apply only where the relevant license and applicable law
require them; copyright exceptions, public-domain material, and other rights
are not overridden by this statement.

## 3. Trademarks are separate

**ARCHITECTURAL GRAVITY** is reported by the trademark holder as a federally
registered United States trademark. Its registered owner is identified in
`TRADEMARKS.md`. Neither Apache-2.0 nor CC BY 4.0 conveys
independent trademark rights. Legitimate source attribution and descriptive,
non-confusing references are not prohibited. Do not imply that third-party
forks or adaptations are official releases or endorsed by the mark owner.

See [`TRADEMARKS.md`](TRADEMARKS.md). This paragraph describes trademark
rights; it does not modify the copyright licenses.

## 4. Licensing contact

For permission requests beyond these licenses, including official brand usage,
contact: https://architecturalgravity.com.

## 5. Third-party license and distribution review

Before releasing source or binaries, review `THIRD_PARTY_NOTICES.md`, dependency
licenses, bundled fonts/dictionaries/icons, published datasets, and any
third-party model traces. Binary distributions may need different third-party
notices from this source repository.
