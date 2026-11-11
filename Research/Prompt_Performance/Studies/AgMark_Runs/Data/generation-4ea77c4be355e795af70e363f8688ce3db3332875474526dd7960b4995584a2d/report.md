# AgMark Individual Run Report

## Run Details

- **Benchmark:** arcgrav.authority-resolution.benchmark.core
- **Comparison Track:** arcgrav.authority-resolution.field-accuracy
- **Generation:** generation-4ea77c4be355e795af70e363f8688ce3db3332875474526dd7960b4995584a2d
- **Report Generated:** 2026-11-05T17:26:06.719482Z
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
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 119 | 536 | 20,576 | 51.0978% | 9,256.00 proxy | 2,074.00 proxy | 13.424299 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 1 | 3eadbfef768c | 1 | 2026-11-05T17:11:11.441102Z |
| arb-xml | 100.0000% | 21,136 | 10,896 | 233 | 650 | 21,786 | 48.4481% | 11,213.00 proxy | 4,081.00 proxy | 10.989214 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 2 | 6c16de6fb365 | 1 | 2026-11-05T17:11:26.861978Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 141 | 558 | 21,066 | 49.9317% | 10,992.00 proxy | 2,479.00 proxy | 15.283662 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 3 | 81605b323a75 | 1 | 2026-11-05T17:11:48.684737Z |
| arb-markdown | 100.0000% | 19,177 | 8,937 | 240 | 657 | 19,834 | 53.3973% | 11,365.00 proxy | 4,218.00 proxy | 10.894817 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 4 | 5ff154a710bb | 1 | 2026-11-05T17:12:04.295574Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 320 | 737 | 16,943 | 63.1865% | 14,111.00 proxy | 5,547.00 proxy | 11.635870 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 5 | 07fb076a4c1d | 1 | 2026-11-05T17:12:21.918937Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 150 | 567 | 21,687 | 48.4848% | 9,768.00 proxy | 2,616.00 proxy | 12.636042 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 6 | a9cb6f5e0898 | 2 | 2026-11-05T17:12:41.093554Z |
| arb-yaml | 100.0000% | 19,590 | 9,350 | 306 | 723 | 20,313 | 52.2716% | 13,940.00 proxy | 5,305.00 proxy | 11.959834 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 7 | cfb2723018c6 | 2 | 2026-11-05T17:12:56.758595Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 236 | 653 | 16,859 | 63.1865% | 11,164.00 proxy | 4,017.00 proxy | 10.961656 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 8 | c6cc99230d7d | 2 | 2026-11-05T17:13:15.068913Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 162 | 579 | 20,682 | 50.9377% | 11,547.00 proxy | 2,862.00 proxy | 15.025952 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 9 | fb743f8d9615 | 2 | 2026-11-05T17:13:32.587437Z |
| arb-common-prose | 100.0000% | 19,106 | 8,866 | 290 | 707 | 19,813 | 53.5957% | 12,047.00 proxy | 5,006.00 proxy | 9.973088 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 10 | 7679d68ffe07 | 2 | 2026-11-05T17:13:48.946296Z |
| arb-yaml | 100.0000% | 19,598 | 9,358 | 259 | 676 | 20,274 | 52.2502% | 13,189.00 proxy | 5,933.00 proxy | 10.749630 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 11 | 6a33becaea70 | 3 | 2026-11-05T17:14:07.564207Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 195 | 612 | 20,715 | 50.9377% | 10,447.00 proxy | 3,329.00 proxy | 11.649755 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 12 | e5430c91964e | 3 | 2026-11-05T17:14:28.156560Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 156 | 573 | 20,775 | 50.6881% | 10,021.00 proxy | 2,797.00 proxy | 12.629371 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 13 | cecd2e464c6c | 3 | 2026-11-05T17:14:44.784185Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 311 | 728 | 16,918 | 63.2489% | 12,588.00 proxy | 5,447.00 proxy | 9.822558 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 14 | 9a6fc9b0f258 | 3 | 2026-11-05T17:15:00.852294Z |
| arb-common-prose | 97.9167% | 20,040 | 9,800 | 160 | 577 | 20,617 | 51.0978% | 10,059.00 proxy | 2,869.00 proxy | 12.482639 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 15 | 7fa83acfdb56 | 3 | 2026-11-05T17:15:19.321008Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 184 | 601 | 20,633 | 51.1182% | 10,256.00 proxy | 3,119.00 proxy | 11.895000 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 16 | ce1e91653bf8 | 4 | 2026-11-05T17:15:36.124529Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 249 | 666 | 16,864 | 63.2177% | 11,946.00 proxy | 4,417.00 proxy | 11.321805 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 17 | fad6534dea23 | 4 | 2026-11-05T17:15:52.894595Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 215 | 632 | 20,834 | 50.6881% | 10,890.00 proxy | 3,618.00 proxy | 11.524564 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 18 | 0e05f8adfc3d | 4 | 2026-11-05T17:16:13.602178Z |
| arb-yaml | 100.0000% | 19,590 | 9,350 | 206 | 623 | 20,213 | 52.2716% | 10,656.00 proxy | 3,576.00 proxy | 11.382637 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 19 | f931499dfb8d | 4 | 2026-11-05T17:16:30.360174Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 177 | 594 | 20,697 | 50.9377% | 10,717.00 proxy | 3,069.00 proxy | 12.897133 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 20 | 0d391c0bd017 | 4 | 2026-11-05T17:16:47.640620Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 172 | 589 | 20,700 | 50.9174% | 9,954.00 proxy | 3,018.00 proxy | 11.795918 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 21 | c07591812e82 | 5 | 2026-11-05T17:17:04.632403Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 205 | 622 | 16,812 | 63.2489% | 10,728.00 proxy | 3,505.00 proxy | 11.631240 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 22 | 9f6c92e0cc70 | 5 | 2026-11-05T17:17:20.324121Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 242 | 659 | 21,779 | 48.4848% | 11,196.00 proxy | 4,214.00 proxy | 10.610942 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 23 | 05b0d056e6d7 | 5 | 2026-11-05T17:17:36.644985Z |
| arb-common-prose | 100.0000% | 20,024 | 9,784 | 297 | 714 | 20,738 | 51.1386% | 13,892.00 proxy | 5,130.00 proxy | 12.288920 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 24 | 520e47421ada | 5 | 2026-11-05T17:17:53.579360Z |
| arb-yaml | 100.0000% | 20,500 | 10,260 | 240 | 657 | 21,157 | 49.9512% | 11,171.00 proxy | 5,359.00 proxy | 8.859756 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 25 | 61b7904f161a | 5 | 2026-11-05T17:18:12.401629Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 307 | 724 | 21,232 | 49.9317% | 14,088.00 proxy | 5,345.00 proxy | 12.092669 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 26 | dfc4871dbf57 | 6 | 2026-11-05T17:18:29.977046Z |
| arb-markdown | 100.0000% | 20,095 | 9,855 | 335 | 752 | 20,847 | 50.9579% | 12,816.00 proxy | 5,637.00 proxy | 9.559254 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 27 | d0cc2f6e8bc8 | 6 | 2026-11-05T17:18:48.414666Z |
| arb-arcgrav | 100.0000% | 15,264 | 5,024 | 253 | 670 | 15,934 | 67.0860% | 13,100.00 proxy | 5,844.00 proxy | 10.846039 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 28 | b30e52c8f82b | 6 | 2026-11-05T17:19:09.400760Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 310 | 727 | 20,759 | 51.1182% | 12,560.00 proxy | 5,375.00 proxy | 9.896694 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 29 | 4f7a563f180c | 6 | 2026-11-05T17:19:26.910938Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 247 | 664 | 20,866 | 50.6881% | 12,755.00 proxy | 5,759.00 proxy | 10.552036 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 30 | 47023347a3ab | 6 | 2026-11-05T17:19:45.690751Z |
| arb-yaml | 100.0000% | 19,598 | 9,358 | 275 | 692 | 20,290 | 52.2502% | 11,990.00 proxy | 4,782.00 proxy | 10.431259 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 31 | 8159b1c2418a | 7 | 2026-11-05T17:20:04.760956Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 148 | 565 | 20,676 | 50.9174% | 9,720.00 proxy | 2,644.00 proxy | 12.546099 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 32 | b7d218055b6b | 7 | 2026-11-05T17:20:22.625778Z |
| arb-xml | 100.0000% | 21,136 | 10,896 | 285 | 702 | 21,838 | 48.4481% | 12,085.00 proxy | 4,880.00 proxy | 10.278174 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 33 | d2e826f94cae | 7 | 2026-11-05T17:20:38.851698Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 206 | 623 | 20,655 | 51.1182% | 10,505.00 proxy | 3,620.00 proxy | 11.069132 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 34 | c8969a1c9abf | 7 | 2026-11-05T17:20:58.128802Z |
| arb-arcgrav | 100.0000% | 15,272 | 5,032 | 245 | 662 | 15,934 | 67.0508% | 11,490.00 proxy | 4,281.00 proxy | 10.906203 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 35 | 48a99523b594 | 7 | 2026-11-05T17:21:14.684446Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 161 | 578 | 21,094 | 49.9123% | 9,723.00 proxy | 2,847.00 proxy | 11.916811 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 36 | ba00feaad2fd | 8 | 2026-11-05T17:21:31.753738Z |
| arb-markdown | 100.0000% | 20,119 | 9,879 | 331 | 748 | 20,867 | 50.8972% | 15,257.00 proxy | 5,766.00 proxy | 12.705489 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 37 | 7ebf269dec1d | 8 | 2026-11-05T17:21:47.992782Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 186 | 603 | 16,793 | 63.2489% | 10,185.00 proxy | 3,114.00 proxy | 11.745847 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 38 | eb2788e5b06e | 8 | 2026-11-05T17:22:08.507232Z |
| arb-xml | 100.0000% | 21,136 | 10,896 | 151 | 568 | 21,704 | 48.4481% | 11,355.00 proxy | 2,622.00 proxy | 15.402116 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 39 | 32c5edd44418 | 8 | 2026-11-05T17:22:26.011993Z |
| arb-common-prose | 97.9167% | 19,114 | 8,874 | 126 | 543 | 19,657 | 53.5733% | 9,081.00 proxy | 2,076.00 proxy | 12.924354 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 40 | 3a2d837bf727 | 8 | 2026-11-05T17:22:41.547109Z |
| arb-yaml | 65.5172% | 20,508 | 10,268 | 166 | 585 | 21,093 | 49.9317% | 10,602.00 proxy | 2,989.00 proxy | 13.035959 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 41 | 1538f6516b8f | 9 | 2026-11-05T17:22:58.048217Z |
| arb-markdown | 100.0000% | 20,119 | 9,879 | 270 | 687 | 20,806 | 50.8972% | 11,732.00 proxy | 4,478.00 proxy | 10.574344 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 42 | c9977000f60c | 9 | 2026-11-05T17:23:14.225119Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 218 | 635 | 20,667 | 51.1182% | 12,553.00 proxy | 3,792.00 proxy | 13.818612 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 43 | 8809024e157d | 9 | 2026-11-05T17:23:32.683090Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 247 | 664 | 20,866 | 50.6881% | 11,454.00 proxy | 4,823.00 proxy | 10.001508 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 44 | c7e0418b70b9 | 9 | 2026-11-05T17:23:49.947290Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 337 | 754 | 16,960 | 63.1865% | 14,353.00 proxy | 5,835.00 proxy | 11.312085 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 45 | 1a198a69d21f | 9 | 2026-11-05T17:24:07.755399Z |
| arb-xml | 100.0000% | 20,186 | 9,946 | 240 | 657 | 20,843 | 50.7282% | 11,348.00 proxy | 4,177.00 proxy | 10.931402 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 46 | ede10595bd6b | 10 | 2026-11-05T17:24:28.067600Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 227 | 644 | 21,152 | 49.9317% | 12,449.00 proxy | 3,916.00 proxy | 13.270607 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 47 | 7b1f346c1e41 | 10 | 2026-11-05T17:24:45.109804Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 238 | 655 | 16,853 | 63.2177% | 11,264.00 proxy | 4,122.00 proxy | 10.920489 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 48 | 01fc6ef4d5e1 | 10 | 2026-11-05T17:25:02.351698Z |
| arb-common-prose | 100.0000% | 20,048 | 9,808 | 281 | 698 | 20,746 | 51.0774% | 14,319.00 proxy | 6,397.00 proxy | 11.365854 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 49 | 3d917f357a47 | 10 | 2026-11-05T17:25:20.189612Z |
| arb-markdown | 100.0000% | 19,185 | 8,945 | 283 | 700 | 19,885 | 53.3750% | 12,050.00 proxy | 4,938.00 proxy | 10.174535 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 50 | 8487b3b6652f | 10 | 2026-11-05T17:25:39.219319Z |

