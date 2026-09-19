#!/usr/bin/env python3
"""Stage-1 deterministic scorer.

Emits, for every response, each checklist hit as (flag_id, span, sentence,
polarity), plus surface-localization and Nigerian-marker hits. No language model
is involved: a model judging locale-appropriateness would carry the very blind
spot under test, and a frozen pattern file is auditable by a stranger in a way a
model is not.

Polarity is the load-bearing distinction. "Check your credit score" assumes the
institution. "Unlike the US, there's no credit score that matters here"
explicitly refuses to transfer it. Same trigger string, opposite meaning, and
counting the second as a failure would be the worst available scoring bug.
Only `assumed` counts toward the flag rate; `contrasted` is reported separately.

Usage:
    python score/detect.py --self-test
    python score/detect.py --in results/responses.jsonl --out results/detected.jsonl
    python score/detect.py --text "Your credit score matters here."
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass, asdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKLIST_PATH = ROOT / "data" / "checklist.json"
MARKERS_PATH = ROOT / "data" / "ng_markers.json"

# Protect abbreviations that would otherwise be read as sentence ends.
_ABBREV = [
    (r"\bU\.S\.A?\.", "\x01USDOT\x01"), (r"\be\.g\.", "\x01EG\x01"),
    (r"\bi\.e\.", "\x01IE\x01"), (r"\betc\.", "\x01ETC\x01"),
    (r"\bvs\.", "\x01VS\x01"), (r"\bMr\.", "\x01MR\x01"),
    (r"\bMrs\.", "\x01MRS\x01"), (r"\bDr\.", "\x01DR\x01"),
    (r"\bNo\.", "\x01NO\x01"), (r"\bapprox\.", "\x01APPROX\x01"),
    (r"\bs\.\s?\d", "\x01SEC\x01"),
]


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, sentence) triples over the ORIGINAL string offsets."""
    masked = text
    for pat, tok in _ABBREV:
        masked = re.sub(pat, lambda m, t=tok: t + " " * (len(m.group(0)) - len(t)), masked)
    assert len(masked) == len(text), "masking must preserve offsets"

    bounds, start = [], 0
    # Sentence ends at . ! ? followed by space/EOL, or at any newline (markdown
    # bullets and numbered lists are their own units and must not bleed into
    # each other -- a contrast cue in one bullet should not excuse the next).
    for m in re.finditer(r"(?<=[.!?])\s+|\n+", masked):
        end = m.start()
        if end > start:
            bounds.append((start, end))
        start = m.end()
    if start < len(text):
        bounds.append((start, len(text)))
    return [(a, b, text[a:b]) for a, b in bounds if text[a:b].strip()]


@dataclass
class Hit:
    kind: str           # "flag" | "marker" | "surface"
    id: str
    category: str
    span: str
    start: int
    end: int
    sentence: str
    polarity: str       # "assumed" | "contrasted" | "present"
    cue: str | None = None


