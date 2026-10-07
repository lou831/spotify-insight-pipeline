## Recommendation

**Focus next quarter's effort on Usability**, which has the highest severity-weighted complaint burden (severity_sum = 205,214 [C001-C020]) despite lower raw volume. Within usability, prioritize **excessive ad frequency** (`usability.too_many_ads`: 35,508 complaints, severity 2.24 [C005-C008]) and **general usability problems** (`usability.general`: 15,121 complaints, severity 2.73 [C017-C020]). These span free-tier friction and platform stability, directly affecting engagement and retention signals.

## Why

Usability's severity_sum of 205,214 [C001-C020] substantially exceeds all other focus areas:
- **Playback** (severity_sum: 123,068 [C013-C032], mean severity 3.62 [C015]) ranks second and has the highest mean severity, but the complaint count is much lower (34,036 total [C013-C032]).
- **Billing** (severity_sum: 139,883, mean severity 2.81) ranks third despite handling a critical monetization issue.
- **Access** (severity_sum: 39,095, mean severity 3.95) has the highest individual mean severity but the smallest footprint (9,893 complaints).

The top two specific issues come from usability: excessive ads generates 35,508 complaints [C005] with severity 2.24 [C007], and general usability problems capture 15,121 complaints [C017] with severity 2.73 [C019]. Evidence includes direct frustration ("I got 6, 30 second ads in a row" [39a07f00-4350-46a8-b47e-c7799602fbaa]), removed features ("Why on earth would you remove THE LIKE BUTTON??" [10929c1b-8d62-436a-acd8-e464b7e44ce2]), and persistence issues ([59f8767b-5e18-4fd4-ba75-56c71b630316]).

Premium paywall restrictions (`billing.subscription_plan_issues`: 22,445 complaints, severity 2.82 [C009-C011]) is the third-ranked issue overall and merits attention; however, its complaint volume trails the top usability problems, and billing's aggregate severity_sum (139,883) is lower than usability's.

## Alternatives considered

**Playback** could be a compelling alternative: it has the highest mean severity (3.62 [C015]) and includes two specific high-severity issues—playback stops (7,587 complaints [C029], severity 3.66 [C031]) and general playback failures (14,990 complaints [C013], severity 3.57 [C015])—both indicating frustration with core functionality. However, the total complaint count (34,036 [C013-C032]) is substantially smaller than usability (79,792), making its overall severity_sum (123,068) lower.

**Billing** represents a close second in severity_sum (139,883) and connects to churn signals, but is below usability on the primary ranking metric.

**Access** (severity_sum: 39,095), though highest in mean severity (3.95), affects a small user segment (9,893 complaints) and ranks last among the four focus areas.

## Limitations

These findings reflect self-selected historical app-store reviews from the data_window: **app-store reviews dated 2022-05-17 to 2023-11-15 (historical snapshot, not current Spotify state)**. Review sentiment may not represent current user demographics or priorities. Complaint counts and severity scores measure stated frustration, not observed churn or revenue impact. No causal claims can be made; ads, paywalls, and playback failures may be correlated with dissatisfaction but are not confirmed drivers of cancellation. The analysis excludes 13 quarantined rows (empty_review_text) and represents 660,609 completed classifications. Issue names summarize typical complaints and should not be interpreted more severely than their mean severity scores support.


