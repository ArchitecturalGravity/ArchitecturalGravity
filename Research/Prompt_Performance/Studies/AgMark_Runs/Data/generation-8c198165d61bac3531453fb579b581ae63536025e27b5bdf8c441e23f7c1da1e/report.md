# AgMark Individual Run Report

## Run Details

- **Benchmark:** arcgrav.authority-resolution.benchmark.core
- **Comparison Track:** arcgrav.authority-resolution.field-accuracy
- **Generation:** generation-8c198165d61bac3531453fb579b581ae63536025e27b5bdf8c441e23f7c1da1e
- **Report Generated:** 2026-11-05T18:18:31.171740Z
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
| arb-arcgrav | 100.0000% | 15,264 | 5,024 | 254 | 671 | 15,935 | 67.0860% | 11,399.00 proxy | 4,399.00 proxy | 10.447761 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 1 | 07fb076a4c1d | 1 | 2026-11-05T18:03:59.312788Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 221 | 638 | 20,741 | 50.9377% | 12,636.00 proxy | 3,847.00 proxy | 13.797488 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 2 | 5ff154a710bb | 1 | 2026-11-05T18:04:16.275289Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 202 | 619 | 20,651 | 51.1182% | 10,485.00 proxy | 3,449.00 proxy | 11.385113 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 3 | 3eadbfef768c | 1 | 2026-11-05T18:04:33.755922Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 170 | 587 | 21,095 | 49.9317% | 11,860.00 proxy | 2,967.00 proxy | 15.175768 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 4 | 81605b323a75 | 1 | 2026-11-05T18:04:50.022359Z |
| arb-xml | 100.0000% | 21,136 | 10,896 | 174 | 591 | 21,727 | 48.4481% | 9,959.00 proxy | 3,024.00 proxy | 11.754237 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 5 | 6c16de6fb365 | 1 | 2026-11-05T18:05:06.287843Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 208 | 625 | 16,815 | 63.2489% | 12,474.00 proxy | 5,341.00 proxy | 11.431090 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 6 | c6cc99230d7d | 2 | 2026-11-05T18:05:22.874448Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 212 | 629 | 20,661 | 51.1182% | 10,590.00 proxy | 3,641.00 proxy | 11.065287 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 7 | 7679d68ffe07 | 2 | 2026-11-05T18:05:39.926180Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 158 | 575 | 21,083 | 49.9317% | 11,676.00 proxy | 2,738.00 proxy | 15.571429 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 8 | cfb2723018c6 | 2 | 2026-11-05T18:05:57.258110Z |
| arb-markdown | 100.0000% | 19,177 | 8,937 | 174 | 591 | 19,768 | 53.3973% | 9,931.00 proxy | 2,968.00 proxy | 11.801695 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 9 | fb743f8d9615 | 2 | 2026-11-05T18:06:13.601919Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 166 | 583 | 21,703 | 48.4848% | 11,671.00 proxy | 2,838.00 proxy | 15.176976 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 10 | a9cb6f5e0898 | 2 | 2026-11-05T18:06:29.841658Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 288 | 705 | 20,816 | 50.9174% | 11,874.00 proxy | 4,882.00 proxy | 9.931818 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 11 | e5430c91964e | 3 | 2026-11-05T18:06:46.147290Z |
| arb-common-prose | 97.9167% | 19,122 | 8,882 | 176 | 593 | 19,715 | 53.5509% | 12,109.00 proxy | 3,076.00 proxy | 15.258446 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 12 | 7fa83acfdb56 | 3 | 2026-11-05T18:07:05.009895Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 259 | 676 | 21,184 | 49.9317% | 11,918.00 proxy | 4,314.00 proxy | 11.265185 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 13 | 6a33becaea70 | 3 | 2026-11-05T18:07:21.221702Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 225 | 642 | 16,848 | 63.1865% | 12,781.00 proxy | 3,924.00 proxy | 13.817473 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 14 | 9a6fc9b0f258 | 3 | 2026-11-05T18:07:39.303989Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 256 | 673 | 21,793 | 48.4848% | 11,402.00 proxy | 4,289.00 proxy | 10.584821 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 15 | cecd2e464c6c | 3 | 2026-11-05T18:07:55.939758Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 269 | 686 | 20,797 | 50.9174% | 13,915.00 proxy | 4,677.00 proxy | 13.486131 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 16 | 0d391c0bd017 | 4 | 2026-11-05T18:08:13.532936Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 376 | 793 | 21,301 | 49.9317% | 13,304.00 proxy | 6,312.00 proxy | 8.828283 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 17 | f931499dfb8d | 4 | 2026-11-05T18:08:32.259456Z |
| arb-xml | 100.0000% | 20,194 | 9,954 | 292 | 709 | 20,903 | 50.7081% | 13,889.00 proxy | 6,962.00 proxy | 9.783898 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 18 | 0e05f8adfc3d | 4 | 2026-11-05T18:08:52.690419Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 187 | 604 | 20,636 | 51.1182% | 10,381.00 proxy | 3,230.00 proxy | 11.859038 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 19 | ce1e91653bf8 | 4 | 2026-11-05T18:09:11.069737Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 273 | 690 | 16,880 | 63.2489% | 13,508.00 proxy | 6,369.00 proxy | 10.361393 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 20 | fad6534dea23 | 4 | 2026-11-05T18:09:27.569772Z |
| arb-arcgrav | 97.9167% | 15,264 | 5,024 | 148 | 565 | 15,829 | 67.0860% | 9,631.00 proxy | 2,551.00 proxy | 12.553191 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 21 | 9f6c92e0cc70 | 5 | 2026-11-05T18:09:44.934451Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 204 | 621 | 20,724 | 50.9377% | 12,080.00 proxy | 5,085.00 proxy | 11.282258 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 22 | c07591812e82 | 5 | 2026-11-05T18:10:00.357895Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 177 | 594 | 21,722 | 48.4665% | 10,182.00 proxy | 3,038.00 proxy | 12.047218 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 23 | 05b0d056e6d7 | 5 | 2026-11-05T18:10:17.620588Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 161 | 578 | 20,618 | 51.0978% | 11,771.00 proxy | 4,592.00 proxy | 12.441941 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 24 | 520e47421ada | 5 | 2026-11-05T18:10:34.345187Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 247 | 664 | 21,180 | 49.9123% | 11,263.00 proxy | 4,045.00 proxy | 10.886878 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 25 | 61b7904f161a | 5 | 2026-11-05T18:10:50.412506Z |
| arb-arcgrav | 100.0000% | 15,264 | 5,024 | 185 | 602 | 15,866 | 67.0860% | 12,082.00 proxy | 4,935.00 proxy | 11.891847 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 26 | b30e52c8f82b | 6 | 2026-11-05T18:11:08.105336Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 199 | 616 | 21,736 | 48.4848% | 10,368.00 proxy | 3,313.00 proxy | 11.471545 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 27 | 47023347a3ab | 6 | 2026-11-05T18:11:24.325685Z |
| arb-yaml | 100.0000% | 19,590 | 9,350 | 177 | 594 | 20,184 | 52.2716% | 11,951.00 proxy | 4,792.00 proxy | 12.072513 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 28 | dfc4871dbf57 | 6 | 2026-11-05T18:11:41.102632Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 262 | 679 | 20,782 | 50.9377% | 11,501.00 proxy | 4,407.00 proxy | 10.463127 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 29 | d0cc2f6e8bc8 | 6 | 2026-11-05T18:11:56.717052Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 212 | 629 | 20,661 | 51.1182% | 12,478.00 proxy | 5,411.00 proxy | 11.253185 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 30 | 4f7a563f180c | 6 | 2026-11-05T18:12:14.108529Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 291 | 708 | 16,898 | 63.2489% | 12,180.00 proxy | 5,039.00 proxy | 10.100424 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 31 | 48a99523b594 | 7 | 2026-11-05T18:12:31.039715Z |
| arb-markdown | 100.0000% | 19,185 | 8,945 | 333 | 750 | 19,935 | 53.3750% | 14,310.00 proxy | 7,431.00 proxy | 9.184246 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 32 | b7d218055b6b | 7 | 2026-11-05T18:12:48.643657Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 194 | 611 | 21,731 | 48.4848% | 10,569.00 proxy | 3,371.00 proxy | 11.800000 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 33 | d2e826f94cae | 7 | 2026-11-05T18:13:07.552836Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 174 | 591 | 20,623 | 51.1182% | 11,554.00 proxy | 4,544.00 proxy | 11.881356 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 34 | c8969a1c9abf | 7 | 2026-11-05T18:13:24.274309Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 287 | 704 | 21,220 | 49.9123% | 12,970.00 proxy | 4,980.00 proxy | 11.365576 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 35 | 8159b1c2418a | 7 | 2026-11-05T18:13:40.563244Z |
| arb-common-prose | 100.0000% | 19,114 | 8,874 | 319 | 736 | 19,850 | 53.5733% | 12,695.00 proxy | 5,518.00 proxy | 9.764626 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 36 | 3a2d837bf727 | 8 | 2026-11-05T18:13:59.811708Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 145 | 562 | 20,673 | 50.9174% | 9,674.00 proxy | 2,519.00 proxy | 12.754011 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 37 | 7ebf269dec1d | 8 | 2026-11-05T18:14:19.220340Z |
| arb-xml | 100.0000% | 21,136 | 10,896 | 131 | 548 | 21,684 | 48.4481% | 9,466.00 proxy | 2,289.00 proxy | 13.120658 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 38 | 32c5edd44418 | 8 | 2026-11-05T18:14:34.774707Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 239 | 656 | 16,846 | 63.2489% | 11,272.00 proxy | 4,131.00 proxy | 10.902290 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 39 | eb2788e5b06e | 8 | 2026-11-05T18:14:50.100737Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 116 | 533 | 21,049 | 49.9123% | 9,139.00 proxy | 2,174.00 proxy | 13.092105 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 40 | ba00feaad2fd | 8 | 2026-11-05T18:15:08.263121Z |
| arb-common-prose | 100.0000% | 19,130 | 8,890 | 213 | 630 | 19,760 | 53.5285% | 10,820.00 proxy | 3,695.00 proxy | 11.327504 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 41 | 8809024e157d | 9 | 2026-11-05T18:15:23.164801Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 292 | 709 | 21,829 | 48.4848% | 13,845.00 proxy | 6,605.00 proxy | 10.225989 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 42 | c7e0418b70b9 | 9 | 2026-11-05T18:15:39.752269Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 180 | 597 | 16,787 | 63.2489% | 10,269.00 proxy | 3,127.00 proxy | 11.983221 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 43 | 1a198a69d21f | 9 | 2026-11-05T18:15:58.665201Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 218 | 635 | 20,738 | 50.9377% | 10,902.00 proxy | 6,530.00 proxy | 6.895899 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 44 | c9977000f60c | 9 | 2026-11-05T18:16:15.184649Z |
| arb-yaml | 100.0000% | 19,590 | 9,350 | 178 | 595 | 20,185 | 52.2716% | 10,211.00 proxy | 3,083.00 proxy | 12.000000 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 45 | 1538f6516b8f | 9 | 2026-11-05T18:16:32.301955Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 323 | 740 | 21,248 | 49.9317% | 12,673.00 proxy | 5,555.00 proxy | 9.631935 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 46 | 7b1f346c1e41 | 10 | 2026-11-05T18:16:48.468201Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 214 | 631 | 16,821 | 63.2489% | 10,831.00 proxy | 4,140.00 proxy | 10.620635 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 47 | 01fc6ef4d5e1 | 10 | 2026-11-05T18:17:07.020727Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 219 | 636 | 20,668 | 51.1182% | 15,379.00 proxy | 3,211.00 proxy | 19.162205 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 48 | 3d917f357a47 | 10 | 2026-11-05T18:17:23.931691Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 187 | 604 | 20,715 | 50.9174% | 11,917.00 proxy | 3,228.00 proxy | 14.409619 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 49 | 8487b3b6652f | 10 | 2026-11-05T18:17:47.124891Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 192 | 609 | 21,729 | 48.4848% | 10,493.00 proxy | 3,350.00 proxy | 11.748355 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 50 | ede10595bd6b | 10 | 2026-11-05T18:18:04.273131Z |

