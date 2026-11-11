# AgMark Individual Run Report

## Run Details

- **Benchmark:** arcgrav.authority-resolution.benchmark.core
- **Comparison Track:** arcgrav.authority-resolution.field-accuracy
- **Generation:** generation-2f4eaa54d275c1b97bb079fd2bf69e759f73b18684c1ad35b0ca02634ee64cc7
- **Report Generated:** 2026-11-05T18:02:04.662128Z
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
| arb-markdown | 100.0000% | 20,119 | 9,879 | 203 | 620 | 20,739 | 50.8972% | 10,720.00 proxy | 3,562.00 proxy | 11.563813 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 1 | 5ff154a710bb | 1 | 2026-11-05T17:47:18.197443Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 336 | 753 | 21,269 | 49.9123% | 14,611.00 proxy | 5,825.00 proxy | 11.683511 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 2 | 81605b323a75 | 1 | 2026-11-05T17:47:34.820085Z |
| arb-arcgrav | 88.8889% | 15,272 | 5,032 | 321 | 765 | 16,037 | 67.0508% | 12,915.00 proxy | 7,156.00 proxy | 7.537958 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 3 | 07fb076a4c1d | 1 | 2026-11-05T17:47:54.949477Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 202 | 619 | 21,739 | 48.4848% | 12,343.00 proxy | 3,530.00 proxy | 14.260518 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 4 | 6c16de6fb365 | 1 | 2026-11-05T17:48:13.359668Z |
| arb-common-prose | 100.0000% | 19,114 | 8,874 | 279 | 696 | 19,810 | 53.5733% | 11,908.00 proxy | 4,770.00 proxy | 10.270504 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 5 | 3eadbfef768c | 1 | 2026-11-05T17:48:30.390380Z |
| arb-markdown | 100.0000% | 20,127 | 9,887 | 142 | 559 | 20,686 | 50.8769% | 11,211.00 proxy | 2,487.00 proxy | 15.634409 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 6 | fb743f8d9615 | 2 | 2026-11-05T17:48:50.662375Z |
| arb-common-prose | 100.0000% | 20,048 | 9,808 | 238 | 655 | 20,703 | 51.0774% | 11,291.00 proxy | 4,117.00 proxy | 10.969419 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 7 | 7679d68ffe07 | 2 | 2026-11-05T17:49:06.889383Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 279 | 696 | 21,212 | 49.9123% | 13,480.00 proxy | 6,398.00 proxy | 10.189928 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 8 | cfb2723018c6 | 2 | 2026-11-05T17:49:24.817423Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 206 | 623 | 21,751 | 48.4665% | 10,807.00 proxy | 3,569.00 proxy | 11.636656 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 9 | a9cb6f5e0898 | 2 | 2026-11-05T17:49:45.213452Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 237 | 654 | 16,844 | 63.2489% | 12,724.00 proxy | 5,744.00 proxy | 10.689127 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 10 | c6cc99230d7d | 2 | 2026-11-05T17:50:01.740055Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 370 | 787 | 16,985 | 63.2177% | 13,624.00 proxy | 6,297.00 proxy | 9.321883 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 11 | 9a6fc9b0f258 | 3 | 2026-11-05T17:50:19.349554Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 189 | 606 | 21,734 | 48.4665% | 10,366.00 proxy | 3,243.00 proxy | 11.773554 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 12 | cecd2e464c6c | 3 | 2026-11-05T17:50:38.822075Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 285 | 702 | 20,734 | 51.1182% | 12,356.00 proxy | 4,972.00 proxy | 10.533524 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 13 | 7fa83acfdb56 | 3 | 2026-11-05T17:50:56.380539Z |
| arb-yaml | 100.0000% | 19,598 | 9,358 | 212 | 629 | 20,227 | 52.2502% | 10,455.00 proxy | 3,556.00 proxy | 10.985669 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 14 | 6a33becaea70 | 3 | 2026-11-05T17:51:14.819826Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 192 | 609 | 20,720 | 50.9174% | 10,513.00 proxy | 3,343.00 proxy | 11.792763 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 15 | e5430c91964e | 3 | 2026-11-05T17:51:31.293012Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 256 | 673 | 20,705 | 51.1182% | 14,853.00 proxy | 4,452.00 proxy | 15.477679 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 16 | ce1e91653bf8 | 4 | 2026-11-05T17:51:48.567496Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 268 | 685 | 21,813 | 48.4665% | 13,461.00 proxy | 4,674.00 proxy | 12.846491 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 17 | 0e05f8adfc3d | 4 | 2026-11-05T17:52:09.944177Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 114 | 531 | 20,642 | 50.9174% | 9,019.00 proxy | 1,913.00 proxy | 13.407547 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 18 | 0d391c0bd017 | 4 | 2026-11-05T17:52:28.286834Z |
| arb-yaml | 81.1321% | 19,582 | 9,342 | 225 | 642 | 20,224 | 52.2929% | 12,590.00 proxy | 3,915.00 proxy | 13.533541 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 19 | f931499dfb8d | 4 | 2026-11-05T17:52:43.214872Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 262 | 679 | 16,869 | 63.2489% | 11,697.00 proxy | 4,538.00 proxy | 10.558997 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 20 | fad6534dea23 | 4 | 2026-11-05T17:53:00.455208Z |
| arb-markdown | 100.0000% | 20,095 | 9,855 | 272 | 689 | 20,784 | 50.9579% | 13,327.00 proxy | 4,709.00 proxy | 12.526163 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 21 | c07591812e82 | 5 | 2026-11-05T17:53:18.522557Z |
| arb-xml | 100.0000% | 20,202 | 9,962 | 260 | 677 | 20,879 | 50.6881% | 11,637.00 proxy | 4,779.00 proxy | 10.144970 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 22 | 05b0d056e6d7 | 5 | 2026-11-05T17:53:36.480796Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 177 | 594 | 20,626 | 51.1182% | 11,702.00 proxy | 3,062.00 proxy | 14.569983 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 23 | 520e47421ada | 5 | 2026-11-05T17:53:55.037882Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 209 | 626 | 16,816 | 63.2489% | 10,752.00 proxy | 3,632.00 proxy | 11.392000 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 24 | 9f6c92e0cc70 | 5 | 2026-11-05T17:54:10.968750Z |
| arb-yaml | 100.0000% | 20,508 | 10,268 | 160 | 577 | 21,085 | 49.9317% | 11,356.00 proxy | 2,729.00 proxy | 14.977431 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 25 | 61b7904f161a | 5 | 2026-11-05T17:54:27.348106Z |
| arb-arcgrav | 100.0000% | 16,206 | 5,966 | 268 | 685 | 16,891 | 63.1865% | 11,849.00 proxy | 4,689.00 proxy | 10.467836 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 26 | b30e52c8f82b | 6 | 2026-11-05T17:54:43.892335Z |
| arb-common-prose | 100.0000% | 20,032 | 9,792 | 190 | 607 | 20,639 | 51.1182% | 11,797.00 proxy | 3,165.00 proxy | 14.244224 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 27 | 4f7a563f180c | 6 | 2026-11-05T17:55:02.644899Z |
| arb-yaml | 100.0000% | 19,582 | 9,342 | 229 | 646 | 20,228 | 52.2929% | 12,850.00 proxy | 3,979.00 proxy | 13.753488 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 28 | dfc4871dbf57 | 6 | 2026-11-05T17:55:18.840392Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 264 | 681 | 21,801 | 48.4848% | 13,253.00 proxy | 6,066.00 proxy | 10.569118 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 29 | 47023347a3ab | 6 | 2026-11-05T17:55:38.889756Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 182 | 599 | 20,710 | 50.9174% | 10,317.00 proxy | 3,175.00 proxy | 11.943144 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 30 | d0cc2f6e8bc8 | 6 | 2026-11-05T17:55:56.620602Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 254 | 671 | 21,187 | 49.9123% | 11,526.00 proxy | 4,422.00 proxy | 10.602985 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 31 | 8159b1c2418a | 7 | 2026-11-05T17:56:13.121643Z |
| arb-common-prose | 97.9167% | 20,040 | 9,800 | 242 | 659 | 20,699 | 51.0978% | 13,548.00 proxy | 6,406.00 proxy | 10.854103 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 32 | c8969a1c9abf | 7 | 2026-11-05T17:56:30.963409Z |
| arb-xml | 100.0000% | 21,136 | 10,896 | 268 | 685 | 21,821 | 48.4481% | 11,808.00 proxy | 4,741.00 proxy | 10.331871 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 33 | d2e826f94cae | 7 | 2026-11-05T17:56:48.240600Z |
| arb-markdown | 100.0000% | 20,111 | 9,871 | 166 | 583 | 20,694 | 50.9174% | 10,008.00 proxy | 2,846.00 proxy | 12.305842 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 34 | b7d218055b6b | 7 | 2026-11-05T17:57:06.157397Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 174 | 591 | 16,781 | 63.2489% | 10,158.00 proxy | 3,027.00 proxy | 12.086441 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 35 | 48a99523b594 | 7 | 2026-11-05T17:57:21.703176Z |
| arb-markdown | 100.0000% | 19,185 | 8,945 | 197 | 614 | 19,799 | 53.3750% | 12,127.00 proxy | 4,899.00 proxy | 11.791191 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 36 | 7ebf269dec1d | 8 | 2026-11-05T17:57:37.347620Z |
| arb-yaml | 100.0000% | 20,524 | 10,284 | 244 | 661 | 21,185 | 49.8928% | 11,407.00 proxy | 4,265.00 proxy | 10.821212 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 37 | ba00feaad2fd | 8 | 2026-11-05T17:57:53.807983Z |
| arb-xml | 100.0000% | 21,120 | 10,880 | 131 | 548 | 21,668 | 48.4848% | 9,426.00 proxy | 2,232.00 proxy | 13.151737 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 38 | 32c5edd44418 | 8 | 2026-11-05T17:58:12.662301Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 173 | 590 | 20,630 | 51.0978% | 10,170.00 proxy | 3,010.00 proxy | 12.156197 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 39 | 3a2d837bf727 | 8 | 2026-11-05T17:58:28.002913Z |
| arb-arcgrav | 100.0000% | 15,272 | 5,032 | 241 | 658 | 15,930 | 67.0508% | 13,147.00 proxy | 5,680.00 proxy | 11.365297 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 40 | eb2788e5b06e | 8 | 2026-11-05T17:58:44.720040Z |
| arb-arcgrav | 100.0000% | 16,190 | 5,950 | 228 | 645 | 16,835 | 63.2489% | 11,018.00 proxy | 4,138.00 proxy | 10.683230 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 41 | 1a198a69d21f | 9 | 2026-11-05T17:59:01.864835Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 189 | 606 | 21,122 | 49.9123% | 12,035.00 proxy | 4,878.00 proxy | 11.829752 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 42 | 1538f6516b8f | 9 | 2026-11-05T17:59:19.524398Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 240 | 657 | 20,697 | 51.0978% | 11,720.00 proxy | 4,198.00 proxy | 11.466463 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 43 | 8809024e157d | 9 | 2026-11-05T17:59:35.704958Z |
| arb-markdown | 100.0000% | 20,103 | 9,863 | 263 | 680 | 20,783 | 50.9377% | 13,073.00 proxy | 5,912.00 proxy | 10.546392 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 44 | c9977000f60c | 9 | 2026-11-05T17:59:52.997117Z |
| arb-xml | 100.0000% | 21,136 | 10,896 | 211 | 628 | 21,764 | 48.4481% | 10,785.00 proxy | 3,646.00 proxy | 11.385965 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 45 | c7e0418b70b9 | 9 | 2026-11-05T18:00:10.583283Z |
| arb-yaml | 100.0000% | 20,516 | 10,276 | 218 | 635 | 21,151 | 49.9123% | 12,389.00 proxy | 5,230.00 proxy | 11.291798 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 46 | 7b1f346c1e41 | 10 | 2026-11-05T18:00:27.076694Z |
| arb-markdown | 100.0000% | 19,185 | 8,945 | 264 | 681 | 19,866 | 53.3750% | 11,704.00 proxy | 4,579.00 proxy | 10.477941 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 47 | 8487b3b6652f | 10 | 2026-11-05T18:00:43.790242Z |
| arb-common-prose | 100.0000% | 20,040 | 9,800 | 177 | 594 | 20,634 | 51.0978% | 10,740.00 proxy | 3,068.00 proxy | 12.937605 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 48 | 3d917f357a47 | 10 | 2026-11-05T18:01:01.638859Z |
| arb-xml | 100.0000% | 21,128 | 10,888 | 220 | 637 | 21,765 | 48.4665% | 11,055.00 proxy | 3,778.00 proxy | 11.441824 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 49 | ede10595bd6b | 10 | 2026-11-05T18:01:18.085620Z |
| arb-arcgrav | 100.0000% | 16,198 | 5,958 | 283 | 700 | 16,898 | 63.2177% | 13,199.00 proxy | 4,909.00 proxy | 11.859800 proxy | Unavailable | Unavailable | 0 | 0 | 0 | 50 | 01fc6ef4d5e1 | 10 | 2026-11-05T18:01:36.245009Z |

