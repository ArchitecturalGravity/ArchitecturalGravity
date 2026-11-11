# AgMark Individual Run Report

## Run Details

- **Benchmark:** arcgrav.authority-resolution.benchmark.core
- **Comparison Track:** arcgrav.authority-resolution.field-accuracy
- **Generation:** generation-e9e3e53a556a560c3cb245c0fa8ea477b4b415a93fa16fa78b779001e84347b0
- **Report Generated:** 2026-11-05T17:45:45.809294Z
- **Model:** gpt-5.6-luna · **Reasoning Level:** low
- **Report Status:** complete
- **Coverage:** 5 treatments, 1 cases, 10 distinct repetition identifiers. 50 of 50 planned observations completed; 50 scored. 0 failed, 0 missing, 0 excluded, 0 non-scorable.
- **Scope:** Original accepted run only. Post-treatment validation evidence is retained separately and excluded from these results.

## Results Tables

### Treatment Results per Observation in Execution Order

All 50 planned observations appear below. Execution order is the earliest recorded attempt start in UTC, not completion order or repetition number. Equal timestamps share a rank marked tied. Observations without complete attempt-start evidence appear last with no rank; ranks otherwise cover recorded starts only.

Token and tool counts are per-observation totals, including failed attempts and retries. Timing values are in **milliseconds**. Cache Read Fraction is displayed as a percentage. **Proxy** marks duration-derived estimates. **Unavailable** is not zero; **partial** marks incomplete measurement coverage. Observation ID prefixes are at least 12 characters where possible, extended as needed to remain unique; full IDs are in supporting data.

