# Bundled US English Hunspell dictionary

AgStudio loads this UTF-8 `en_US.aff` / `en_US.dic` pair explicitly. It does
not use a system dictionary or cHunspell's bundled ISO-8859-1 dictionary.
Keep the pair together. The 71 AgStudio technical terms remain separate
application data and are added to Hunspell at runtime, without modifying
these upstream files.

## Provenance and redistribution

Copied unchanged from the official LibreOffice dictionaries repository at
commit [4f1df64b2e8e14751aa7c2205d170ca016071315](https://github.com/LibreOffice/dictionaries/commit/4f1df64b2e8e14751aa7c2205d170ca016071315)
(2026-10-27), retrieved 2026-11-06:

- [en_US.aff](https://github.com/LibreOffice/dictionaries/blob/4f1df64b2e8e14751aa7c2205d170ca016071315/en/en_US.aff)
- [en_US.dic](https://github.com/LibreOffice/dictionaries/blob/4f1df64b2e8e14751aa7c2205d170ca016071315/en/en_US.dic)
- [README_en_US.txt](https://github.com/LibreOffice/dictionaries/blob/4f1df64b2e8e14751aa7c2205d170ca016071315/en/README_en_US.txt)

The upstream README identifies the dictionary as SCOWL-derived, version
2020.12.07, normal size 60. LibreOffice subsequently updated the affix file;
its retained header marks the 2024 apostrophe-handling change. The dictionary
declares and contains 49,568 entries.

`README_en_US.txt` is the complete upstream copyright, permission,
disclaimer, source and credit notice. It includes the SCOWL, WordNet,
VarCon and Ispell-related terms. Distribute that file with this dictionary,
retain all notices, and mark any future modifications. Do not label the
dictionary simply as MIT or use the wrapper's license as its license.

SHA-256:
- `en_US.aff`: `e746c882dd6f303c2c46e7452804b9201115a6942cfeb15f18f8edf774d2e24e`
- `en_US.dic`: `f0b1a234bd178bdd01875b2a392a9647f888b8fe879f79c52aae62c2759b3647`
- `README_en_US.txt`: `168b4c01cb841f766a72f310b065c04d09cff46376c37a81d799593ce751c371`

All upstream data and license files are also listed in `SHA256SUMS`.
Their Git blob identities were checked against the upstream connector
responses during import.

## Native engine and wrapper

The application integration targets [cHunspell 2.0.5](https://pypi.org/project/chunspell/2.0.5/),
a native Cython wrapper distributed as `chunspell` and imported as
`hunspell`. Its published documentation identifies Hunspell 1.7.2 as the
bundled engine. Do not install the competing `hunspell` or `cyhunspell`
distributions into the same environment; they use the same import name.
No pyspellchecker or Spylls fallback is used.

The wrapper is MIT-licensed, while native Hunspell carries
MPL-1.1 / GPL-2.0-or-later / LGPL-2.1-or-later alternatives and retained
MySpell BSD notices. Full notices are preserved under `licenses/`:

- `chunspell_LICENSE.txt` and `HUNSPELL_LICENSE_LESSER.txt`:
  [cHunspell source snapshot f33bd90b425451e6165b0c6f60f3b9d437eeb6cf](https://github.com/cdhigh/chunspell/tree/f33bd90b425451e6165b0c6f60f3b9d437eeb6cf).
- `HUNSPELL_COPYING`, `HUNSPELL_COPYING.LESSER`,
  `HUNSPELL_COPYING.MPL`, `license.hunspell`, and `license.myspell`:
  [Hunspell 1.7.2, commit 2969be996acad84b91ab3875b1816636fe61a40e](https://github.com/hunspell/hunspell/tree/2969be996acad84b91ab3875b1816636fe61a40e).

These are unmodified upstream notices, not a claim that adding license text
alone completes binary-distribution compliance. Before distributing a frozen
app, verify the exact wheel's bundled library/version, preserve all its
notices, and satisfy the chosen license's source-availability and, where
applicable, relinking requirements. The wrapper's Windows library build
instructions contain older version references, so do not infer exact binary
provenance solely from its current README.

## Packaging constraints and release checks

- Published 2.0.5 wheels cover CPython 3.9-3.15 on Windows x86/x64 and Linux
  x86_64/ARM64, with separate glibc and musl builds. No Windows ARM64 wheel
  was listed when inspected. Use a wheel matching the supported interpreter
  and target platform; wheel availability is not a runtime test.
- Linux wheel tags require glibc 2.27+ on x86_64 or 2.26+ on ARM64, or musl
  1.2+. A missing compatible wheel can trigger a compiler/toolchain build;
  an ordinary source installation is not a dependency-free fallback.
- A compatible wheel bundles Hunspell, so a separate system Hunspell install
  should not be needed. Frozen builds must collect the extension, bundled
  native libraries, this dictionary pair, notices and checksums. Test each
  supported Windows/Linux target independently, including non-ASCII paths.
- Pass an absolute application dictionary directory and UTF-8 path encoding
  explicitly. The wrapper otherwise consults `HUNSPELL_DATA` and
  `HUNSPELL_PATH_ENCODING`. Word encoding follows `SET UTF-8` in this pair.
- Test native lookup, ranked suggestions, case and apostrophe handling,
  all 71 technical terms, and missing-library/dictionary errors. Do not
  treat fake-backend tests as native integration verification.