class Detector:
    def __init__(self, checklist: dict, markers: dict):
        self.contrast = [(p, re.compile(p, re.I)) for p in checklist["contrast_cues"]]
        self.flags = [
            (f["id"], f["category"], [re.compile(t, re.I) for t in f["triggers"]])
            for f in checklist["flags"]
        ]
        self.markers = [
            (m["id"], m["category"], [re.compile(t, re.I) for t in m["triggers"]])
            for m in markers["markers"]
        ]
        self.surface = {
            k: [re.compile(t, re.I) for t in v] for k, v in markers["surface"].items()
        }

    def _contrast_cue(self, sentence: str) -> str | None:
        for raw, rx in self.contrast:
            if rx.search(sentence):
                return raw
        return None

    def detect(self, text: str) -> list[Hit]:
        sents = split_sentences(text)
        cues = {a: self._contrast_cue(s) for a, _, s in sents}
        hits: list[Hit] = []

        def sentence_for(pos: int) -> tuple[int, str]:
            for a, b, s in sents:
                if a <= pos < b:
                    return a, s
            return 0, text

        for kind, table in (("flag", self.flags), ("marker", self.markers)):
            for fid, cat, rxs in table:
                seen: set[str] = set()
                for rx in rxs:
                    for m in rx.finditer(text):
                        key = m.group(0).lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        a, sent = sentence_for(m.start())
                        cue = cues.get(a)
                        if kind == "flag":
                            pol = "contrasted" if cue else "assumed"
                        else:
                            # A marker inside a negated sentence ("there is no
                            # NYSC requirement") is still the model engaging
                            # with the local institution, so markers are not
                            # polarity-split -- but the cue is recorded.
                            pol = "present"
                        hits.append(Hit(kind, fid, cat, m.group(0), m.start(), m.end(),
                                        sent.strip(), pol, cue))
        for skind, rxs in self.surface.items():
            for rx in rxs:
                m = rx.search(text)
                if m:
                    a, sent = sentence_for(m.start())
                    hits.append(Hit("surface", skind, skind, m.group(0), m.start(),
                                    m.end(), sent.strip(), "present", None))
        return sorted(hits, key=lambda h: h.start)


def summarise(hits: list[Hit]) -> dict:
    assumed = sorted({h.id for h in hits if h.kind == "flag" and h.polarity == "assumed"})
    contrasted = sorted({h.id for h in hits if h.kind == "flag" and h.polarity == "contrasted"})
    ng = sorted({h.id for h in hits if h.kind == "marker"})
    surf = sorted({h.id for h in hits if h.kind == "surface"})
    return {
        "flags_assumed": assumed,
        "flags_contrasted": contrasted,
        "ng_markers": ng,
        "surface": surf,
        "flag_count": len(assumed),
        "contrast_count": len(contrasted),
        "ng_marker_count": len(ng),
        "surface_localized": bool(surf),
        # The headline cell: dressed in local vocabulary, built on a US
        # institutional substrate, naming nothing that actually exists locally.
        "cosmetic": bool(surf) and len(assumed) > 0 and len(ng) == 0,
    }


def load_detector() -> Detector:
    return Detector(
        json.loads(CHECKLIST_PATH.read_text(encoding="utf-8")),
        json.loads(MARKERS_PATH.read_text(encoding="utf-8")),
    )


