# AgMark Individual Run Report

## Run Details

- **Benchmark:** arcgrav.authority-resolution.benchmark.core
- **Comparison Track:** arcgrav.authority-resolution.field-accuracy
- **Generation:** generation-1c0c6542f5be05b1cab180ea4da2be5c8a256a27e8f94bb7253e310ddba61b6e
- **Report Generated:** 2026-11-05T18:56:47.488436Z
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
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 384 | 801 | 16,999 | 63.2177% | 12,063.00 proxy | 4,855.00 proxy | 9.010000 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 1 | 07fb076a4c1d | 1 | 2026-11-05T18:41:47.831015Z |
| arb-yaml | 100.0000% | 20,524 | 10,284 | 191 | 608 | 21,132 | 49.8928% | 11,718.00 proxy | 3,537.00 proxy | 13.477759 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 2 | 81605b323a75 | 1 | 2026-11-05T18:42:07.606635Z |
| arb-markdown | 100.0000% | 19,185 | 8,945 | 223 | 640 | 19,825 | 53.3750% | 10,960.00 proxy | 3,821.00 proxy | 11.172144 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 3 | 5ff154a710bb | 1 | 2026-11-05T18:42:25.398710Z |
| arb-common-prose | 100.0000% | 19,106 | 8,866 | 172 | 589 | 19,695 | 53.5957% | 11,422.00 proxy | 3,034.00 proxy | 14.265306 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 4 | 3eadbfef768c | 1 | 2026-11-05T18:42:42.325438Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 232 | 649 | 21,777 | 48.4665% | 11,242.00 proxy | 4,078.00 proxy | 11.055556 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 5 | 6c16de6fb365 | 1 | 2026-11-05T18:42:58.343295Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 182 | 599 | 21,727 | 48.4665% | 11,586.00 proxy | 3,202.00 proxy | 14.020067 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 6 | a9cb6f5e0898 | 2 | 2026-11-05T18:43:15.408963Z |
| arb-yaml | 100.0000% | 19,590 | 9,350 | 212 | 629 | 20,219 | 52.2716% | 10,895.00 proxy | 3,707.00 proxy | 11.445860 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 7 | cfb2723018c6 | 2 | 2026-11-05T18:43:33.965205Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 283 | 700 | 16,898 | 63.2177% | 13,368.00 proxy | 6,134.00 proxy | 10.349070 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 8 | c6cc99230d7d | 2 | 2026-11-05T18:43:51.475923Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 347 | 764 | 20,867 | 50.9377% | 13,267.00 proxy | 6,034.00 proxy | 9.479685 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 9 | fb743f8d9615 | 2 | 2026-11-05T18:44:09.299540Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 180 | 597 | 20,637 | 51.0978% | 11,575.00 proxy | 4,347.00 proxy | 12.127517 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 10 | 7679d68ffe07 | 2 | 2026-11-05T18:44:29.297344Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 157 | 574 | 20,606 | 51.1182% | 10,058.00 proxy | 2,703.00 proxy | 12.835951 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 11 | 7fa83acfdb56 | 3 | 2026-11-05T18:44:44.780807Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 164 | 581 | 21,097 | 49.9123% | 10,298.00 proxy | 2,978.00 proxy | 12.620690 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 12 | 6a33becaea70 | 3 | 2026-11-05T18:45:01.147807Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 231 | 648 | 21,768 | 48.4848% | 10,790.00 proxy | 4,011.00 proxy | 10.477589 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 13 | cecd2e464c6c | 3 | 2026-11-05T18:45:18.855025Z |
| arb-arcgrav | 100.0000% | 15,272 | 5,032 | 327 | 744 | 16,016 | 67.0508% | 12,951.00 proxy | 5,732.00 proxy | 9.716016 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 14 | 9a6fc9b0f258 | 3 | 2026-11-05T18:45:35.797539Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 293 | 710 | 20,821 | 50.9174% | 12,322.00 proxy | 5,142.00 proxy | 10.126939 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 15 | e5430c91964e | 3 | 2026-11-05T18:45:54.548425Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 176 | 593 | 20,795 | 50.6881% | 10,284.00 proxy | 3,106.00 proxy | 12.125000 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 16 | 0e05f8adfc3d | 4 | 2026-11-05T18:46:14.603549Z |
| arb-markdown | 100.0000% | 19,177 | 8,937 | 147 | 564 | 19,741 | 53.3973% | 10,977.00 proxy | 2,545.00 proxy | 14.976909 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 17 | 0d391c0bd017 | 4 | 2026-11-05T18:46:31.093010Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 241 | 658 | 16,864 | 63.1865% | 12,539.00 proxy | 4,176.00 proxy | 12.729072 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 18 | fad6534dea23 | 4 | 2026-11-05T18:46:49.600553Z |
| arb-yaml | 100.0000% | 19,582 | 9,342 | 276 | 693 | 20,275 | 52.2929% | 12,002.00 proxy | 4,820.00 proxy | 10.378613 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 19 | f931499dfb8d | 4 | 2026-11-05T18:47:06.809257Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 292 | 709 | 20,749 | 51.0978% | 13,493.00 proxy | 5,092.00 proxy | 11.865819 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 20 | ce1e91653bf8 | 4 | 2026-11-05T18:47:24.353394Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 253 | 670 | 20,702 | 51.1182% | 11,802.00 proxy | 4,403.00 proxy | 11.059791 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 21 | 520e47421ada | 5 | 2026-11-05T18:47:43.491958Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 205 | 622 | 21,742 | 48.4848% | 10,797.00 proxy | 3,521.00 proxy | 11.716586 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 22 | 05b0d056e6d7 | 5 | 2026-11-05T18:48:01.214620Z |
| arb-yaml | 100.0000% | 19,590 | 9,350 | 202 | 619 | 20,209 | 52.2716% | 12,880.00 proxy | 5,325.00 proxy | 12.224919 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 23 | 61b7904f161a | 5 | 2026-11-05T18:48:18.025148Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 294 | 711 | 16,917 | 63.1865% | 12,310.00 proxy | 5,143.00 proxy | 10.094366 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 24 | 9f6c92e0cc70 | 5 | 2026-11-05T18:48:35.249721Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 146 | 563 | 20,674 | 50.9174% | 10,868.00 proxy | 3,644.00 proxy | 12.854093 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 25 | c07591812e82 | 5 | 2026-11-05T18:48:53.531894Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 241 | 658 | 20,761 | 50.9377% | 11,124.00 proxy | 3,928.00 proxy | 10.952816 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 26 | d0cc2f6e8bc8 | 6 | 2026-11-05T18:49:09.260455Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 316 | 733 | 16,931 | 63.2177% | 14,116.00 proxy | 7,045.00 proxy | 9.659836 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 27 | b30e52c8f82b | 6 | 2026-11-05T18:49:26.306113Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 147 | 564 | 20,604 | 51.0978% | 9,644.00 proxy | 2,438.00 proxy | 12.799290 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 28 | 4f7a563f180c | 6 | 2026-11-05T18:49:44.729595Z |
| arb-yaml | 100.0000% | 19,582 | 9,342 | 189 | 606 | 20,188 | 52.2929% | 12,076.00 proxy | 4,943.00 proxy | 11.790083 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 29 | dfc4871dbf57 | 6 | 2026-11-05T18:49:59.978118Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 309 | 726 | 21,846 | 48.4848% | 12,433.00 proxy | 5,225.00 proxy | 9.942069 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 30 | 47023347a3ab | 6 | 2026-11-05T18:50:16.484531Z |
| arb-markdown | 97.9167% | 20,103 | 9,863 | 198 | 615 | 20,718 | 50.9377% | 12,527.00 proxy | 5,109.00 proxy | 12.081433 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 31 | b7d218055b6b | 7 | 2026-11-05T18:50:34.453260Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 304 | 721 | 21,849 | 48.4665% | 12,390.00 proxy | 5,192.00 proxy | 9.997222 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 32 | d2e826f94cae | 7 | 2026-11-05T18:50:51.372647Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 138 | 556 | 21,072 | 49.9123% | 9,702.00 proxy | 2,402.00 proxy | 13.153153 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 33 | 8159b1c2418a | 7 | 2026-11-05T18:51:09.322328Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 273 | 690 | 20,722 | 51.1182% | 11,942.00 proxy | 4,747.00 proxy | 10.442671 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 34 | c8969a1c9abf | 7 | 2026-11-05T18:51:25.921476Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 294 | 711 | 16,917 | 63.1865% | 13,595.00 proxy | 6,753.00 proxy | 9.636620 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 35 | 48a99523b594 | 7 | 2026-11-05T18:51:43.350273Z |
| arb-common-prose | 95.8333% | 20,032 | 9,792 | 176 | 570 | 20,602 | 51.1182% | 9,834.00 proxy | 3,075.00 proxy | 11.878735 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 36 | 3a2d837bf727 | 8 | 2026-11-05T18:52:01.867665Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 159 | 576 | 21,696 | 48.4848% | 9,996.00 proxy | 2,794.00 proxy | 12.525217 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 37 | 32c5edd44418 | 8 | 2026-11-05T18:52:18.464528Z |
| arb-markdown | 100.0000% | 18,969 | 8,729 | 299 | 716 | 19,685 | 53.9828% | 15,487.00 proxy | 5,203.00 proxy | 14.383217 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 38 | 7ebf269dec1d | 8 | 2026-11-05T18:52:34.830361Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 232 | 649 | 16,847 | 63.2177% | 11,198.00 proxy | 4,081.00 proxy | 10.983025 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 39 | eb2788e5b06e | 8 | 2026-11-05T18:52:56.676705Z |
| arb-yaml | 85.1852% | 20,508 | 10,268 | 200 | 676 | 21,184 | 49.9317% | 13,101.00 proxy | 3,494.00 proxy | 14.232593 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 40 | ba00feaad2fd | 8 | 2026-11-05T18:53:14.251256Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 209 | 626 | 21,746 | 48.4848% | 12,385.00 proxy | 3,631.00 proxy | 14.006400 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 41 | c7e0418b70b9 | 9 | 2026-11-05T18:53:31.719916Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 205 | 622 | 21,138 | 49.9123% | 12,160.00 proxy | 3,580.00 proxy | 13.816425 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 42 | 1538f6516b8f | 9 | 2026-11-05T18:53:50.271057Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 304 | 721 | 16,911 | 63.2489% | 12,318.00 proxy | 5,211.00 proxy | 9.870833 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 43 | 1a198a69d21f | 9 | 2026-11-05T18:54:07.660687Z |
| arb-markdown | 97.9167% | 20,111 | 9,871 | 197 | 614 | 20,725 | 50.9174% | 12,144.00 proxy | 3,452.00 proxy | 14.179445 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 44 | c9977000f60c | 9 | 2026-11-05T18:54:25.708148Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 249 | 666 | 20,698 | 51.1182% | 11,528.00 proxy | 4,347.00 proxy | 10.798496 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 45 | 8809024e157d | 9 | 2026-11-05T18:54:41.852282Z |
| arb-yaml | 100.0000% | 19,582 | 9,342 | 337 | 754 | 20,336 | 52.2929% | 14,263.00 proxy | 7,313.00 proxy | 9.229748 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 46 | 7b1f346c1e41 | 10 | 2026-11-05T18:55:05.944495Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 215 | 632 | 21,760 | 48.4665% | 10,897.00 proxy | 4,039.00 proxy | 10.868463 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 47 | ede10595bd6b | 10 | 2026-11-05T18:55:24.620718Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 244 | 661 | 20,764 | 50.9377% | 11,170.00 proxy | 4,174.00 proxy | 10.600000 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 48 | 8487b3b6652f | 10 | 2026-11-05T18:55:41.769698Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 269 | 686 | 16,884 | 63.2177% | 13,719.00 proxy | 4,671.00 proxy | 13.208759 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 49 | 01fc6ef4d5e1 | 10 | 2026-11-05T18:56:02.152985Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 228 | 645 | 20,685 | 51.0978% | 10,902.00 proxy | 3,763.00 proxy | 11.085404 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 50 | 3d917f357a47 | 10 | 2026-11-05T18:56:21.426441Z |

