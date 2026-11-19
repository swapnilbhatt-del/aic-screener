# Stage 3 run report: research

Date: 2026-11-19 (all sources accessed this date). Tests: 240 passed.
Cache: `data/research/<Company>.json` and `_fund.json` (gitignored; they contain founder searches). Hashes and spot-check log: `reports/stage3_cache_manifest.json`. Reruns read the cache; nothing is re-fetched unless a cache file is deleted.

## How it ran

- **Per-company briefs** (`python -m aic.research briefs`) list every testable claim with its Stage 1 claim id: market inputs, competitors and competition claims, founders and credentials, regulatory dependencies.
- **Six research agents** ran in parallel following `prompts/research.md`: 5 covered two companies each, 1 covered the fund's portfolio and thesis.
- **Every finding is validated in code** (`aic/research.py`). Each needs:
  - an http(s) URL that is not one of the applications' `.example` addresses
  - a source title, publisher, published date and an ISO access date
  - a stance and a confidence level
  - a quote of 25 words or fewer
  - the claim it tests, with any `claim_ref` resolving to a real Stage 1 claim or Stage 2 check
- **Conflicts must cite at least 2 findings.** Competitors must cite a finding, and funded competitors must give the amount.
- **Founder rule:** a founder is recorded only when a source names the founder at this company. Same-name people elsewhere were deliberately not recorded.

## Counts

| | Findings | Competitors (funded) | Contradicts application | Conflicts | Not found |
|---|---|---|---|---|---|
| CAPilot | 16 | 10 (4) | 7 | 2 | 6 |
| CareCorner | 22 | 8 (8) | 0 | 1 | 5 |
| EarnWise | 16 | 3 (3) | 6 | 2 | 6 |
| GrainKind | 19 | 8 (8) | 2 | 3 | 5 |
| Pumpwise | 13 | 6 (3) | 5 | 2 | 5 |
| RentRoute | 16 | 7 (2) | 8 | 2 | 7 |
| Settlr | 15 | 8 (5) | 1 | 1 | 6 |
| StockSathi | 14 | 6 (5) | 5 | 2 | 7 |
| Talkbook | 16 | 9 (8) | 8 | 2 | 6 |
| Yatrika | 16 | 9 (9) | 8 | 1 | 4 |
| Fund (portfolio, thesis) | 35 | 68 portfolio companies | n/a | 7 | 5 |
| **Total** | **198** | | | **25** | **62** |

**Confidence:** 62 high, 58 medium, 78 low. 88 findings say they rest partly on a search snippet the agent could not open (many sites returned 403). Low-confidence findings must not move a score on their own.

## Verified independently

I opened 8 of the most decision-relevant sources myself; **8 of 8 confirm the finding**:
- NoticeAI on ICAI's AI portal drafts notice replies
- Convin's USD 6.5M Series A
- Infinite Uptime's USD 35M Series C
- the ASI 2024-25 count of 2.67 lakh factories, with the state figures
- Tata's acquisition of Soulfull
- WTTC's INR 14.64 trillion domestic tourism spend
- RBI's rule that only regulated entities may lend and that pool accounts are banned
- Qwipo's presence in tier-2 and tier-3 Telangana towns

That is a sample, not a full audit. The remaining 190 findings are validated for form only.

Agent commentary I checked and found wrong: one agent said Settlr's TAM and SAM multiply correctly. Stage 2 shows all three of Settlr's market sizes are 10× low. The comment was not written into the cache.

## No public record for any applicant or founder

**None of the 10 companies and none of the 20 founders has a findable web presence.** All 20 founder searches are `not_found`. Same-name people were found for several founders and deliberately not recorded. This means no founder credential can be checked against an outside source, and no public-record contradiction of a material field was found.

## Findings that matter most, by company

