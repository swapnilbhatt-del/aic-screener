# Trust and limits: how far the screener can be trusted, and where it breaks

For Kushal to read and agree before the system touches a real decision. Every number is computed from the pipeline's own files (`python -m aic.assurance`).

## The numbers

| Measure | Result |
|---|---|
| Blind backtest, 12 past memos | 6/12 bands agree; all scored Pass (same as 'always pass') |
| Ranking (AUC, in-sample) | total 0.88, founder 0.99, path 0.56 |
| Deciding reasons matched | passes 14/14, investments 3/15 |
| Claims extracted | 944, 0 invalid; 40/40 key figures recalled |
| Deterministic checks | 143 (27 fail, 1 unverifiable); reference script agrees 34/34 |
| Web findings | 198, 78 low confidence; 8/8 spot-checks confirmed; 62 questions not answerable |
| Founders confirmed by an outside source | 0 of 20 |

## What holds

- Arithmetic and cross-document checks: 143 checks, every input cited; the reference script agrees on 34/34 of its checks.
- Extraction: 944 claims, each quote verified on its page; 40/40 key figures recalled.
- Every score cites a page, a check or a URL with access date; totals, caps and bands are computed in code.
- Nothing is sent, booked or decided without a named human: enforced by database triggers and tested.

## Where it breaks

| Where | Numbers | Why it matters |
|---|---|---|
| Call/pass bands on narrative evidence | All 12 past memos scored Pass; band agreement 6/12, the same as 'always pass'. | Missing data scores 0, so a pre-revenue or narrative file cannot reach 70. The band would not have surfaced any of the fund's 6 investments. |
| Reasons for investing | Deciding reasons matched for passes 14/14, for investments 3/15. | It recognises why the fund says no far better than why it says yes; investment reasons lived in partner judgement the file does not record. |
| Founder evidence | 0 of 20 founders confirmed by any outside source. | Founder scores are capped at 4 and rest on the applicant's own words. F3 (candour) is read from text, with no call notes. |
| Web research quality | 78 of 198 findings are low confidence (search snippets); 8/8 spot-checked sources confirmed. | Funding amounts and market sizes from snippets can be wrong or stale; they are leads, and a low-confidence finding never moves a score on its own. |
| Portfolio conflict check (G1) | 68 portfolio companies found publicly; the fund's own list was not available. | An overlap with an unlisted portfolio company would be missed; weak-source overlaps may be false alarms. |
| Scorer consistency | One scoring pass per company by five agents; T2 sub-parts were read inconsistently until a code rule fixed it. | Run-to-run variance is not measured. A second independent pass would show how stable each score is. |
| In-sample validation | Ranking AUC 0.88 (total), 0.99 (founder), 0.56 (path) on 12 memos the rubric was built from. | These numbers are optimistic; the rubric quotes the same memos. Only new decided applications or the uneasy passes test it out of sample. |

## Terms to agree in advance (proposals; Kushal decides)

1. Use now as a reason-checker and ranking aid, not as a call/pass signal. *Basis: band agreement equals 'always pass' on the 12 memos.*
2. Before the band is used to skip reading an application: score the next 10 applications blind, before partners decide, and compare. Proposed bar: at least 8 of 10 agree, and no application the partners call is scored Pass. *Basis: the only out-of-sample test available; the bar is a proposal for Kushal to set.*
3. Any Hold, flag or material contradiction always goes to a partner. *Basis: already enforced in code.*
4. A low-confidence research finding never moves a score on its own. *Basis: 78 of 198 findings are low confidence.*
5. Weights and thresholds change only through the corrections log: a proposal after 3 similar corrections, accepted by a named partner. *Basis: Stage 6, enforced in code.*

Agreed by: ____________________   Date: ____________

## What the system could not find, and what that costs

| Missing | What was found | What it costs |
|---|---|---|
| The fund's investment thesis | Public line (fintech, deeptech, consumer tech, consumer brands) from press and the fund's site; sources disagree on sectors, cheque size and Fund II close (7 conflicts logged). | G2 (sector) and M3 (thesis fit) score against a reconstructed thesis. Riya's drift between the written thesis and what the fund backs is shown as two fields, not resolved. |
| Criteria and their precise definitions | Rebuilt from the 12 memos and partner notes as rubric v1 (draft). | The rubric is in-sample: its anchors quote the memos it is tested on. Agreement numbers are optimistic until tested on new decisions. |
| Anti-thesis exclusions | Only what the memos show (a business that exists only if a regulator changes the rules; models needing far more capital than a pre-seed cheque) and a third-party note excluding founders not fully committed. | G2 and G4 catch those patterns only; any other exclusion the partners apply is invisible to the system. |
| The full portfolio list | 68 companies from the fund's site, a directory and press; some may be from the earlier First Cheque vehicle. | G1 (conflict) can miss an overlap with an unlisted company, and may hold an applicant on a weak-source overlap. |
| Anything about applicants beyond their own deck | None of the 10 companies and none of the 20 founders has a findable web presence. | Founder criteria are capped at 4; S2 (integrity) can't reach 5; credentials can only be checked deck against form. |
| Call notes for applicants | Not in the pack. | F3 (candour) is judged from written text at low or medium confidence. |
| Cohort, bank or customer data | Only what each company chose to disclose. | T2 scores 0 for every undisclosed sub-part; some good companies score low for lack of disclosure (by design: missing scores 0). |
| Ledgerly and the three uneasy passes | Mentioned in the notes; not in the pack. | No out-of-sample test of whether the rubric would have caught the misses Kushal worries about. |
| Partner decisions on these 10 applications | None yet; all outcomes are undecided. | Corrections, reuse and weight proposals have no input until partners decide and correct. |

## Time and cost against Riya's nineteen days

- **Riya today:** 30 minutes per application, 19+ days a quarter (about 304 applications at 8 hours a day); 5.0 hours for a batch of 10.
- **System, batch of 10:** about 16.8 minutes of wall-clock with agents in parallel (68.0 agent-minutes in total, 6.8 per application), plus 3.3 seconds of code.
- **Tokens per application:** about 207,498 (extraction 33,087, research 87,760, scoring 70,973, research_fund (shared) 15,678). Model cost = tokens x your contracted per-token price. No price is assumed here; tokens are as reported by the agent runtime and include all input the agents read.
- **Still human:** A partner reads each card and decides (not measured yet: time it on the first real batch).; Approve each outreach email and calendar hold.; Confirm curated text contradictions and any 'no' or unclear founder reply.; Enter corrections with a one-line reason.; Check low-confidence research leads that matter to the decision.

Source: Agent runtime completion reports (subagent_tokens, duration_ms) for each agent run in the build session of 2026-11-19, plus timed runs of the code stages on the same machine. Tokens are as reported by the runtime; no price is applied here.