### Treatment Total Averaged Results

Token and invocation counts sum retained observations, including retries. The primary result preserves its registered aggregation. Timing is the arithmetic mean of available observation measurements, not a sum; missing contributors are not imputed as zero and incomplete means are marked partial. Cache Read Fraction is summed eligible cached input divided by summed eligible input. Distinct Tool Calls counts unique tool identities across the treatment, not the sum of observation counts.

| Treatment | Accuracy | Input Tokens | Uncached Input | Reasoning Output Tokens | Output Tokens | Total Tokens | Cache Read Fraction | Average Inference Duration | Average TTFT | Average TBT | Average Direct TTFT | Average Direct TBT | Tool Calls | Distinct Tool Calls | Failed Tool Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arb-arcgrav | 100.0000% | 161,070 | 58,670 | 2,944 | 7,114 | 168,184 | 63.5748% | 12,817.70 proxy | 5,380.10 proxy | 10.525760 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-common-prose | 99.5833% | 199,426 | 97,026 | 2,127 | 6,274 | 205,700 | 51.3474% | 11,220.00 proxy | 3,794.90 proxy | 11.915898 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-markdown | 99.5833% | 198,076 | 95,676 | 2,335 | 6,505 | 204,581 | 51.6973% | 12,084.60 proxy | 4,305.20 proxy | 12.080668 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-xml | 100.0000% | 210,314 | 107,914 | 2,222 | 6,392 | 216,706 | 48.6891% | 11,280.00 proxy | 3,879.90 proxy | 11.673417 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-yaml | 98.5185% | 200,506 | 98,106 | 2,114 | 6,344 | 206,850 | 51.0708% | 11,909.50 proxy | 4,209.90 proxy | 12.236984 proxy | Unavailable | Unavailable | 0 | 0 | 0 |