| Company | Finding | Effect on the application |
|---|---|---|
| CAPilot | AI notice-reply tools exist (NoticeAI on ICAI's portal, GST Reply AI, TaxReplies); about 1.6 lakh practising CAs in about 95k firms; no source for INR 1.4 lakh Cr | contradicts "AI notice replies: only us"; market headline unsourced |
| CareCorner | 8 funded primary-care competitors (Even Healthcare USD 30M Series A, Clinikk, CureBay); NSS 2025: median out-of-pocket outpatient spend at public facilities is zero; Telangana Clinical Establishments Act being enforced | free public alternative to a paid clinic; no INR 6,000 per-household source |
| EarnWise | KarmaLife (INR 44 Cr), Refyne (USD 82M), Jify (USD 10M); RBI: only regulated entities may lend, no pool accounts; draft unregulated-lending bill | lending from the founder's savings conflicts with RBI rules; INR 12,000 average advance contradicted by earnings data; 10M workforce supported (1–1.2 crore gig workers) |
| GrainKind | Soulfull (Tata), Yoga Bar (ITC, about INR 645 Cr), Slurrp Farm, Troo Good; branded healthy snacks about Rs 6,000 Cr (Bain) | "large cereal brands: millet rare" contradicted; TAM about 15× the branded healthy-snack market |
| Pumpwise | Infinite Uptime (Pune office, about USD 65M), Presage Insights (small and mid-sized plants), Nanoprecise; ASI: 2.67 lakh registered factories in India | "imported systems" is not the only alternative; ~300K MSMEs with 20+ motors exceeds all registered factories; wireless approval via self-declaration, so cheap certification questions the 25% of the raise set aside for it |
| RentRoute | PhonePe, Paytm and CRED stopped card rent payments after RBI's payment aggregator directions of Sep 2025; aggregators may collect only for onboarded merchants; competitors relaunching at a 1.5–2% fee | the regulatory risk the form names had already happened before incorporation; "no direct competitors" contradicted; no source for INR 1.5 lakh Cr |
| Settlr | M1xchange, RXIL, CredFlow (now its own NBFC), KredX, Vayana, Razorpay; about 95% of Udyam firms are micro (turnover ≤ INR 5 Cr) | INR 4.5 Cr per SME looks high; crowded field the application doesn't name |
| StockSathi | Qwipo (Hyderabad, tier-2/3 Telangana), VilCart (Telangana/AP), Flipkart Wholesale 14-day credit, Jumbotail, Udaan; RBI: first-loss guarantees only from a lending-service company, capped at 5%; lending as a principal business without registration not permitted | "mostly metro" and "credit limited" contradicted; both the deck's and the form's credit structures raise regulatory questions |
| Talkbook | Convin (USD 6.5M), Arrowhead (USD 3M, Hindi/Tamil/Telugu, BFSI), Darwix, Salesken; DPDP Rules 2025 consent; India sales workforce about 1.5M (TeamLease 2018) vs deck 7M | "no India-first player" contradicted; TAM input unsupported |
| Yatrika | WTTC: domestic visitor spend INR 14.64 lakh Cr (2023); 30 Sundays (Rs 61 Cr), WanderOn, Holiday Tribe, Airial; MoSPI: most trips are pilgrimage or social visits | INR 3 lakh Cr headline unsourced and about 5× below WTTC; funded AI planners exist |

## Fund: portfolio and thesis (for gates G1 and G2)

- **68 portfolio companies** came from AIC's own site (18 cards plus founder stories), the VCBacked directory and press. 13 China-based entries belonging to a same-name investor were excluded. Some names may be from the earlier First Cheque vehicle. The list is still not authoritative: Tracxn and Crunchbase were not readable.
- **35 overlap flags; 5 rated "direct":**

| Applicant | Portfolio company | Basis | Source strength |
|---|---|---|---|
| Talkbook | MeetRecord (now Outdoo AI) | AI sales-call intelligence | strong; the notes already flag this overlap |
| StockSathi | SuperK | supplies and franchises small-town kiranas (AP, next to Telangana) | listed on AIC's own site; model partly from a snippet |
| GrainKind | Taakat | jowar/ragi multigrain healthy snacks | Preqin snippet only |
| GrainKind | MomsMade | clean-label traditional family snacks | single aggregator |
| Settlr | Mannjal | SME credit vs lending infrastructure for lenders | sources conflict on Mannjal's model |

  The other 30 flags are "adjacent" (e.g. CareCorner with Arva Health and Piiko). No applicant has zero flags, because the agent over-flagged as the notes asked.
- **Stated thesis:**
  - Fund I (2022): USD 10–11M, sector-agnostic, pre-seed and seed.
  - Fund II (launched Mar 2025): INR 200 Cr target with a first close of INR 85–100 Cr. Described as sector-agnostic with a focus on consumer tech, deeptech, fintech and consumer brands. Cheques up to INR 5 Cr.
  - Website today: USD 250–600K cheques.
  - Sources conflict on the first-close amount, the sector list, cheque size, Fund I size and headquarters (Mumbai vs Bangalore).

## Assumed

1. Findings marked low confidence rest on search snippets. Treat them as leads, not evidence.
2. The portfolio list is public-source only. G1 still can't be run against the full portfolio; that needs the fund's own list.
3. "Contradicts" means the source disagrees with the application's claim as worded. It doesn't mean the company is wrong. For example, the WTTC tourism figure may measure something broader than the deck intended.

## Open questions for you

1. **G1 Hold vs Flag.** Your rubric says any portfolio overlap means Hold. With 35 flags, every applicant would be on Hold. My proposal: **Hold only for the 5 "direct" overlaps**, with the 30 adjacent ones shown on the card as information. Decide whether any of the 5 should drop: Settlr–Mannjal's sources conflict, and GrainKind–Taakat and GrainKind–MomsMade rest on one weak source each.
2. **Founder evidence ceiling.** Your scoring anchor for 5 needs evidence "checkable from an outside source". No founder could be checked, so strictly applied, no founder criterion can reach 5 for any applicant (prior scores gave 5s to Pumpwise, Settlr, Talkbook, StockSathi and Yatrika). Apply it strictly (max 4 where specific and internally consistent), or allow 5 on the application text alone?
3. **Public-record contradictions outside the material fields** (competition claims, market sizes) would feed M1 and M2, not the integrity cap. Confirm.