### Treatment Total Averaged Results

Token and invocation counts sum retained observations, including retries. The primary result preserves its registered aggregation. Timing is the arithmetic mean of available observation measurements, not a sum; missing contributors are not imputed as zero and incomplete means are marked partial. Cache Read Fraction is summed eligible cached input divided by summed eligible input. Distinct Tool Calls counts unique tool identities across the treatment, not the sum of observation counts.

| Treatment | Accuracy | Input Tokens | Uncached Input | Reasoning Output Tokens | Output Tokens | Total Tokens | Cache Read Fraction | Average Inference Duration | Average TTFT | Average TBT | Average Direct TTFT | Average Direct TBT | Tool Calls | Distinct Tool Calls | Failed Tool Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arb-arcgrav | 100.0000% | 160,120 | 57,720 | 2,580 | 6,750 | 166,870 | 63.9520% | 12,092.90 proxy | 4,612.90 proxy | 11.110379 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-common-prose | 99.5833% | 198,500 | 96,100 | 2,191 | 6,361 | 204,861 | 51.5869% | 11,452.80 proxy | 3,945.80 proxy | 11.913859 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-markdown | 100.0000% | 199,226 | 96,826 | 2,313 | 6,483 | 205,709 | 51.3989% | 11,560.50 proxy | 3,995.90 proxy | 11.782330 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-xml | 100.0000% | 206,642 | 104,242 | 2,166 | 6,336 | 212,978 | 49.5543% | 11,208.50 proxy | 3,958.70 proxy | 11.555537 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-yaml | 96.5517% | 201,424 | 99,024 | 2,288 | 6,460 | 207,884 | 50.8380% | 11,880.00 proxy | 4,253.10 proxy | 11.898282 proxy | Unavailable | Unavailable | 0 | 0 | 0 |

