#!/usr/bin/env python3
"""Generate the frozen scoring instruments.

Emits data/checklist.json (US-default presuppositions) and data/ng_markers.json
(locally-grounded markers). Run once, commit the output, then freeze: any later
edit must be recorded in data/CHECKLIST_CHANGELOG.md with a reason and a new
version, because tuning the instrument after seeing results would invalidate
the study.
"""
import hashlib
import json
import pathlib

VERSION = "1.0.0"
FROZEN_AT = "2026-09-19"
ROOT = pathlib.Path(__file__).resolve().parent.parent

# Cues that, appearing in the same sentence as a trigger, flip the polarity from
# "the answer assumes this institution" to "the answer explicitly says it does
# not apply here". Explicit non-transfer is good behaviour and is measured
# separately -- counting it as a failure would be the single worst scoring bug
# available, so these are deliberately generous. The human confirmation pass
# resolves anything ambiguous.
CONTRAST_CUES = [
    r"\bunlike\b",
    r"\bin contrast\b",
    r"\bwhereas\b",
    r"\bas opposed to\b",
    r"\brather than\b",
    r"\binstead of\b",
    r"\bdiffers?\b",
    r"\bdifferent from\b",
    r"\bnot (?:the case|common|typical|standard|usual|how|applicable|really a thing|widely)\b",
    r"\bno (?:such|equivalent|real|meaningful|formal|functioning|reliable|direct)\b",
    r"\b(?:does|do|did|is|are|was|were|will|would|can|could)\s*n[o']t\b",
    r"\b(?:do|does|did|is|are|was|were|will|would|can|could|may|might)\s+not\b",
    r"\bnever\b",
    r"\brarely\b",
    r"\bseldom\b",
    r"\buncommon\b",
    r"\batypical\b",
    r"\bless common\b",
    r"\bwithout\b",
    r"\blacks?\b",
    r"\blacking\b",
    r"\babsent\b",
    r"\bnon-?existent\b",
    r"\bdoes ?n[o']t exist\b",
    r"\bdo ?n[o']t exist\b",
    r"\bthere is no\b",
    r"\bthere are no\b",
    r"\bthere is ?n[o']t\b",
    r"\bunavailable\b",
    r"\bnot available\b",
    r"\bin the (?:US|U\.S\.?|USA|United States|UK|West)\b",
    r"\b(?:American|Western|US-based|U\.S\.-based)\b",
    r"\bmay not apply\b",
    r"\bdoes not apply\b",
    r"\bwo ?n[o']t (?:apply|help|work|be)\b",
    r"\bunlikely\b",
    r"\bhard to come by\b",
    r"\bnot how (?:it|this|things)\b",
]