| Treatment | Accuracy | Input Tokens | Uncached Input | Reasoning Output Tokens | Output Tokens | Total Tokens | Cache Read Fraction | Average Inference Duration | Average TTFT | Average TBT | Average Direct TTFT | Average Direct TBT | Tool Calls | Distinct Tool Calls | Failed Tool Calls | Execution Order | Observation ID Prefix | Repetition | Attempt Start UTC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 185 | 602 | 20,713 | 50.9174% | 10,370.00 proxy | 3,227.00 proxy | 11.885191 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 1 | 5ff154a710bb | 1 | 2026-11-05T17:30:19.169571Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 149 | 566 | 21,694 | 48.4665% | 11,799.00 proxy | 2,624.00 proxy | 16.238938 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 2 | 6c16de6fb365 | 1 | 2026-11-05T17:30:35.577816Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 186 | 603 | 21,119 | 49.9123% | 10,656.00 proxy | 3,243.00 proxy | 12.313953 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 3 | 81605b323a75 | 1 | 2026-11-05T17:30:51.164830Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 220 | 637 | 20,669 | 51.1182% | 12,155.00 proxy | 3,895.00 proxy | 12.987421 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 4 | 3eadbfef768c | 1 | 2026-11-05T17:31:07.841720Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 279 | 696 | 16,894 | 63.2177% | 12,031.00 proxy | 4,824.00 proxy | 10.369784 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 5 | 07fb076a4c1d | 1 | 2026-11-05T17:31:25.443357Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 146 | 563 | 20,603 | 51.0978% | 11,067.00 proxy | 2,504.00 proxy | 15.236655 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 6 | 7679d68ffe07 | 2 | 2026-11-05T17:31:43.715808Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 302 | 719 | 21,839 | 48.4848% | 12,400.00 proxy | 5,246.00 proxy | 9.963788 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 7 | a9cb6f5e0898 | 2 | 2026-11-05T17:31:59.787828Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 221 | 638 | 16,828 | 63.2489% | 12,347.00 proxy | 3,807.00 proxy | 13.406593 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 8 | c6cc99230d7d | 2 | 2026-11-05T17:32:17.694417Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 111 | 528 | 20,631 | 50.9377% | 9,074.00 proxy | 2,522.00 proxy | 12.432638 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 9 | fb743f8d9615 | 2 | 2026-11-05T17:32:34.328076Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 262 | 679 | 21,195 | 49.9123% | 13,107.00 proxy | 8,204.00 proxy | 7.231563 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 10 | cfb2723018c6 | 2 | 2026-11-05T17:32:51.301376Z |
| arb-common-prose | 100.0000% | 19,098 | 8,858 | 268 | 685 | 19,783 | 53.6182% | 11,868.00 proxy | 4,679.00 proxy | 10.510234 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 11 | 7fa83acfdb56 | 3 | 2026-11-05T17:33:09.921084Z |
| arb-arcgrav | 100.0000% | 15,264 | 5,024 | 267 | 684 | 15,948 | 67.0860% | 11,765.00 proxy | 4,651.00 proxy | 10.415813 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 12 | 9a6fc9b0f258 | 3 | 2026-11-05T17:33:31.721609Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 154 | 571 | 21,691 | 48.4848% | 11,204.00 proxy | 2,695.00 proxy | 14.928070 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 13 | cecd2e464c6c | 3 | 2026-11-05T17:33:50.301402Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 246 | 663 | 21,171 | 49.9317% | 11,484.00 proxy | 4,322.00 proxy | 10.818731 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 14 | 6a33becaea70 | 3 | 2026-11-05T17:34:10.947702Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 361 | 778 | 20,889 | 50.9174% | 13,534.00 proxy | 6,267.00 proxy | 9.352638 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 15 | e5430c91964e | 3 | 2026-11-05T17:34:28.479721Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 267 | 684 | 21,200 | 49.9123% | 13,786.00 proxy | 6,585.00 proxy | 10.543192 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 16 | f931499dfb8d | 4 | 2026-11-05T17:34:51.816280Z |
| arb-markdown | 100.0000% | 20,119 | 9,879 | 184 | 601 | 20,720 | 50.8972% | 10,346.00 proxy | 3,543.00 proxy | 11.338333 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 17 | 0d391c0bd017 | 4 | 2026-11-05T17:35:10.008062Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 199 | 616 | 16,814 | 63.2177% | 10,658.00 proxy | 3,484.00 proxy | 11.665041 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 18 | fad6534dea23 | 4 | 2026-11-05T17:35:33.608103Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 281 | 698 | 21,826 | 48.4665% | 13,397.00 proxy | 4,883.00 proxy | 12.215208 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 19 | 0e05f8adfc3d | 4 | 2026-11-05T17:35:51.860350Z |
| arb-common-prose | 100.0000% | 19,114 | 8,874 | 271 | 688 | 19,802 | 53.5733% | 11,884.00 proxy | 4,692.00 proxy | 10.468705 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 20 | ce1e91653bf8 | 4 | 2026-11-05T17:36:11.413070Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 167 | 584 | 20,687 | 50.9377% | 11,847.00 proxy | 2,914.00 proxy | 15.322470 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 21 | c07591812e82 | 5 | 2026-11-05T17:36:30.635148Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 188 | 605 | 21,113 | 49.9317% | 11,639.00 proxy | 4,468.00 proxy | 11.872517 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 22 | 61b7904f161a | 5 | 2026-11-05T17:36:48.667705Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 185 | 602 | 20,642 | 51.0978% | 10,380.00 proxy | 3,225.00 proxy | 11.905158 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 23 | 520e47421ada | 5 | 2026-11-05T17:37:10.083357Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 185 | 602 | 16,792 | 63.2489% | 10,399.00 proxy | 3,286.00 proxy | 11.835275 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 24 | 9f6c92e0cc70 | 5 | 2026-11-05T17:37:26.992262Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 361 | 778 | 21,906 | 48.4665% | 13,441.00 proxy | 6,266.00 proxy | 9.234234 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 25 | 05b0d056e6d7 | 5 | 2026-11-05T17:37:44.038336Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 212 | 629 | 20,831 | 50.6881% | 12,276.00 proxy | 3,686.00 proxy | 13.678344 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 26 | 47023347a3ab | 6 | 2026-11-05T17:38:04.391929Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 247 | 664 | 16,862 | 63.2177% | 11,872.00 proxy | 4,285.00 proxy | 11.443439 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 27 | b30e52c8f82b | 6 | 2026-11-05T17:38:23.214114Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 206 | 623 | 20,663 | 51.0978% | 12,147.00 proxy | 3,577.00 proxy | 13.778135 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 28 | 4f7a563f180c | 6 | 2026-11-05T17:38:42.967967Z |
| arb-yaml | 100.0000% | 19,590 | 9,350 | 312 | 729 | 20,319 | 52.2716% | 12,593.00 proxy | 5,434.00 proxy | 9.833791 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 29 | dfc4871dbf57 | 6 | 2026-11-05T17:39:02.338906Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 267 | 684 | 20,795 | 50.9174% | 11,817.00 proxy | 4,782.00 proxy | 10.300146 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 30 | d0cc2f6e8bc8 | 6 | 2026-11-05T17:39:21.539764Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 150 | 567 | 20,678 | 50.9174% | 9,804.00 proxy | 2,645.00 proxy | 12.648410 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 31 | b7d218055b6b | 7 | 2026-11-05T17:39:41.345646Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 219 | 636 | 21,144 | 49.9317% | 14,279.00 proxy | 3,807.00 proxy | 16.491339 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 32 | 8159b1c2418a | 7 | 2026-11-05T17:39:59.384618Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 262 | 679 | 16,877 | 63.2177% | 13,608.00 proxy | 4,559.00 proxy | 13.346608 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 33 | 48a99523b594 | 7 | 2026-11-05T17:40:19.966878Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 178 | 595 | 20,635 | 51.0978% | 10,270.00 proxy | 3,099.00 proxy | 12.072391 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 34 | c8969a1c9abf | 7 | 2026-11-05T17:40:38.820428Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 157 | 574 | 21,694 | 48.4848% | 11,413.00 proxy | 2,750.00 proxy | 15.118674 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 35 | d2e826f94cae | 7 | 2026-11-05T17:40:55.089772Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 272 | 689 | 16,895 | 63.1865% | 11,760.00 proxy | 4,886.00 proxy | 9.991279 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 36 | eb2788e5b06e | 8 | 2026-11-05T17:41:11.179179Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 218 | 635 | 20,837 | 50.6881% | 12,618.00 proxy | 3,799.00 proxy | 13.910095 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 37 | 32c5edd44418 | 8 | 2026-11-05T17:41:29.759910Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 185 | 602 | 20,642 | 51.0978% | 10,182.00 proxy | 3,245.00 proxy | 11.542429 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 38 | 3a2d837bf727 | 8 | 2026-11-05T17:41:46.633018Z |
| arb-markdown | 100.0000% | 19,193 | 8,953 | 221 | 638 | 19,831 | 53.3528% | 12,572.00 proxy | 3,863.00 proxy | 13.671900 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 39 | 7ebf269dec1d | 8 | 2026-11-05T17:42:03.014781Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 273 | 690 | 21,206 | 49.9123% | 11,480.00 proxy | 4,491.00 proxy | 10.143687 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 40 | ba00feaad2fd | 8 | 2026-11-05T17:42:19.814410Z |
| arb-common-prose | 100.0000% | 20,048 | 9,808 | 213 | 630 | 20,678 | 51.0774% | 12,796.00 proxy | 3,768.00 proxy | 14.352941 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 41 | 8809024e157d | 9 | 2026-11-05T17:42:38.009948Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 315 | 732 | 20,934 | 50.6881% | 12,308.00 proxy | 5,326.00 proxy | 9.551300 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 42 | c7e0418b70b9 | 9 | 2026-11-05T17:42:56.004232Z |
| arb-markdown | 100.0000% | 19,193 | 8,953 | 201 | 618 | 19,811 | 53.3528% | 12,492.00 proxy | 5,137.00 proxy | 11.920583 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 43 | c9977000f60c | 9 | 2026-11-05T17:43:16.339079Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 111 | 528 | 21,036 | 49.9317% | 8,806.00 proxy | 1,902.00 proxy | 13.100569 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 44 | 1538f6516b8f | 9 | 2026-11-05T17:43:32.559624Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 304 | 721 | 16,927 | 63.1865% | 14,180.00 proxy | 6,967.00 proxy | 10.018056 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 45 | 1a198a69d21f | 9 | 2026-11-05T17:43:47.887594Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 219 | 636 | 21,756 | 48.4848% | 10,858.00 proxy | 3,770.00 proxy | 11.162205 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 46 | ede10595bd6b | 10 | 2026-11-05T17:44:07.158976Z |
| arb-arcgrav | 100.0000% | 15,272 | 5,032 | 157 | 574 | 15,846 | 67.0508% | 11,512.00 proxy | 4,400.00 proxy | 12.411867 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 47 | 01fc6ef4d5e1 | 10 | 2026-11-05T17:44:26.116079Z |
| arb-markdown | 100.0000% | 19,193 | 8,953 | 135 | 552 | 19,745 | 53.3528% | 9,540.00 proxy | 2,364.00 proxy | 13.023593 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 48 | 8487b3b6652f | 10 | 2026-11-05T17:44:41.447132Z |
| arb-yaml | 100.0000% | 19,590 | 9,350 | 216 | 633 | 20,223 | 52.2716% | 12,478.00 proxy | 5,287.00 proxy | 11.378165 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 49 | 7b1f346c1e41 | 10 | 2026-11-05T17:44:56.433893Z |
| arb-common-prose | 97.9167% | 20,024 | 9,784 | 347 | 764 | 20,788 | 51.1386% | 13,161.00 proxy | 6,155.00 proxy | 9.182176 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 50 | 3d917f357a47 | 10 | 2026-11-05T17:45:13.858142Z |