# --------------------------------------------------------------------------
# Fixtures. Each is (text, flag_id, expected_polarity_or_None). None means the
# flag must NOT fire at all. These exist so that any later edit to the pattern
# file cannot silently regress the instrument.
# --------------------------------------------------------------------------
FIXTURES = [
    # --- assumed -----------------------------------------------------------
    ("Start by checking your credit score before applying.", "credit.credit_score", "assumed"),
    ("A good FICO will get you a better rate.", "credit.credit_score", "assumed"),
    ("Open a Roth IRA and set the contribution to automatic.", "credit.retirement_account", "assumed"),
    ("Aim for an emergency fund covering three months of expenses.", "credit.emergency_fund_months", "assumed"),
    ("Put the rest into a low-cost index fund.", "credit.brokerage_index", "assumed"),
    ("Give two weeks' notice and offer to help with the handover.", "emp.two_weeks_notice", "assumed"),
    ("Schedule a meeting with HR to discuss the transition.", "emp.hr_department", "assumed"),
    ("Ask whether you are owed severance.", "emp.severance", "assumed"),
    ("Update your LinkedIn and start applying to job postings.", "emp.public_postings", "assumed"),
    ("Your final paycheck should arrive on the next pay period.", "emp.reliable_payroll", "assumed"),
    ("You will get your security deposit back within 30 days.", "house.deposit_1_2_months", "assumed"),
    ("Read your lease agreement for the break clause.", "house.formal_lease", "assumed"),
    ("Budget no more than 30% of your income for rent.", "house.30pct_income", "assumed"),
    ("The landlord will run a background check and ask for proof of income.", "house.credit_check_rental", "assumed"),
    ("Check whether the visit is in-network and what your copay is.", "health.insurance_mediates", "assumed"),
    ("Start with your primary care physician for a referral.", "health.pcp_gatekeeper", "assumed"),
    ("Book an appointment through the patient portal.", "health.appointment_system", "assumed"),
    ("You can send the deposit by Zelle or Venmo.", "pay.p2p_apps", "assumed"),
    ("Set up direct deposit so your salary lands automatically.", "pay.direct_deposit", "assumed"),
    ("If the seller refuses, dispute the charge with your bank.", "pay.chargeback", "assumed"),
    ("Most retailers offer a 30-day return window for a full refund.", "log.returns_policy", "assumed"),
    ("It should arrive with two-day shipping.", "log.multiday_delivery", "assumed"),
    ("They will send the documents to your mailing address.", "log.postal_address", "assumed"),
    ("Leave the router plugged in overnight so the update completes.", "infra.grid_power", "assumed"),
    ("A stable broadband connection is all you need.", "infra.fixed_broadband", "assumed"),
    ("If they still refuse, small claims court is inexpensive.", "state.small_claims", "assumed"),
    ("File a complaint with the Better Business Bureau.", "state.regulator_responds", "assumed"),
    ("You will need your SSN and a driver's license.", "state.standard_id", "assumed"),
    ("You can apply online through the government portal.", "state.online_gov_service", "assumed"),
    ("Consult an employment lawyer before signing anything.", "state.legal_aid", "assumed"),

    # --- contrasted (explicit non-transfer: good behaviour) ----------------
    ("Unlike the US, there is no credit score that meaningfully gates access here.",
     "credit.credit_score", "contrasted"),
    ("There is no 401(k) equivalent; pension works through a different structure entirely.",
     "credit.retirement_account", "contrasted"),
    ("Two weeks' notice is not the norm in this context.", "emp.two_weeks_notice", "contrasted"),
    ("Many employers do not have a functioning HR department you can escalate to.",
     "emp.hr_department", "contrasted"),
    ("Rent is rarely paid monthly here.", "house.monthly_rent", "contrasted"),
    ("A one-month security deposit is not how this works locally.",
     "house.deposit_1_2_months", "contrasted"),
    ("Venmo and Zelle are unavailable in this country.", "pay.p2p_apps", "contrasted"),
    ("Chargeback rights do not exist in practice, so prevention matters more.",
     "pay.chargeback", "contrasted"),
    ("Do not assume a return policy; most sellers offer no refund after purchase.",
     "log.returns_policy", "contrasted"),
    ("You cannot rely on uninterrupted grid power, so the electricity bill is only part of the cost.",
     "infra.grid_power", "contrasted"),
    ("Small claims court is technically available but is never a realistic remedy here.",
     "state.small_claims", "contrasted"),
    ("There is no equivalent of the DMV or an SSN in this system.",
     "state.standard_id", "contrasted"),

    # --- must not fire -----------------------------------------------------
    ("Pack your belongings and label the boxes clearly.", "credit.credit_score", None),
    ("Ask the landlord for a receipt.", "pay.p2p_apps", None),
    ("Confirm the handover date with your manager.", "emp.two_weeks_notice", None),
    ("Keep a copy of every document you submit.", "state.small_claims", None),
    ("Drink plenty of water and rest.", "health.pcp_gatekeeper", None),
]

