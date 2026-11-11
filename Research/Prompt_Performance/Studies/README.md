<a id="prompt-performance-studies"></a>
# Prompt Performance — Studies

This directory is an open-ended collection of studies related to prompt performance. Studies can explore different questions, use different approaches, and take whatever form suits the work. This index does not prescribe a study design, methodology, evidence type, measurement, or presentation format.

## Study Index

| Study | Investigation | Evidence status |
| --- | --- | --- |
| [ArcGrav Authority Resolution Benchmark — Prompt Refinement Trials](./ArcGrav_ARB_Trials/README.md) | Adaptive sequence of prompt revisions on one fixed authority-resolution fixture; seven thematic analyses of the observed construction and output discrepancies | 407 completed historical strict exact-response trials (236 passes, 171 failures), 57 tested prompt hashes, preserved [Trial Audit](./ArcGrav_ARB_Trials/Data/Trial_Audit.json) and [Evidence Ledger](./ArcGrav_ARB_Trials/Data/Evidence_Ledger.json); descriptive sequential evidence, not isolated edit effects |
| [Prompt Performance Across Five Authority Resolution Representations](./AgMark_Runs/AgMark_Prompt_Performance.md) | Five retained AgMark runs comparing ArcGrav, common prose, Markdown, XML and YAML on one authority-resolution case; examines field accuracy, exact-result agreement, token consumption and timing proxies | 250 scored observations (5 runs × 5 treatments × 10 repetitions) under `gpt-5.6-luna` with low reasoning; original reports and `.agmark` archives retained, with an inline score-reproduction example in the study (no standalone script or derived JSON committed); descriptive single-case evidence, not an isolated syntax effect |

## Scope and Organization

Entries point to the studies themselves. A study can be presented as a single document, a directory of materials, or another suitable arrangement. Its scope, contents, and stage of development are defined by the work, not by this index. Additional studies can be added as the collection grows.

## Relationship to Research

This directory holds studies that can inform the broader [Prompt Performance research](../README.md). The parent research develops and revises concepts and interpretations drawn from such work. Studies may also stand on their own; inclusion in this catalog does not require a particular conclusion or make separate entries directly comparable.