### Treatment Total Averaged Results

Token and invocation counts sum retained observations, including retries. The primary result preserves its registered aggregation. Timing is the arithmetic mean of available observation measurements, not a sum; missing contributors are not imputed as zero and incomplete means are marked partial. Cache Read Fraction is summed eligible cached input divided by summed eligible input. Distinct Tool Calls counts unique tool identities across the treatment, not the sum of observation counts.

| Treatment | Accuracy | Input Tokens | Uncached Input | Reasoning Output Tokens | Output Tokens | Total Tokens | Cache Read Fraction | Average Inference Duration | Average TTFT | Average TBT | Average Direct TTFT | Average Direct TBT | Tool Calls | Distinct Tool Calls | Failed Tool Calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arb-arcgrav | 98.8889% | 160,096 | 57,696 | 2,593 | 6,790 | 166,886 | 63.9616% | 12,108.30 proxy | 4,981.00 proxy | 10.596257 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-common-prose | 99.7917% | 199,450 | 97,050 | 2,257 | 6,427 | 205,877 | 51.3412% | 12,008.50 proxy | 4,122.00 proxy | 12.347970 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-markdown | 100.0000% | 199,258 | 96,858 | 1,995 | 6,165 | 205,423 | 51.3907% | 11,201.90 proxy | 3,742.50 proxy | 12.198920 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-xml | 100.0000% | 210,346 | 107,946 | 2,219 | 6,389 | 216,735 | 48.6817% | 11,494.10 proxy | 4,025.80 proxy | 11.754270 proxy | Unavailable | Unavailable | 0 | 0 | 0 |
| arb-yaml | 98.1132% | 202,374 | 99,974 | 2,346 | 6,516 | 208,890 | 50.5994% | 12,269.90 proxy | 4,519.70 proxy | 11.966932 proxy | Unavailable | Unavailable | 0 | 0 | 0 |