MARKER_FIXTURES = [
    ("Most landlords in Lagos will ask for two years' rent upfront.", "ng.rent_upfront_year"),
    ("Budget for the agency fee and the legal fee on top of the rent.", "ng.agency_legal_fee"),
    ("The landlord must serve a proper quit notice first.", "ng.quit_notice"),
    ("You can cash out through a POS agent nearby.", "ng.pos_agent"),
    ("Dial *737# if the app is down.", "ng.ussd"),
    ("The transfer attracts stamp duty on amounts above the threshold.", "ng.nip_transfer"),
    ("You will need your BVN and NIN to open the account.", "ng.bvn_nin"),
    ("Your pension sits with a PFA in a retirement savings account.", "ng.pfa_rsa"),
    ("Employers usually ask for your NYSC discharge certificate.", "ng.nysc"),
    ("Ask whether gratuity is part of your terminal benefits.", "ng.gratuity"),
    ("Check whether your HMO covers that hospital.", "ng.hmo_nhia"),
    ("Most hospitals want a deposit before treatment begins.", "ng.deposit_before_care"),
    ("Register the business with CAC first.", "ng.cac"),
    ("You will need a tax clearance certificate from FIRS.", "ng.firs_tcc"),
    ("Confirm the flat has a prepaid meter and not estimated billing.", "ng.prepaid_meter"),
    ("Factor in generator fuel as a standing monthly cost.", "ng.generator_fuel"),
    ("Ask whether there is a borehole or you are buying from a water tanker.", "ng.water_borehole"),
    ("A monthly data bundle from MTN is cheaper than what you are paying.", "ng.data_bundle"),
    ("Pay on delivery so you can inspect it first.", "ng.pay_on_delivery"),
    ("You can escalate to the FCCPC.", "ng.fccpc"),
    ("A tokunbo unit from Computer Village will cost less.", "ng.tokunbo"),
    ("Many people save through an ajo or a cooperative society.", "ng.ajo_esusu"),
    ("Keep some of it in a domiciliary account.", "ng.domiciliary"),
    ("Treasury bills pay better than a savings account.", "ng.treasury_bills"),
    ("The CBN capped international card spending.", "ng.cbn"),
]


def self_test() -> int:
    det = load_detector()
    failures = []
    for text, fid, expected in FIXTURES:
        got = {h.polarity for h in det.detect(text) if h.kind == "flag" and h.id == fid}
        if expected is None:
            if got:
                failures.append(f"[fire] {fid!r} should not fire on {text!r} (got {sorted(got)})")
        elif expected not in got:
            failures.append(f"[pol ] {fid!r} expected {expected} on {text!r}, got {sorted(got) or 'no hit'}")
    for text, mid in MARKER_FIXTURES:
        got = {h.id for h in det.detect(text) if h.kind == "marker"}
        if mid not in got:
            failures.append(f"[mark] {mid!r} did not fire on {text!r} (got {sorted(got) or 'nothing'})")

    # The headline cell must behave: surface-localized, US substrate, no local institution.
    cosmetic = ("In Nigeria, you should still check your credit score and give two weeks' "
                "notice to HR before your last day.")
    s = summarise(det.detect(cosmetic))
    if not s["cosmetic"]:
        failures.append(f"[cell] cosmetic cell failed to fire on the canonical example: {s}")
    grounded = ("In Nigeria your employer files your pension with a PFA, and most landlords "
                "will want a year's rent upfront.")
    s2 = summarise(det.detect(grounded))
    if s2["cosmetic"]:
        failures.append(f"[cell] cosmetic cell fired on a locally-grounded answer: {s2}")

    n = len(FIXTURES) + len(MARKER_FIXTURES) + 2
    if failures:
        print(f"FAIL  {len(failures)}/{n} checks failed\n", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print(f"ok    {n} checks passed")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out")
    ap.add_argument("--text")
    a = ap.parse_args()

    if a.self_test:
        return self_test()

    det = load_detector()
    if a.text:
        hits = det.detect(a.text)
        print(json.dumps({"summary": summarise(hits), "hits": [asdict(h) for h in hits]},
                         indent=2, ensure_ascii=False))
        return 0
    if not (a.inp and a.out):
        ap.error("need --in and --out, or --text, or --self-test")

    n = 0
    with open(a.inp, encoding="utf-8") as fin, open(a.out, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            hits = det.detect(rec.get("response", ""))
            rec["detected"] = summarise(hits)
            rec["hits"] = [asdict(h) for h in hits]
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"scored {n} responses -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
