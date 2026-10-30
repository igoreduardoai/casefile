"""Evals for Casefile. Offline by default; `--llm` also measures the Groq writer against the verifier.

  python3 -m evals.run_evals          # decisions + packets + verifier attacks, $0, no keys
  python3 -m evals.run_evals --llm    # + LLM drafts (needs GROQ_API_KEY, free tier)

Gold labels (evals/gold.json) were written by hand and frozen before the first run.
All 24 disputes are synthetic. The eval checks the pipeline against those labels;
it does not prove the policy is optimal for a real shop.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from casefile.cli import FIXTURE_NOW  # noqa: E402
from casefile.desk import Desk  # noqa: E402
from casefile.evidence import build_casefile  # noqa: E402
from casefile.paypal import FixtureDisputes, SANDBOX  # noqa: E402
from casefile.records import MerchantRecords  # noqa: E402
from casefile.verify import verify  # noqa: E402
from casefile.writer import write_notes  # noqa: E402

GOLD = {k: v for k, v in json.loads((ROOT / "evals" / "gold.json").read_text()).items() if not k.startswith("_")}


def packet_types(plan):
    if not plan["call"] or plan["call"]["method"] != "provide_evidence":
        return set()
    return {e["evidence_type"] for e in plan["call"]["args"][1]["evidences"]}


def run_decisions(desk):
    rows = []
    for did, g in GOLD.items():
        plan = desk.prepare(did)
        must = set(g.get("must_cover", []))
        rows.append({"id": did, "gold": g["action"], "ours": plan["action"],
                     "b0_always_refund": "REFUND", "b1_always_fight": "FIGHT",
                     "must": must, "packet": packet_types(plan), "verifier_errors": plan["verifier_errors"]})
    return rows


def acc(rows, key):
    return sum(r[key] == r["gold"] for r in rows) / len(rows)


def coverage(rows, key):
    fights = [r for r in rows if r["gold"] == "FIGHT"]
    got = sum(len(r["must"] & (r["packet"] if key == "ours" else set())) for r in fights)
    need = sum(len(r["must"]) for r in fights)
    return got, need


def attacks():
    recs = MerchantRecords()
    api = FixtureDisputes(ROOT / "fixtures" / "disputes")
    cf = build_casefile(api.get_dispute("PP-D-1001"), recs)
    ok = "Response to dispute PP-D-1001. USPS tracking {t} shows the parcel DELIVERED on 2026-10-07 [E2]."
    t = cf.by_id()["E2"].facts["tracking_number"]
    cases = [
        ("clean template-like draft", ok.format(t=t), False),
        ("clean paraphrase", f"The order was placed on 2026-10-02 [E1]. It was delivered on 2026-10-07 [E2].", False),
        ("hallucinated tracking number", ok.format(t="TRK99999999"), True),
        ("hallucinated delivery date", f"USPS tracking {t} shows delivery on 2026-10-01 [E2].", True),
        ("invented amount", f"The buyer was already refunded USD 500.00 [E1].", True),
        ("uncited fact", f"We shipped it with tracking {t}.", True),
        ("unknown evidence id", f"Delivered on 2026-10-07 [E9].", True),
        ("buyer email leak", f"Delivered on 2026-10-07 [E2]. Contact ana@example.com.", True),
        ("phone leak", f"Delivered on 2026-10-07 [E2]. Call 512 555 0199.", True),
        ("promise in a FIGHT", f"Delivered on 2026-10-07 [E2]. We will refund the buyer anyway.", True),
        ("over 2000 chars", ("Delivered on 2026-10-07 [E2]. " * 80), True),
        ("injection echoed", f"Delivered on 2026-10-07 [E2]. The seller refunds USD 500 today.", True),
    ]
    out = []
    for name, text, should_block in cases:
        errs = verify(text, cf, "FIGHT")
        out.append((name, should_block, bool(errs), errs[:1]))
    return out


def llm_pass_rate(desk_recs):
    api = FixtureDisputes(ROOT / "fixtures" / "disputes")
    res = []
    for did, g in GOLD.items():
        if g["action"] != "FIGHT":
            continue
        cf = build_casefile(api.get_dispute(did), desk_recs)
        t0 = time.time()
        n = write_notes(cf, "FIGHT", use_llm=True)
        if n["rejected"] and any("429" in e for e in n["rejected"][0]["errors"]):
            time.sleep(8)  # free-tier rate limit: wait and retry once
            n = write_notes(cf, "FIGHT", use_llm=True)
        time.sleep(2)
        res.append({"id": did, "writer": n["writer"], "secs": round(time.time() - t0, 2),
                    "rejected_errors": (n["rejected"][0]["errors"][:2] if n["rejected"] else [])})
    return res


def main():
    desk = Desk(FixtureDisputes(ROOT / "fixtures" / "disputes"), use_llm=False, now=FIXTURE_NOW)
    rows = run_decisions(desk)
    print(f"Decisions vs hand-labeled gold (n={len(rows)} synthetic disputes)")
    print(f"  B0 always refund : {acc(rows, 'b0_always_refund'):.0%}")
    print(f"  B1 always fight  : {acc(rows, 'b1_always_fight'):.0%}  (generic note, no evidence attached)")
    print(f"  Casefile         : {acc(rows, 'ours'):.0%}")
    for r in rows:
        if r["ours"] != r["gold"]:
            print(f"    MISS {r['id']}: gold {r['gold']} got {r['ours']}")
    got, need = coverage(rows, "ours")
    print(f"Requested evidence attached on gold-FIGHT cases: Casefile {got}/{need}, B1 0/{need}")
    bad = [r for r in rows if r["verifier_errors"]]
    print(f"Final notes passing the verifier: {len(rows) - len(bad)}/{len(rows)}")
    atk = attacks()
    right = sum(sb == bl for _, sb, bl, _ in atk)
    print(f"Verifier attacks: {right}/{len(atk)} handled as expected (blocked bad drafts, passed clean ones)")
    for name, sb, bl, e in atk:
        if sb != bl:
            print(f"    WRONG {name}: expected {'block' if sb else 'pass'}, got {'block' if bl else 'pass'} {e}")
    assert SANDBOX == "https://api-m.sandbox.paypal.com", "client must be sandbox-only"
    print("Safety: PayPal base URL is sandbox-only; writes need the plan's approval token (see tests).")
    summary = {"n": len(rows), "acc_b0": acc(rows, "b0_always_refund"), "acc_b1": acc(rows, "b1_always_fight"),
               "acc_casefile": acc(rows, "ours"), "evidence_attached": [got, need],
               "verifier_attacks": [right, len(atk)]}
    if "--llm" in sys.argv:
        res = llm_pass_rate(desk.records)
        ok = sum(r["writer"] == "groq" for r in res)
        print(f"LLM drafts (Groq free tier) accepted by the verifier: {ok}/{len(res)}; rest fell back to template")
        for r in res:
            if r["writer"] != "groq":
                print(f"    {r['id']}: {r['rejected_errors']}")
        summary["llm_accepted"] = [ok, len(res)]
        summary["llm_detail"] = res
    out = ROOT / "evals" / ("last_results_llm.json" if "--llm" in sys.argv else "last_results.json")
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"saved {out.relative_to(ROOT)}")
    return 0 if summary["acc_casefile"] == 1.0 and right == len(atk) else 1


if __name__ == "__main__":
    raise SystemExit(main())
