## Recommendation

Put next quarter's product effort into **usability**, starting with the free-tier listening experience: how often ads interrupt and the recent removal of controls users relied on. Usability has the largest severity-weighted complaint total of the four candidate areas (severity sum 205,214 across 79,792 complaints). Its biggest single issue is `usability.too_many_ads`: 35,508 complaints [C005], severity sum 79,637 [C006], mean severity 2.24 [C007].

## Why (evidence)

| Area | Complaints | Severity sum | Mean severity |
|---|---|---|---|
| Usability | 79,792 | 205,214 | 2.57 |
| Billing | 49,795 | 139,883 | 2.81 |
| Support | 759 | 2,225 | 2.93 |
| Playback | 34,036 | 123,068 | 3.62 |
| Access | 9,893 | 39,095 | 3.95 |

Area rows add up the issues in each topic; they are context, not separate claim IDs.

- **Ads** are the most common specific complaint. A typical review: "I got 6, 30 second ads in a row." (39a07f00-4350-46a8-b47e-c7799602fbaa).
- **Removed or changed controls** make up `usability.general`: 15,121 complaints [C017], mean severity 2.73 [C019]. Example: "Why on earth would you remove THE LIKE BUTTON??" (10929c1b-8d62-436a-acd8-e464b7e44ce2).
- The only issue ranked above ads is `other.general_dissatisfaction` (76,926 complaints [C001], mean severity 2.00 [C003]): generic "worst app" reviews that name no feature, so they cannot be acted on directly.

Caveat: usability leads because of **volume**. Its mean severity (2.57) means most of these complaints are annoyances rather than broken features.

## Alternatives considered

- **Billing/support** (billing severity sum 139,883; support 2,225). Main issues: `billing.subscription_plan_issues`, 22,445 complaints [C009], mean severity 2.82 [C011] ("Stop including every feature into Premium!", 3dd40007-b7ab-45ec-a658-0b6444151ad8), and `billing.premium_locked_controls`, 11,036 complaints [C025], mean severity 2.99 [C027] ("Won't even let you skip one song anymore.", 05ecab99-c305-49af-b78f-2629070860e0). Most are reactions to free-tier limits, which is a pricing decision more than a product defect. Choose this area if leadership is willing to revisit what the free tier includes.
- **Playback** (severity sum 123,068; mean severity 3.62). Fewer complaints, but each is more serious because music stops working: `playback.playback_stops`, 7,587 complaints [C029], mean severity 3.66 [C031] ("The recent update is making the songs pause every 10 seconds", 00ef7aa1-39aa-450e-9643-c47be81fb6ee). Fix these bugs in parallel through normal engineering work.
- **Access** (severity sum 39,095; mean severity 3.95; 9,893 complaints). The most severe per complaint (people are locked out) but the smallest volume. Handle with targeted login fixes.

## Limitations

- Evidence covers app-store reviews dated 2022-05-17 to 2023-11-15 (historical snapshot, not current Spotify state). Reviewers chose to post, so they are not a representative sample of all users.
- Cancellation language is expressed intent, not observed churn. The data has no revenue or plan information, so no revenue or causal claims are made.
- Labels come from automated models checked against a small hand-labeled sample and an independent verifier; individual labels can be wrong.
- Each complaint is counted in exactly one keyword-defined issue, so issue boundaries are approximate.
- 660,609 reviews were classified; 13 empty reviews were quarantined (empty_review_text) and excluded.