## Notable Results and Exceptions

- **Accuracy:** arb-arcgrav 98.8889%; arb-common-prose 99.7917%; arb-markdown 100.0000%; arb-xml 100.0000%; arb-yaml 98.1132%.
- **Total Tokens:** arb-arcgrav recorded the lowest within-run value (166,886).
- **Uncached Input Tokens:** arb-arcgrav recorded the lowest within-run value (57,696).
- **Inference Duration:** arb-markdown recorded the lowest within-run value (11,201.90 proxy).
- **TTFT:** arb-markdown recorded the lowest within-run value (3,742.50 proxy).
- **TBT:** arb-arcgrav recorded the lowest within-run value (10.596257 proxy).
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

The supporting JSON files are stored in the [retained AgMark archive](./generation-2f4eaa54d275c1b97bb079fd2bf69e759f73b18684c1ad35b0ca02634ee64cc7.agmark) (a ZIP container), not as loose files beside this Markdown report. Open the archive and inspect these members:

- `reports/generation-2f4eaa54d275c1b97bb079fd2bf69e759f73b18684c1ad35b0ca02634ee64cc7/report.json`: result tables, registered report sections and availability states.
- `reports/generation-2f4eaa54d275c1b97bb079fd2bf69e759f73b18684c1ad35b0ca02634ee64cc7/canonical-evidence.json`: full observation IDs, scores, measurement provenance and source references.
- `reports/generation-2f4eaa54d275c1b97bb079fd2bf69e759f73b18684c1ad35b0ca02634ee64cc7/report-manifest.json`: exact component identities and integrity hashes.

The link above opens the actual archive on GitHub. The original report and source evidence embedded in the archive remain unchanged.