# id, category, label, triggers
FLAGS = [
    # ---- credit & finance -------------------------------------------------
    ("credit.credit_score", "credit_finance", "A consumer credit score exists and gates access",
     [r"\bcredit score\b", r"\bcredit rating\b", r"\bFICO\b", r"\bcredit history\b",
      r"\bcredit report\b", r"\bcreditworth\w*\b"]),
    ("credit.consumer_credit", "credit_finance", "Consumer credit (cards, personal loans) is normally accessible",
     [r"\bcredit cards?\b", r"\bpersonal loans?\b", r"\bline of credit\b",
      r"\bunsecured loans?\b", r"\bbuy now,? pay later\b", r"\bBNPL\b"]),
    ("credit.mortgage", "credit_finance", "A mortgage is a normal route to home ownership",
     [r"\bmortgages?\b", r"\bhome loans?\b", r"\bdown ?payment\b", r"\bpre-?approv\w+ for a\b",
      r"\bescrow\b", r"\brefinanc\w+\b"]),
    ("credit.retirement_account", "credit_finance", "US/UK-style retirement vehicles",
     [r"\b401\s?\(?k\)?\b", r"\bIRA\b", r"\bRoth\b", r"\bISA\b", r"\b403\s?\(?b\)?\b",
      r"\bemployer match\w*\b", r"\bSocial Security (?:benefits?|check|income)\b"]),
    ("credit.emergency_fund_months", "credit_finance", "The 3-6 month emergency fund rule, unqualified",
     [r"\b(?:three|3|six|6|3\s*(?:-|to|–)\s*6|three\s*(?:-|to|–)\s*six)\s*months?\D{0,30}\b(?:expenses|emergency fund|savings|living costs)\b",
      r"\bemergency fund\b"]),
    ("credit.brokerage_index", "credit_finance", "Brokerage / index funds as the default investing vehicle",
     [r"\bindex funds?\b", r"\bS&P 500\b", r"\bVanguard\b", r"\bFidelity\b", r"\bETFs?\b",
      r"\bbrokerage account\b", r"\bmutual funds?\b", r"\brobo-?advis\w+\b"]),

    # ---- employment -------------------------------------------------------
    ("emp.written_contract", "employment", "A written, enforceable employment contract is standard",
     [r"\bemployment contract\b", r"\bwritten contract\b", r"\byour contract\b",
      r"\bcontract terms\b", r"\boffer letter\b"]),
    ("emp.at_will", "employment", "At-will employment",
     [r"\bat-?will\b", r"\bterminate (?:you|your employment) at any time\b",
      r"\bwithout cause\b"]),
    ("emp.hr_department", "employment", "A functioning HR department exists and can be relied on",
     [r"\bHR\b", r"\bhuman resources\b", r"\bpeople (?:team|ops|operations)\b",
      r"\bHRBP\b", r"\bexit interview\b"]),
    ("emp.two_weeks_notice", "employment", "Two weeks' notice as the resignation norm",
     [r"\btwo weeks'? notice\b", r"\b2 weeks'? notice\b", r"\bstandard notice period\b",
      r"\bcustomary\D{0,20}notice\b"]),
    ("emp.severance", "employment", "Severance as a normal entitlement",
     [r"\bseverance\b", r"\bredundancy pay\b", r"\bexit package\b", r"\bgarden leave\b"]),
    ("emp.public_postings", "employment", "Jobs are found through public postings",
     [r"\bLinkedIn\b", r"\bIndeed\b", r"\bGlassdoor\b", r"\bjob boards?\b",
      r"\bjob postings?\b", r"\bapply online\b", r"\bATS\b", r"\brecruiters? (?:will|reach)\b"]),
    ("emp.unemployment_benefits", "employment", "Unemployment insurance / benefits",
     [r"\bunemployment (?:benefits?|insurance|claim)\b", r"\bjobseeker'?s? allowance\b",
      r"\bfile for unemployment\b"]),
    ("emp.health_coverage_tied", "employment", "Health coverage is tied to employment and continues after exit",
     [r"\bCOBRA\b", r"\bhealth (?:insurance|coverage|benefits?)\D{0,40}\b(?:employer|job|work|company)\b",
      r"\b(?:employer|company|workplace)\D{0,30}\bhealth (?:insurance|coverage|plan)\b"]),
    ("emp.pto_accrual", "employment", "Accrued paid leave is tracked and paid out",
     [r"\bPTO\b", r"\bpaid time off\b", r"\baccrued (?:leave|vacation|days)\b",
      r"\bvacation days?\b", r"\bpaid out\b"]),
    ("emp.reliable_payroll", "employment", "Salary arrives on schedule through payroll",
     [r"\bpay ?cheques?\b", r"\bpay ?checks?\b", r"\bpayroll\b", r"\bfinal pay ?(?:cheque|check)\b",
      r"\bnext pay period\b", r"\bpay stub\b", r"\bW-?2\b", r"\b1099\b"]),

    # ---- housing ----------------------------------------------------------
    ("house.monthly_rent", "housing", "Rent is paid monthly",
     [r"\bmonthly rent\b", r"\brent (?:each|every|per) month\b", r"\brent is due\b",
      r"\bmonth'?s rent\b", r"\brent payments?\b",
      r"\brent\w*\b[^.!?\n]{0,25}\bmonthly\b", r"\bmonthly\b[^.!?\n]{0,25}\brent\w*\b"]),
    ("house.deposit_1_2_months", "housing", "A security deposit of one to two months",
     [r"\bsecurity deposit\b", r"\bdamage deposit\b",
      r"\b(?:one|two|1|2)\D{0,15}months?'? (?:rent as a )?deposit\b"]),
    ("house.formal_lease", "housing", "A formal written lease with standard protections",
     [r"\blease agreement\b", r"\byour lease\b", r"\blease terms?\b", r"\bsublet\b",
      r"\blease break\w*\b", r"\bbreak (?:your|the) lease\b"]),
    ("house.tenant_dispute_body", "housing", "Accessible landlord-tenant dispute resolution",
     [r"\btenants?'? rights?\b", r"\btenancy board\b", r"\bhousing (?:authority|tribunal|court)\b",
      r"\blandlord-?tenant (?:board|court|law|dispute)\b", r"\brent control\b"]),
    ("house.credit_check_rental", "housing", "The landlord runs credit / reference / background checks",
     [r"\bbackground check\b", r"\breference check\b", r"\brental history\b",
      r"\bcredit check\b", r"\bproof of income\b", r"\bco-?signer\b", r"\bguarantor\b"]),
    ("house.renters_insurance", "housing", "Renters insurance is normal",
     [r"\brenters'? insurance\b", r"\bcontents insurance\b", r"\bhome insurance\b"]),
    ("house.30pct_income", "housing", "The 30%-of-income rent rule",
     [r"\b(?:30|thirty)\s?%\D{0,30}\b(?:income|salary|pay)\b",
      r"\b(?:income|salary|pay)\D{0,30}\b(?:30|thirty)\s?%\b"]),

    # ---- healthcare -------------------------------------------------------
    ("health.employer_insurance", "healthcare", "Employer-provided health insurance",
     [r"\bemployer-?(?:provided|sponsored)\b", r"\bgroup health plan\b",
      r"\bopen enrollment\b", r"\bACA\b", r"\bmarketplace plan\b", r"\bMedicaid\b", r"\bMedicare\b"]),
    ("health.insurance_mediates", "healthcare", "Insurance mediates access to care",
     [r"\bco-?pay\w*\b", r"\bdeductible\b", r"\bin-?network\b", r"\bout-?of-?network\b",
      r"\bpre-?authorization\b", r"\bclaims? (?:form|process|submit)\w*\b", r"\bcoinsurance\b",
      r"\byour insurance (?:will|should|may|might|covers?)\b"]),
    ("health.pcp_gatekeeper", "healthcare", "A primary care physician is the entry point",
     [r"\bprimary care (?:physician|provider|doctor)\b", r"\bPCP\b", r"\bGP\b",
      r"\byour (?:regular )?doctor\b", r"\bfamily (?:doctor|physician)\b",
      r"\breferral (?:to|from) a specialist\b"]),
    ("health.appointment_system", "healthcare", "Care is accessed by booking an appointment",
     [r"\bbook an appointment\b", r"\bschedule an appointment\b", r"\bmake an appointment\b",
      r"\bpatient portal\b", r"\bappointment slots?\b"]),
    ("health.prescription_required", "healthcare", "Pharmacy access is gated by prescription",
     [r"\bprescription\b", r"\brefill\b", r"\bpharmacist will\b", r"\bover-?the-?counter\b"]),
    ("health.emergency_services", "healthcare", "A responsive emergency service exists",
     [r"\b911\b", r"\b999\b", r"\bcall an ambulance\b", r"\bemergency services\b",
      r"\bER\b", r"\bemergency room\b", r"\bA&E\b"]),

    # ---- payments ---------------------------------------------------------
    ("pay.p2p_apps", "payments", "US/Western peer-to-peer payment apps",
     [r"\bVenmo\b", r"\bZelle\b", r"\bCash ?App\b", r"\bPayPal\b", r"\bApple Pay\b",
      r"\bGoogle Pay\b", r"\bWise\b", r"\bRevolut\b"]),
    ("pay.direct_deposit", "payments", "Direct deposit / ACH / wire as the normal rail",
     [r"\bdirect deposit\b", r"\bACH\b", r"\bwire transfers?\b", r"\brouting number\b",
      r"\bIBAN\b", r"\bSWIFT\b", r"\bstanding order\b", r"\bdirect debit\b"]),
    ("pay.card_ubiquity", "payments", "Cards are accepted essentially everywhere",
     [r"\bdebit cards?\b", r"\btap to pay\b", r"\bcontactless\b", r"\bswipe your card\b",
      r"\bcard on file\b", r"\bautopay\b", r"\bauto-?pay\b"]),
    ("pay.chargeback", "payments", "Chargeback / bank dispute rights are usable",
     [r"\bcharge ?backs?\b", r"\bdispute the charge\b", r"\bdispute it with your bank\b",
      r"\bfraud protection\b", r"\bpurchase protection\b", r"\bSection 75\b"]),
    ("pay.cheques", "payments", "Cheques are a normal instrument",
     [r"\bwrite a (?:check|cheque)\b", r"\bpersonal (?:check|cheque)\b", r"\bcashier'?s (?:check|cheque)\b",
      r"\bmoney order\b"]),
    ("pay.card_rewards", "payments", "Rewards/points optimization is a live consideration",
     [r"\bcash ?back\b", r"\brewards? points?\b", r"\bmiles\b", r"\bsign-?up bonus\b"]),

    # ---- logistics --------------------------------------------------------
    ("log.multiday_delivery", "logistics", "Reliable multi-day / next-day delivery",
     [r"\btwo-?day (?:shipping|delivery)\b", r"\bnext-?day (?:shipping|delivery)\b",
      r"\bfree shipping\b", r"\bPrime\b", r"\btracking number\b", r"\bUPS\b", r"\bFedEx\b",
      r"\bUSPS\b", r"\bRoyal Mail\b"]),
    ("log.postal_address", "logistics", "Reliable street addressing and mail delivery",
     [r"\bmailing address\b", r"\bin the mail\b", r"\bmailed to you\b", r"\bpost(?:ed)? to your address\b",
      r"\bZIP code\b", r"\bpostcode\b", r"\bmail ?box\b", r"\bcertified mail\b"]),
    ("log.returns_policy", "logistics", "Returns and refunds are a default consumer right",
     [r"\breturn polic\w+\b", r"\breturn window\b", r"\b(?:14|30|60|90)-?day returns?\b",
      r"\bfull refund\b", r"\bmoney-?back guarantee\b", r"\breturn it for a refund\b",
      r"\bno-?questions-?asked\b"]),

    # ---- infrastructure ---------------------------------------------------
    ("infra.grid_power", "infrastructure", "Uninterrupted mains electricity is assumed",
     [r"\bplug it in\b", r"\bkeep it charged\b", r"\belectricity bill\b", r"\butility bill\b",
      r"\bpower outage\w*\b", r"\bleave it running\b", r"\bplugged in overnight\b"]),
    ("infra.fixed_broadband", "infrastructure", "Reliable fixed broadband is assumed",
     [r"\bbroadband\b", r"\bwi-?fi\b", r"\bhome internet\b", r"\bfibre\b", r"\bfiber\b",
      r"\binternet plan\b", r"\bunlimited data\b", r"\bstream\w*\b"]),
    ("infra.municipal_water", "infrastructure", "Piped municipal water is assumed",
     [r"\btap water\b", r"\bwater bill\b", r"\bmunicipal water\b", r"\bwater utility\b",
      r"\bwater company\b"]),
    ("infra.public_transit", "infrastructure", "A functioning public transit system is an option",
     [r"\bpublic transit\b", r"\bpublic transport\w*\b", r"\bsubway\b", r"\bmetro\b",
      r"\btransit pass\b", r"\bcommuter rail\b", r"\bthe bus schedule\b"]),

    # ---- state & legal ----------------------------------------------------
    ("state.small_claims", "state_legal", "Small claims court is a usable remedy",
     [r"\bsmall claims\b", r"\bfile a (?:claim|suit|case) in court\b",
      r"\btake (?:them|him|her) to court\b", r"\bsue (?:them|him|her|the)\b"]),
    ("state.regulator_responds", "state_legal", "A regulator or ombudsman will act on a complaint",
     [r"\bfile a complaint with\b", r"\bombuds\w+\b", r"\bCFPB\b", r"\bFTC\b",
      r"\bBetter Business Bureau\b", r"\bBBB\b", r"\bregulator\w*\b",
      r"\bconsumer protection agency\b", r"\bFCA\b", r"\bTrading Standards\b"]),
    ("state.public_records", "state_legal", "Public records are searchable and accessible",
     [r"\bpublic records?\b", r"\bland registry\b", r"\btitle search\b",
      r"\bcounty (?:clerk|recorder)\b", r"\bFOIA\b", r"\bcompanies house\b"]),
    ("state.standard_id", "state_legal", "US/UK-style identity and tax infrastructure",
     [r"\bSSN\b", r"\bsocial security number\b", r"\bDMV\b", r"\bIRS\b", r"\bHMRC\b",
      r"\bNational Insurance number\b", r"\bdriver'?s license\b", r"\bW-?9\b", r"\bFAFSA\b"]),
    ("state.online_gov_service", "state_legal", "Government processes complete online end to end",
     [r"\bapply online\b", r"\bgovernment (?:portal|website)\b", r"\bonline (?:application|renewal)\b",
      r"\bdownload the form from\b", r"\bsubmit (?:it )?electronically\b",
      r"\b\.gov\b", r"\bgov\.uk\b"]),
    ("state.legal_aid", "state_legal", "A lawyer or legal aid is accessible and affordable",
     [r"\bconsult (?:a|an|your) (?:lawyer|attorney|solicitor)\b",
      r"\blegal aid\b", r"\bfree legal (?:advice|clinic)\b", r"\bemployment lawyer\b",
      r"\bpro bono\b"]),
]