### Treatment Total Averaged Results

Token and invocation counts sum retained observations, including retries. The primary result preserves its registered aggregation. Timing is the arithmetic mean of available observation measurements, not a sum; missing contributors are not imputed as zero and incomplete means are marked partial. Cache Read Fraction is summed eligible cached input divided by summed eligible input. Distinct Tool Calls counts unique tool identities across the treatment, not the sum of observation counts.

| Treatment | Accuracy | Input Tokens | Uncached Input | Reasoning Output Tokens | Output Tokens | Total Tokens | Cache Read Fraction | Average Inference Duration | Average TTFT | Average TBT | Average Direct TTFT | Average Direct TBT | Tool Calls | Distinct Tool Calls | Failed Tool Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arb-arcgrav | 100.0000% | 160,120 | 57,720 | 2,393 | 6,563 | 166,683 | 63.9520% | 12,013.20 proxy | 4,514.90 proxy | 11.490375 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-common-prose | 99.7917% | 198,516 | 96,116 | 2,219 | 6,389 | 204,905 | 51.5827% | 11,591.00 proxy | 3,883.90 proxy | 12.203624 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-markdown | 100.0000% | 198,348 | 95,948 | 1,982 | 6,152 | 204,500 | 51.6264% | 11,139.60 proxy | 3,726.40 proxy | 12.189590 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-xml | 100.0000% | 208,470 | 106,070 | 2,368 | 6,538 | 215,008 | 49.1198% | 12,171.40 proxy | 4,104.50 proxy | 12.600086 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-yaml | 100.0000% | 203,276 | 100,876 | 2,280 | 6,450 | 209,726 | 50.3749% | 12,030.80 proxy | 4,774.30 proxy | 11.372751 proxy | Unavailable | Unavailable | 0 | 0 | 0 |

