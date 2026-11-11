# Architectural Gravity Research — Manuscript Style Guide

This guide establishes a consistent manuscript style: direct explanation, explicit construct boundaries, precise measurements, and restrained presentation. Preserve technical claims, source links, and stable anchors when editing.

## Editorial principles

1. **Standalone comprehension.** Give every central construct a plain-language description before its technical definition. Readers should not need a separate paper merely to understand the opening definition.
2. **One technical owner.** A construct's owning paper specifies its canonical formal definition and measurement procedure. Importing papers give a short independent description and link the owner instead of rebuilding the entire argument.
3. **One evidence boundary.** Distinguish observed findings from hypotheses in a concise `Scope and Evidence Status` section; do not repeat cautions throughout the abstract, discussion, and conclusion.
4. **One argument per section.** Progress from motivation and definition to formalization, consequences, tests, and conclusion. Consolidate repeated prediction, implications, and conclusion summaries.
5. **Scholarly restraint.** Prefer precise claims over rhetorical intensifiers. Reserve strong emphasis for key definitions and primary results.
6. **Format serves meaning.** Use tables for comparison, math for formal relationships, examples for interpretation, and prose for argument. Preserve information and stable anchor IDs.

## Front matter and abstracts

Every research manuscript starts with its existing title, followed by `## Abstract` and then `## Introduction`. The `Introduction` must be the first section after the abstract. Use the introduction to establish the problem, motivation, research question or purpose, and contribution in language accessible to readers outside the research program. Orient the reader to the argument without repeating the abstract or preempting the detailed definitions, methods, and results that follow.

Use a continuous paragraph or two for the abstract; do not place a large list of statistics or a separate thesis pull quote inside it.

- Theoretical and methodological papers: roughly 100–160 words, establishing problem, contribution, approach, and central prediction or boundary.
- Empirical papers: roughly 140–200 words, stating data/design, central quantitative result, interpretation, and the decisive measurement boundary.
- Paper version, author, and date metadata may be supplied in publication front matter; do not invent them to fill a template.

## Composition: theoretical and methodological papers

Follow this *role progression*, combining or retaining numbered sections when appropriate:

1. `Introduction` — problem, motivation, purpose, and principal contribution.
2. `Role Within the Research Program` — short positioning and conceptual ownership.
3. `Construct Definition and Boundaries` — plain-language explanation, precise definition, what the construct excludes.
4. Theory/mechanism/representation — substantive account and worked examples.
5. Hypotheses, operationalization, and quantification — predictions and measurable definitions.
6. Experimental program / interactions — design and confounds when relevant.
7. `Scope and Evidence Status` — one compact paragraph about established and prospective evidence.
8. `Conclusion` — one brief synthesis, avoiding a second abstract.
9. `Related Papers` — internal conceptual references.
10. `References` — external scholarship.

Use meaningful existing headings when they already serve these roles; do not create empty placeholder sections or renumber purely for uniformity.

## Composition: empirical papers

Prefer `Abstract → Introduction → Research Question / Scope → Dataset and Methods → Measurements → Results → Interpretation → Scope and Evidence Status → Conclusion → Data and Reproducibility → Related Papers → References`. Keep principal analyses in the body; move extended sensitivity tables and incidental background to appendices as appropriate.

Software READMEs, dataset manifests, experiment stimuli, and directory indexes may retain documentation-oriented layouts. The associated research papers follow the manuscript conventions.

## Central construct definition pattern

At first substantive introduction, include:

- **In plain language:** One independent sentence understandable without other project-specific terminology.
- **Technical definition:** The precise construct, including scope and units where applicable.
- **Boundary:** What it is not; distinguish measured input, inferred mechanisms, and observed outcomes.
- **Quantification:** An operational procedure or link to the owning definition.

One paragraph may convey several of these parts; never manufacture a formula or section merely to satisfy formatting.

## Visual, notation, and copy style

Use sentence-case headings, consistent term capitalization, and a single notation for the same quantity within a paper. Display multiline math in fenced `math` blocks, but combine connected equations rather than fencing every minor relation. Label substantial figures and tables; state units and denominators. Prefer paragraphs over repeated pull quotes. Use bold for first definitions and primary findings, not routine caveats or every row in a table. Preserve named HTML anchor IDs because the research index relies on them. Do not change quoted experimental stimuli or reported participant/model responses for style alone.

## Citation and bibliography conventions

**External scholarly evidence:** Use author–year in prose, e.g. `Author et al. (Year)` or `(Author et al., Year)`, with a Markdown link at the first substantive citation if helpful. Conclude every manuscript with `## References`, alphabetized by first author where known, then title. Format entries consistently: `Author(s). (Year). *Title*. Venue or publisher, when established. Canonical URL/DOI.` Do not invent bibliographic metadata: if a source lacks verified author/venue information in the existing corpus, retain its precise linked title and publication year until curated.

**Internal literature:** Link canonical papers by relative path in the body. End with `## Related Papers` when needed; use one Markdown bullet per related paper, with descriptive linked text, rather than semicolon-separated or standalone prose links. Do not count cross-links within the research program as independent evidence.

**Primary evidence and tooling:** Put datasets, prompt transcripts, scripts, hashes, and benchmark extraction instructions under `## Data and Reproducibility` in empirical papers. Public incidents, platform rate cards, and public usage anecdotes belong to a labeled `Other Sources` section when cited rather than being presented as peer-reviewed studies.

References should match actual cited material; remove duplicate entries, prefer stable publication URLs, and preserve existing external links during migration. Run [validate_references.py](./validate_references.py) to check the citation catalog and reference coverage. Never convert a descriptive title into a guessed author–year citation.

## Review checklist

- [ ] Abstract uses the common pattern and does not duplicate Methods/Results.
- [ ] `## Introduction` follows the abstract and establishes motivation, purpose, and contribution.
- [ ] Research role and boundaries are clear.
- [ ] Every new central term has a standalone explanation and one canonical owner.
- [ ] Direct findings, proposed experiments, and methodological analogies are distinguishable.
- [ ] Section progression is coherent without duplicative conclusions.
- [ ] Bibliography and internal links use the common conventions.
- [ ] Equation notation, table units, and quoted observations remain unchanged.
- [ ] Existing permanent anchors and repository relative paths still resolve.