def build_checklist():
    return {
        "version": VERSION,
        "frozen_at": FROZEN_AT,
        "description": (
            "Frozen checklist of institutional presuppositions characteristic of a US/Western "
            "default world model. A response is flagged for a given id when a trigger matches "
            "AND no contrast cue appears in the same sentence. Polarity 'assumed' counts toward "
            "the flag rate; polarity 'contrasted' is reported separately as explicit non-transfer, "
            "which is desirable behaviour."
        ),
        "scoring_note": (
            "Stage 1 is deterministic and auditable. Stage 2 is human confirmation of the emitted "
            "spans. No language model is used as a judge at any point, because a model judging "
            "locale-appropriateness carries the blind spot under test."
        ),
        "contrast_cues": CONTRAST_CUES,
        "flags": [
            {"id": i, "category": c, "label": lab, "triggers": t}
            for (i, c, lab, t) in FLAGS
        ],
    }


NG_MARKERS = [
    ("ng.rent_upfront_year", "tenancy", "Rent demanded a year or more upfront",
     [r"\b(?:one|two|1|2|three|3)\s*years?'?\s*rent\b", r"\brent upfront\b",
      r"\bannual rent\b", r"\byearly rent\b", r"\bupfront\D{0,20}\byears?\b"]),
    ("ng.agency_legal_fee", "tenancy", "Agency / agreement / legal / caution fees",
     [r"\bagency fee\b", r"\bagreement fee\b", r"\blegal fee\b", r"\bcaution (?:fee|deposit)\b",
      r"\bservice charge\b", r"\bagent'?s? (?:fee|commission)\b"]),
    ("ng.quit_notice", "tenancy", "Statutory quit notice",
     [r"\bquit notice\b", r"\bnotice to quit\b", r"\bseven days'? notice of owner'?s intention\b"]),
    ("ng.tenancy_law", "tenancy", "Nigerian tenancy statute named",
     [r"\bTenancy Law\b", r"\bRecovery of Premises\b", r"\bLagos State Tenancy Law\b"]),
    ("ng.pos_agent", "payments", "POS agent / agency banking",
     [r"\bPOS (?:agent|operator|vendor)\b", r"\bagency banking\b", r"\bmobile money agent\b"]),
    ("ng.ussd", "payments", "USSD banking",
     [r"\bUSSD\b", r"\*\d{3}#", r"\bbank(?:ing)? (?:short ?)?code\b", r"\bdial \*\d"]),
    ("ng.nip_transfer", "payments", "NIP / NIBSS instant transfer and its charges",
     [r"\bNIBSS\b", r"\bNIP\b", r"\binstant transfer\b", r"\bstamp duty\b",
      r"\btransfer (?:charge|levy)\b", r"\bEMTL\b"]),
    ("ng.fintech_apps", "payments", "Nigerian fintech rails",
     [r"\bOPay\b", r"\bPalmPay\b", r"\bKuda\b", r"\bMoniepoint\b", r"\bPaga\b",
      r"\bFlutterwave\b", r"\bPaystack\b"]),
    ("ng.bvn_nin", "identity", "BVN / NIN identity rails",
     [r"\bBVN\b", r"\bNIN\b", r"\bNIMC\b", r"\bbank verification number\b",
      r"\bnational identification number\b"]),
    ("ng.pfa_rsa", "employment", "Pension under the Nigerian PFA/RSA regime",
     [r"\bPFA\b", r"\bRSA\b", r"\bpension fund administrator\b", r"\bretirement savings account\b",
      r"\bPenCom\b", r"\bPension Reform Act\b"]),
    ("ng.nysc", "employment", "NYSC as a structuring fact",
     [r"\bNYSC\b", r"\byouth service\b", r"\bcorps? member\b", r"\bcorper\b",
      r"\bdischarge certificate\b"]),
    ("ng.gratuity", "employment", "Gratuity / terminal benefits",
     [r"\bgratuity\b", r"\bterminal benefits?\b", r"\bentitlements? (?:on|after) (?:exit|leaving)\b"]),
    ("ng.confirmation", "employment", "Probation and confirmation of appointment",
     [r"\bconfirmation letter\b", r"\bconfirmed staff\b", r"\bconfirmation of appointment\b"]),
    ("ng.labour_act", "employment", "Nigerian Labour Act",
     [r"\bLabour Act\b", r"\bNigerian labour law\b", r"\bNigeria Labour Act\b"]),
    ("ng.hmo_nhia", "healthcare", "HMO / NHIS / NHIA cover",
     [r"\bHMO\b", r"\bNHIS\b", r"\bNHIA\b", r"\bhealth maintenance organi[sz]ation\b",
      r"\bretainership\b"]),
    ("ng.deposit_before_care", "healthcare", "Payment or deposit demanded before treatment",
     [r"\bdeposit before\b", r"\bpay before (?:treatment|admission|the doctor)\b",
      r"\bout-?of-?pocket\b", r"\bcash and carry\b"]),
    ("ng.teaching_hospital", "healthcare", "Teaching / general hospital referral chain",
     [r"\bteaching hospital\b", r"\bgeneral hospital\b", r"\bLUTH\b", r"\bUCH\b",
      r"\bprimary health ?(?:care)? cent(?:re|er)\b", r"\bFMC\b"]),
    ("ng.cac", "government", "Corporate Affairs Commission",
     [r"\bCAC\b", r"\bCorporate Affairs Commission\b", r"\bbusiness name registration\b"]),
    ("ng.firs_tcc", "government", "FIRS / tax clearance certificate / TIN",
     [r"\bFIRS\b", r"\btax clearance\b", r"\bTCC\b", r"\bTIN\b", r"\bstate internal revenue\b",
      r"\bPAYE\b"]),
    ("ng.immigration_frsc", "government", "NIS passport / FRSC licence",
     [r"\bNigeria Immigration Service\b", r"\bNIS\b", r"\bFRSC\b",
      r"\bFederal Road Safety\b", r"\bpassport (?:office|capture)\b"]),
    ("ng.in_person_followup", "government", "In-person follow-up as a structural requirement",
     [r"\bgo (?:in person|to the office) (?:to|and)\b", r"\bfollow ?up in person\b",
      r"\bphysical(?:ly)? (?:visit|present|submit)\b", r"\bbiometric capture\b"]),
    ("ng.prepaid_meter", "utilities", "Prepaid meter, token, estimated billing, tariff band",
     [r"\bprepaid meter\b", r"\bestimated billing\b", r"\bmeter token\b", r"\bDisCo\b",
      r"\bBand [ABCDE]\b", r"\bIKEDC\b", r"\bEKEDC\b", r"\bAEDC\b", r"\bNERC\b"]),
    ("ng.generator_fuel", "utilities", "Generator / inverter / solar as a standing line item",
     [r"\bgenerator\b", r"\bgen(?:set)?\b", r"\binverter\b", r"\bsolar (?:panel|setup|system)\b",
      r"\bPHCN\b", r"\bNEPA\b", r"\bdiesel\b", r"\bpetrol\b", r"\bfuel (?:cost|budget)\b"]),
    ("ng.water_borehole", "utilities", "Borehole / tanker / vendor water",
     [r"\bborehole\b", r"\bwater tanker\b", r"\bmai ?ruwa\b", r"\bwell water\b",
      r"\bwater vendors?\b"]),
    ("ng.data_bundle", "utilities", "Mobile data bundles and airtime as the internet",
     [r"\bdata bundle\b", r"\bairtime\b", r"\bMTN\b", r"\bGlo\b", r"\bAirtel\b",
      r"\b9 ?mobile\b", r"\brecharge\b"]),
    ("ng.pay_on_delivery", "commerce", "Pay on delivery as the default e-commerce trust mechanism",
     [r"\bpay on delivery\b", r"\bpayment on delivery\b", r"\bPOD\b", r"\bJumia\b",
      r"\bKonga\b", r"\bcash on delivery\b"]),
    ("ng.fccpc", "commerce", "FCCPC as the consumer remedy",
     [r"\bFCCPC\b", r"\bFederal Competition and Consumer Protection\b",
      r"\bConsumer Protection Council\b", r"\bCPC\b"]),
    ("ng.tokunbo", "commerce", "Tokunbo / fairly-used market",
     [r"\btokunbo\b", r"\bfairly[- ]used\b", r"\bbelgium\b", r"\bComputer Village\b",
      r"\bAlaba\b"]),
    ("ng.landmark_address", "commerce", "Addressing by landmark and phone call",
     [r"\blandmark\b", r"\bbus ?stop\b", r"\bcall (?:the rider|when you get)\b",
      r"\bdescribe (?:the|your) (?:address|location)\b"]),
    ("ng.ajo_esusu", "finance", "Rotating savings and cooperative societies",
     [r"\bajo\b", r"\besusu\b", r"\badashe\b", r"\bthrift (?:collector|savings|contribution)\b",
      r"\bcooperative societ\w+\b", r"\bcontribution scheme\b"]),
    ("ng.domiciliary", "finance", "Domiciliary account / FX access",
     [r"\bdomiciliary account\b", r"\bdom account\b", r"\bFX (?:access|window)\b",
      r"\bparallel market\b", r"\bblack market rate\b", r"\bI&E window\b"]),
    ("ng.treasury_bills", "finance", "Treasury bills / FGN instruments as the savings vehicle",
     [r"\btreasury bills?\b", r"\bT-?bills?\b", r"\bFGN (?:bonds?|savings)\b",
      r"\bcommercial papers?\b", r"\bmoney market fund\b"]),
    ("ng.credit_bureau", "finance", "Nigerian credit bureaux",
     [r"\bCRC\b", r"\bFirstCentral\b", r"\bCreditRegistry\b", r"\bcredit bureau\b"]),
    ("ng.cbn", "finance", "Central Bank of Nigeria",
     [r"\bCBN\b", r"\bCentral Bank of Nigeria\b"]),
    ("ng.salary_delay", "employment", "Delayed salary treated as a normal condition",
     [r"\bsalary (?:delay|is late|arrears)\b", r"\bowed (?:\d+ )?months?'? salary\b",
      r"\bunpaid salar\w+\b", r"\bbacklog of salar\w+\b"]),
]