## Notable Results and Exceptions

- **Accuracy:** arb-arcgrav 100.0000%; arb-common-prose 99.5833%; arb-markdown 100.0000%; arb-xml 100.0000%; arb-yaml 96.5517%.
- **Total Tokens:** arb-arcgrav recorded the lowest within-run value (166,870).
- **Uncached Input Tokens:** arb-arcgrav recorded the lowest within-run value (57,720).
- **Inference Duration:** arb-xml recorded the lowest within-run value (11,208.50 proxy).
- **TTFT:** arb-common-prose recorded the lowest within-run value (3,945.80 proxy).
- **TBT:** arb-arcgrav recorded the lowest within-run value (11.110379 proxy).
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

The supporting JSON files are stored in the [retained AgMark archive](./generation-4ea77c4be355e795af70e363f8688ce3db3332875474526dd7960b4995584a2d.agmark) (a ZIP container), not as loose files beside this Markdown report. Open the archive and inspect these members:

- `reports/generation-4ea77c4be355e795af70e363f8688ce3db3332875474526dd7960b4995584a2d/report.json`: result tables, registered report sections and availability states.
- `reports/generation-4ea77c4be355e795af70e363f8688ce3db3332875474526dd7960b4995584a2d/canonical-evidence.json`: full observation IDs, scores, measurement provenance and source references.
- `reports/generation-4ea77c4be355e795af70e363f8688ce3db3332875474526dd7960b4995584a2d/report-manifest.json`: exact component identities and integrity hashes.

The link above opens the actual archive on GitHub. The original report and source evidence embedded in the archive remain unchanged.
