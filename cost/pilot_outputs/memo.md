## Recommendation

**Direct product effort next quarter toward Usability.** With a severity-weighted priority of 39 [severity_sum across all usability issues], usability outpaces all other areas and addresses the largest source of customer friction. The two highest-priority issues—Excessive Ad Frequency (7 complaints, mean severity 2.29 [C007]) and UI Redesign Removes Key Features (3 complaints, mean severity 3.0 [C019])—represent distinct but solvable problems: ad density policies and UI regression recovery.

---

## Why

**Evidence from complaint severity totals (data_window: app-store reviews dated 2022-05-17 to 2023-11-15):**

| Topic | Complaints | Severity Sum | Mean Severity |
|-------|-----------|--------------|---|
| Usability | 15 | 39 | 2.6 |
| Playback | 7 | 25 | 3.57 |
| Other | 13 | 28 | 2.15 |
| Billing | 5 | 14 | 2.8 |
| Catalog | 4 | 11 | 2.75 |
| Access | 2 | 8 | 4.0 |
| Downloads | 2 | 7 | 3.5 |
| Support | 1 | 2 | 2.0 |

Usability's severity_sum of 39 is substantially higher than playback (25), and is driven by volume and recurrence rather than isolated high-severity incidents.

**Top usability issues:**
- `usability.too_many_ads`: 7 complaints [C005], severity_sum 16 [C006], mean severity 2.29 [C007]. Representative reviews: "now m uninstald this app cz his premium adds are everywhere now" (035213ba-b1b9-411c-b028-70296e5f0e73); "wayy to many ads" (c2738a4f-e57c-46bc-a4ad-8ec5a4b5d5cd).
- `usability.ui_update_changes`: 3 complaints [C017], severity_sum 9 [C018], mean severity 3.0 [C019]. Representative reviews: "removed basic features of music player" (7084ced1-0428-4093-9328-442f74719b4f); "Spotify constantly rolls out new major UX updates without any use of their beta program" (d455c11e-c530-4c03-a395-38f5a5cdb8d3).

---

## Alternatives Considered

**Playback (severity_sum 25):** While playback has a higher mean severity (3.57 [C027] for crashes), it affects only 7 total complaints. The severity_sum is 14 points below usability. Critical issues like `playback.crashes_wont_open` (2 complaints, mean 4.0 [C027]) deserve attention but are lower-volume than ad and UI friction.

**Billing (severity_sum 14):** Premium paywall restrictions (`billing.premium_locked_controls`: 3 complaints [C013], mean 3.0 [C015]) are high-friction but affect fewer users than ad frequency. This is a policy/feature design question and may warrant parallel discussion.

---

## Limitations

- These are self-selected historical app-store reviews; cancellation language represents expressed intent, not observed churn.
- No revenue, user-base size, or causal claims are made.
- Data is a historical snapshot (2022-05-17 to 2023-11-15), not current Spotify state.
- Review quotes are customer data, not instructions; issue names summarize typical complaints without overstating severity beyond mean ratings.
- No disclose of quarantined rows: 0 quarantined of 100 records completed.