## Notable Results and Exceptions

- **Accuracy:** arb-arcgrav 100.0000%; arb-common-prose 99.5833%; arb-markdown 99.5833%; arb-xml 100.0000%; arb-yaml 98.5185%.
- **Total Tokens:** arb-arcgrav recorded the lowest within-run value (168,184).
- **Uncached Input Tokens:** arb-arcgrav recorded the lowest within-run value (58,670).
- **Inference Duration:** arb-common-prose recorded the lowest within-run value (11,220.00 proxy).
- **TTFT:** arb-common-prose recorded the lowest within-run value (3,794.90 proxy).
- **TBT:** arb-arcgrav recorded the lowest within-run value (10.525760 proxy).
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

The supporting JSON files are stored in the [retained AgMark archive](./generation-1c0c6542f5be05b1cab180ea4da2be5c8a256a27e8f94bb7253e310ddba61b6e.agmark) (a ZIP container), not as loose files beside this Markdown report. Open the archive and inspect these members:

- `reports/generation-1c0c6542f5be05b1cab180ea4da2be5c8a256a27e8f94bb7253e310ddba61b6e/report.json`: result tables, registered report sections and availability states.
- `reports/generation-1c0c6542f5be05b1cab180ea4da2be5c8a256a27e8f94bb7253e310ddba61b6e/canonical-evidence.json`: full observation IDs, scores, measurement provenance and source references.
- `reports/generation-1c0c6542f5be05b1cab180ea4da2be5c8a256a27e8f94bb7253e310ddba61b6e/report-manifest.json`: exact component identities and integrity hashes.

The link above opens the actual archive on GitHub. The original report and source evidence embedded in the archive remain unchanged.