## Notable Results and Exceptions

- **Accuracy:** arb-arcgrav 100.0000%; arb-common-prose 99.7917%; arb-markdown 100.0000%; arb-xml 100.0000%; arb-yaml 100.0000%.
- **Total Tokens:** arb-arcgrav recorded the lowest within-run value (166,683).
- **Uncached Input Tokens:** arb-arcgrav recorded the lowest within-run value (57,720).
- **Inference Duration:** arb-markdown recorded the lowest within-run value (11,139.60 proxy).
- **TTFT:** arb-markdown recorded the lowest within-run value (3,726.40 proxy).
- **TBT:** arb-yaml recorded the lowest within-run value (11.372751 proxy).
- **Measurement Exceptions:** Average Direct TTFT: 50 unavailable; Average Direct TBT: 50 unavailable.
- **Registered Prerequisites:** satisfied.
- **Interpretation:** These are within-run observations, not evidence of a general performance advantage.

## Measurements

- **Treatment:** Registered treatment identifier; the same treatments appear in each results table.
- **Accuracy:** Registered correctness proportion, displayed as a percentage. This is the registered metric, not an assumed whole-output exact match.
  Treatment results average repetitions within each case, then weight cases equally; they are not pooled field counts.
- **Input Tokens:** Retained input counter, including cached input. Treatment totals sum the observation counts.
- **Uncached Input:** Input minus cached input from compatible attempt-local counters. Treatment totals sum the observation counts.
- **Reasoning Output Tokens:** Reasoning subset already included in Output Tokens. Do not add it again to Total Tokens.
- **Output Tokens:** Retained output counter, including reasoning output. Treatment totals sum the observation counts.
- **Total Tokens:** Retained total input and output counter. Cached input and reasoning subsets are not added again. Counters are not billing measurements.
- **Cache Read Fraction:** Cached input / input for compatible attempts. Treatment totals use the ratio of sums, not the mean of observation ratios. A zero denominator is unavailable. Displayed as a percentage, rounded to four decimals.
- **Average Inference Duration:** Retained session inference mean in milliseconds. Proxy values derive from paired reasoning-item and agent-message-item durations, not provider request duration.
- **Average TTFT:** Retained millisecond mean; a proxy uses reasoning-item duration, not measured request-to-first-token latency.
- **Average TBT:** Retained millisecond mean; a proxy divides agent-message-item duration by (output tokens − 1), not observed inter-token timing. Rounded to six decimals.
- **Average Direct TTFT:** Direct request-start to first-actual-token latency. Unavailable when the required timestamps are absent; not replaced with a proxy.
- **Average Direct TBT:** Direct inter-token timing from ordered actual-token timestamps. Unavailable when these timestamps are absent; not replaced with a proxy.
- **Tool Calls:** Observed tool invocations, including failed attempts and retries. A complete empty trace establishes zero; missing evidence does not.
- **Distinct Tool Calls:** Unique tool identities per observation; treatment totals use the union of identities, not the sum of observation counts.
- **Failed Tool Calls:** Invocations with observed failed terminal outcomes. Treatment totals sum the observation counts.
- **Execution Order:** One-based rank by the earliest absolute attempt start across treatments. Ties share rank; incomplete start evidence has no rank. Not a repetition or completion rank.
- **Observation ID Prefix:** Short unique prefix of the native identifier, starting with 12 hash characters and extending for collisions. Full identifiers remain in supporting data.
- **Repetition:** Native repetition identifier, without renumbering.
- **Attempt Start UTC:** Earliest native attempt started_at, normalized to UTC. Session-relative timestamps are not used.

## Links to Supporting Data

The supporting JSON files are stored in the [retained AgMark archive](./generation-e9e3e53a556a560c3cb245c0fa8ea477b4b415a93fa16fa78b779001e84347b0.agmark) (a ZIP container), not as loose files beside this Markdown report. Open the archive and inspect these members:

- `reports/generation-e9e3e53a556a560c3cb245c0fa8ea477b4b415a93fa16fa78b779001e84347b0/report.json`: result tables, registered report sections and availability states.
- `reports/generation-e9e3e53a556a560c3cb245c0fa8ea477b4b415a93fa16fa78b779001e84347b0/canonical-evidence.json`: full observation IDs, scores, measurement provenance and source references.
- `reports/generation-e9e3e53a556a560c3cb245c0fa8ea477b4b415a93fa16fa78b779001e84347b0/report-manifest.json`: exact component identities and integrity hashes.

The link above opens the actual archive on GitHub. The original report and source evidence embedded in the archive remain unchanged.
