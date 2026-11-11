# Implementation checklist (review before public release)

This overlay was designed for the structure of the GitHub repository
`ArchitecturalGravity/ArchitecturalGravity` on November 11, 2026. It is a
proposal for attorney/owner review, not a determination that the repo's entire
contents have cleared third-party-rights review.

## Required owner inputs

- [ ] Replace every `[INSERT ...]` and `[CORRECT ...]` placeholder with the
      verified legal copyright holder, copyright year/range, creator/contributor credit, registered
      trademark owner, and contact. The copyright owner and trademark owner
      may be different entities.
- [ ] Verify the federal trademark registration, exact mark, owner, covered
      goods/services and any assignment record; enter number in TRADEMARKS or
      delete the optional number line.
- [ ] Confirm contributor ownership or permission to license every original
      part; confirm all included third-party rights before publishing.
- [ ] Verify upstream SWE-rebench terms and the legality of redistributing
      the actual `trajectories/**` files; remove any uncleared records.
- [ ] Review PySide6/Qt, Hunspell dictionaries and bundled image/icon assets
      before distributing packaged desktop binaries.
- [ ] Keep the full standard Apache and CC BY license texts intact.
- [ ] Publish a concise link to `LICENSING.md` and `TRADEMARKS.md` in root
      README, and links to the applicable license in each subproject README.
- [ ] Add SPDX markers to original code and documentation as files are touched;
      do not erase existing contributor or third-party notices.
- [ ] Have U.S. IP counsel review trademark policy and actual legal ownership.

## Proposed addition to the root README.md

Paste a `## Licensing and attribution` section near the end of the existing
root README (do not replace the current README):

> This is a multi-license project. Original software and executable examples
> are generally under Apache License 2.0; original specifications, research,
> and illustrations are generally under CC BY 4.0, with documented exceptions
> for third-party materials. **Preserve the attribution and license notices
> required by the applicable license.** See [LICENSING.md](LICENSING.md),
> [ATTRIBUTION.md](ATTRIBUTION.md), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
>
> ARCHITECTURAL GRAVITY is a federally registered U.S. trademark of
> [EXACT TRADEMARK OWNER]. Redistribution rights do not confer separate
> trademark branding rights. See [TRADEMARKS.md](TRADEMARKS.md).

## Subproject README links

- `AgStudio/README.md`: add `License: Apache-2.0; preserve NOTICE; see
  ../LICENSING.md and ../TRADEMARKS.md.`
- `AgMark/README.md`: add `License: Apache-2.0; preserve NOTICE; see
  ../LICENSING.md and ../TRADEMARKS.md.`
- `ArcGrav/README.md`: add `Original specification and guide: CC BY 4.0;
  Guide/Examples: Apache-2.0; see ../LICENSING.md, ATTRIBUTION.md,
  and ../TRADEMARKS.md.`
- `Research/README.md`: add `Original research documents: CC BY 4.0;
  original utilities: Apache-2.0; external data exceptions apply; see
  ../LICENSING.md, ATTRIBUTION.md, and ../THIRD_PARTY_NOTICES.md.`

## Enforceable requirements vs policy requests

- Apache-2.0 redistribution: retain notices, pass the license, identify
  modified files, and carry forward any applicable NOTICE attribution in one
  of Apache-2.0 section 4(d)'s permitted locations. It is not a requirement
  that every fork keep the project name as its brand or show it on-screen.
- CC BY 4.0 redistribution: give reasonable credit, indicate changes,
  identify the license and provide source link where reasonably practicable.
  No fixed placement or exact wording is imposed, and CC BY includes a
  request-to-remove-credit clause.
- Trademark protection: independently constrains confusing uses of the mark;
  does not prohibit lawful factual attribution or impose new restrictions on
  copyright permissions. The registered owner needs to enforce the mark in
  light of its registered classes and actual use.