### Treatment Total Averaged Results

Token and invocation counts sum retained observations, including retries. The primary result preserves its registered aggregation. Timing is the arithmetic mean of available observation measurements, not a sum; missing contributors are not imputed as zero and incomplete means are marked partial. Cache Read Fraction is summed eligible cached input divided by summed eligible input. Distinct Tool Calls counts unique tool identities across the treatment, not the sum of observation counts.

| Treatment | Accuracy | Input Tokens | Uncached Input | Reasoning Output Tokens | Output Tokens | Total Tokens | Cache Read Fraction | Average Inference Duration | Average TTFT | Average TBT | Average Direct TTFT | Average Direct TBT | Tool Calls | Distinct Tool Calls | Failed Tool Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arb-arcgrav | 99.7917% | 159,138 | 56,738 | 2,217 | 6,387 | 165,525 | 64.3467% | 11,642.70 proxy | 4,395.60 proxy | 11.410933 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-common-prose | 99.7917% | 197,598 | 95,198 | 2,075 | 6,245 | 203,843 | 51.8224% | 11,826.20 proxy | 4,036.70 proxy | 12.539870 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-markdown | 100.0000% | 199,218 | 96,818 | 2,301 | 6,471 | 205,689 | 51.4010% | 11,874.00 proxy | 4,557.40 proxy | 11.400629 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-xml | 100.0000% | 210,314 | 107,914 | 2,073 | 6,243 | 216,557 | 48.6891% | 11,184.40 proxy | 3,907.90 proxy | 11.771370 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-yaml | 100.0000% | 203,268 | 100,868 | 2,291 | 6,461 | 209,729 | 50.3768% | 11,696.50 proxy | 4,096.00 proxy | 11.988967 proxy | Unavailable | Unavailable | 0 | 0 | 0 |

