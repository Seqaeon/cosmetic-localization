# Ground truth and provenance

Every item carries `gt_tier` and `gt_source`. The tier is the single column that does
more for credibility than doubling the dataset size, because it lets a reader weigh each
claim rather than taking all of them on the author's word.

| Tier | Source | Notes |
|---|---|---|
| 1 | Statute and regulation | Labour Act, Pension Reform Act, Lagos State Tenancy Law, NHIA Act, FCCPA, CBN and NERC instruments. Cite section numbers. |
| 2 | Institutional documentation | Bank published terms, NIS and FRSC guidelines, regulator FAQs, HMO published policy, NIBSS scheme rules. |
| 3 | Observable market data | Listed prices, published tariffs, advertised rents. **`gt_date` is required** — these move. |
| 4 | Practitioner knowledge | The author's own and that of people consulted. Unavoidable for how things actually work as opposed to how they are written down, which is exactly the gap under study. |

**Declared limitation.** Ground truth for N items derives from the author's practitioner
knowledge of Nigerian practice rather than documentary sources. Those items are marked
tier 4, and every headline number is reported both on the full set and on the
documentary-only (tier 1–2) subset as a robustness check.

## Where law and practice diverge

The most interesting category in the dataset, and the one almost nothing in the
literature measures. A model that recites the statute is not wrong in the way a benchmark
would score, and is useless in the way that matters.

Record both: what the instrument says, and what actually happens. Target ≥20 items.

Candidates already identified in the gate set:

| Item | Statute says | Practice is |
|---|---|---|
| `ten_001` | Lagos State Tenancy Law 2011 s.4(1) makes it unlawful to demand more than one year's rent in advance from a yearly tenant | Two years upfront is routine, especially for new tenants; the provision is essentially unenforced |
| `ten_002` | ss.13–16 set a notice ladder by tenancy type, then a court order; holding over is civil | Self-help eviction — locks changed, power cut — is common and rarely produces consequences |
| `hea_001` | NHIA Act 2022 s.14 makes health insurance mandatory for all residents | Enrolment covers a small minority; out-of-pocket payment at the point of care dominates |
| `hea_002` | National Health Act 2014 s.20 makes refusing emergency treatment an offence | A deposit before treatment is routinely demanded; prosecutions are rare |
| `hea_003` | PCN regulations restrict prescription-only medicines to sale on prescription | Dispensing without prescription is widespread and is the ordinary route |
| `com_001` | FCCPA 2018 ss.120–122 give rights to refund, repair or replacement | "No refund after purchase" is near-universal; enforcement is complaint-driven and slow |
| `emp_001` | Labour Act s.11 graduates notice by length of service | Terminal pay is routinely withheld pending a clearance process the Act does not provide for |
| `emp_003` | Labour Act ss.15–17 require payment at agreed intervals | Months of arrears are absorbed rather than litigated; the NICN runs to years |
| `gov_001` | NIS publishes processing timelines | Collection commonly exceeds them; in-person follow-up is part of the process, not an exception |
| `gov_003` | FRSC states production timelines in weeks | Collection runs to months; the temporary paper permit is the operative document |
| `uti_001` | NERC capping order limits billing for unmetered customers | Estimated billing persists at scale and capping is unevenly enforced |

## Per-item table

> **[FILL DURING AUTHORING.]** One row per released item: id, tier, source with section
> number or URL, date for tier 3, and a one-line note where law and practice diverge.

## External check

> **[OPTIONAL BUT WORTH THE EMAILS.]** Two or three local practitioners — an HR person, a
> lawyer, an accountant — reviewing a subset converts "one person's opinion" into
> "lightly validated". Acknowledge them here.
