"""The dispute desk: PayPal dispute -> casefile -> decision -> notes -> plan -> (approval) -> PayPal call."""
import hashlib
import json
from dataclasses import asdict
from datetime import datetime

from .decide import decide, DEFAULT_HANDLING_COST
from .evidence import build_casefile
from .records import MerchantRecords
from .verify import verify
from .writer import write_notes


def evidence_payload(cf, notes: str) -> dict:
    evs = []
    by = cf.by_id()
    for etype, ids in cf.covered().items():
        if not ids:
            continue
        info = {}
        tracking = [{"carrier_name": by[i].facts["carrier"], "tracking_number": by[i].facts["tracking_number"]}
                    for i in ids if "carrier" in by[i].facts]
        refunds = [by[i].facts["refund_id"] for i in ids if "refund_id" in by[i].facts]
        if tracking and etype in ("PROOF_OF_FULFILLMENT", "PROOF_OF_DELIVERY_SIGNATURE"):
            info["tracking_info"] = tracking
        if refunds and etype == "PROOF_OF_REFUND":
            info["refund_ids"] = [{"refund_id": r} for r in refunds]
        ev = {"evidence_type": etype, "notes": notes}
        if info:
            ev["evidence_info"] = info
        evs.append(ev)
    return {"evidences": evs}


class Desk:
    def __init__(self, disputes_api, records: MerchantRecords | None = None, use_llm: bool = True,
                 now: datetime | None = None):
        self.api = disputes_api
        self.records = records or MerchantRecords()
        self.use_llm = use_llm
        self.now = now

    def prepare(self, dispute_id: str) -> dict:
        dispute = self.api.get_dispute(dispute_id)
        cf = build_casefile(dispute, self.records)
        cost = float(self.records.policy.get("handling_cost_usd", DEFAULT_HANDLING_COST))
        d = decide(cf, now=self.now, handling_cost=cost)
        notes = write_notes(cf, d.action, use_llm=self.use_llm) if d.action != "NO_ACTION" else \
            {"text": "", "writer": None, "rejected": []}
        if d.action == "FIGHT":
            call = {"method": "provide_evidence", "args": [cf.dispute_id, evidence_payload(cf, notes["text"])]}
        elif d.action == "REFUND":
            call = {"method": "accept_claim", "args": [cf.dispute_id, notes["text"]]}
        else:
            call = None
        plan = {"dispute_id": cf.dispute_id, "action": d.action, "why": d.why, "coverage": round(d.coverage, 2),
                "requested": cf.requested, "covered": cf.covered(), "risk": cf.risk,
                "evidence": [asdict(e) for e in cf.evidence], "notes": notes,
                "verifier_errors": verify(notes["text"], cf, d.action) if notes["text"] else [],
                "call": call, "source": getattr(self.api, "source", "PAYPAL SANDBOX (live API)")}
        plan["approval_token"] = hashlib.sha256(json.dumps(call, sort_keys=True).encode()).hexdigest()[:12]
        return plan

    def execute(self, plan: dict, approval_token: str | None, client) -> dict:
        """Run the planned PayPal call. Requires the human to echo the plan's token."""
        if plan["call"] is None:
            return {"executed": False, "reason": "no action"}
        if approval_token != plan["approval_token"]:
            return {"executed": False, "reason": "not approved (token missing or does not match this plan)"}
        if plan["verifier_errors"]:
            return {"executed": False, "reason": f"verifier errors: {plan['verifier_errors']}"}
        if not getattr(client, "base", "").startswith("https://api-m.sandbox.paypal.com"):
            return {"executed": False, "reason": "refusing: client is not the PayPal sandbox"}
        fn = getattr(client, plan["call"]["method"])
        return {"executed": True, "response": fn(*plan["call"]["args"])}