## Notable Results and Exceptions

- **Accuracy:** arb-arcgrav 99.7917%; arb-common-prose 99.7917%; arb-markdown 100.0000%; arb-xml 100.0000%; arb-yaml 100.0000%.
- **Total Tokens:** arb-arcgrav recorded the lowest within-run value (165,525).
- **Uncached Input Tokens:** arb-arcgrav recorded the lowest within-run value (56,738).
- **Inference Duration:** arb-xml recorded the lowest within-run value (11,184.40 proxy).
- **TTFT:** arb-xml recorded the lowest within-run value (3,907.90 proxy).
- **TBT:** arb-markdown recorded the lowest within-run value (11.400629 proxy).
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

The supporting JSON files are stored in the [retained AgMark archive](./generation-8c198165d61bac3531453fb579b581ae63536025e27b5bdf8c441e23f7c1da1e.agmark) (a ZIP container), not as loose files beside this Markdown report. Open the archive and inspect these members:

- `reports/generation-8c198165d61bac3531453fb579b581ae63536025e27b5bdf8c441e23f7c1da1e/report.json`: result tables, registered report sections and availability states.
- `reports/generation-8c198165d61bac3531453fb579b581ae63536025e27b5bdf8c441e23f7c1da1e/canonical-evidence.json`: full observation IDs, scores, measurement provenance and source references.
- `reports/generation-8c198165d61bac3531453fb579b581ae63536025e27b5bdf8c441e23f7c1da1e/report-manifest.json`: exact component identities and integrity hashes.

The link above opens the actual archive on GitHub. The original report and source evidence embedded in the archive remain unchanged.