SURFACE = {
    "country_mention": [
        r"\bNigerian?s?\b", r"\bLagos\b", r"\bAbuja\b", r"\bPort Harcourt\b",
        r"\bKano\b", r"\bIbadan\b", r"\bNaija\b", r"\bWest Africa\w*\b",
    ],
    "currency": [r"₦", r"\bNGN\b", r"\bnairas?\b", r"\bkobo\b"],
}


def build_markers():
    return {
        "version": VERSION,
        "frozen_at": FROZEN_AT,
        "description": (
            "Locally-grounded Nigerian institutions and practices. A response naming any of these "
            "is engaging with the actual institutional substrate rather than the US default. "
            "Reported as ng_marker_rate, and used with surface localization to compute the "
            "cosmetic-localization cell."
        ),
        "surface": SURFACE,
        "markers": [
            {"id": i, "category": c, "label": lab, "triggers": t}
            for (i, c, lab, t) in NG_MARKERS
        ],
    }


def main():
    out = {
        ROOT / "data" / "checklist.json": build_checklist(),
        ROOT / "data" / "ng_markers.json": build_markers(),
    }
    lines = []
    for path, obj in out.items():
        blob = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
        path.write_text(blob, encoding="utf-8")
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        n = len(obj.get("flags") or obj.get("markers"))
        lines.append(f"path=data/{path.name} entries={n} sha256={digest}")
        print(lines[-1])

    # The sentence splitter decides which contrast cues reach which triggers, so
    # it changes flag counts as surely as the pattern files do. It is part of the
    # instrument and is frozen with them.
    for rel in ("score/detect.py",):
        digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        lines.append(f"path={rel} sha256={digest}")
        print(lines[-1])

    (ROOT / "data" / "INSTRUMENT_HASHES.txt").write_text(
        f"# frozen {FROZEN_AT}, version {VERSION}\n"
        f"# Any change here needs an entry in data/CHECKLIST_CHANGELOG.md.\n"
        + "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
