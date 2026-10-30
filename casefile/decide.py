"""Deterministic recommendation. The LLM never decides money; this does.

FIGHT   = submit evidence (provide-evidence)
REFUND  = accept the claim (accept-claim)
NO_ACTION = nothing the seller can do right now (not waiting on seller, or past due)

The handling cost is an explicit, editable assumption, not a measured number.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from .evidence import Casefile

DEFAULT_HANDLING_COST = 25.0  # USD of seller time per contested case (assumption, set in policy.json)


@dataclass
class Decision:
    action: str
    why: list[str]
    coverage: float


def decide(cf: Casefile, now: datetime | None = None, handling_cost: float = DEFAULT_HANDLING_COST) -> Decision:
    now = now or datetime.now(timezone.utc)
    if cf.status != "WAITING_FOR_SELLER_RESPONSE":
        return Decision("NO_ACTION", [f"status is {cf.status}; PayPal is not waiting on the seller"], cf.coverage())
    if cf.due and datetime.fromisoformat(cf.due.replace("Z", "+00:00")) < now:
        return Decision("NO_ACTION", [f"seller response was due {cf.due[:10]}"], cf.coverage())
    if cf.fault:
        return Decision("REFUND", [f"seller at fault: {f}" for f in cf.fault], cf.coverage())
    cov = cf.coverage()
    if cov == 0:
        return Decision("REFUND", ["no record answers what PayPal requested"], cov)
    if cf.amount < handling_cost:
        return Decision("REFUND", [f"amount {cf.amount:.2f} is below the handling cost {handling_cost:.2f}"], cov)
    covered = [t for t, ids in cf.covered().items() if ids]
    return Decision("FIGHT", [f"records cover {len(covered)}/{len(cf.requested)} requested evidence types: "
                              + ", ".join(covered)], cov)
