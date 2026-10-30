"""Collect evidence from the merchant's records for one PayPal dispute.

Every item gets an id (E1, E2, ...) and the exact facts it can support.
The writer may only cite these ids, and the verifier checks every number
in the draft against the facts of the items it cites.
"""
from dataclasses import dataclass, field
from datetime import datetime

from .playbook import EVIDENCE_SOURCES, requested_types
from .records import MerchantRecords


@dataclass
class Evidence:
    id: str
    kind: str
    summary: str
    facts: dict = field(default_factory=dict)
    satisfies: list[str] = field(default_factory=list)


@dataclass
class Casefile:
    dispute_id: str
    reason: str
    status: str
    stage: str
    amount: float
    currency: str
    invoice: str
    due: str | None
    requested: list[str]
    evidence: list[Evidence]
    fault: list[str]          # reasons the seller is at fault (deterministic)
    risk: list[str]           # neutral notes for the human reviewer
    buyer_messages: list[str]

    def covered(self) -> dict[str, list[str]]:
        return {t: [e.id for e in self.evidence if t in e.satisfies] for t in self.requested}

    def coverage(self) -> float:
        cov = self.covered()
        return sum(1 for v in cov.values() if v) / len(cov) if cov else 0.0

    def by_id(self) -> dict[str, Evidence]:
        return {e.id: e for e in self.evidence}


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def build_casefile(dispute: dict, records: MerchantRecords) -> Casefile:
    txn = (dispute.get("disputed_transactions") or [{}])[0]
    invoice = txn.get("invoice_number", "")
    amount = float(dispute["dispute_amount"]["value"])
    currency = dispute["dispute_amount"]["currency_code"]
    reason = dispute.get("reason", "OTHER")
    requested = requested_types(dispute)
    items: list[Evidence] = []
    fault: list[str] = []
    risk: list[str] = []

    def add(kind, summary, facts):
        sat = [t for t, kinds in EVIDENCE_SOURCES.items() if kind in kinds]
        items.append(Evidence(f"E{len(items) + 1}", kind, summary, facts, sat))

    order = records.order(invoice)
    if order:
        add("order", f"Order {invoice} placed {order['created'][:10]} for {currency} {order['total']:.2f}",
            {"invoice": invoice, "date": order["created"][:10], "amount": order["total"],
             "items": [i["sku"] for i in order["items"]]})
        if abs(order["total"] - float(txn.get("gross_amount", {}).get("value", order["total"]))) > 0.005:
            risk.append("PayPal gross amount differs from the order total")
    else:
        fault.append("no order record for this invoice")

    shipments = records.shipments_for(invoice)
    for s in shipments:
        st = s["status"]
        if s.get("digital"):
            add("digital_delivery", f"Digital delivery sent to the buyer's email on {s['delivered'][:10]}",
                {"date": s["delivered"][:10], "log_id": s["tracking_number"]})
            continue
        kind = {"DELIVERED": "shipment_delivered", "IN_TRANSIT": "shipment_in_transit"}.get(st)
        if kind:
            date = (s.get("delivered") or s["shipped"])[:10]
            add(kind, f"{s['carrier']} tracking {s['tracking_number']} status {st} ({date})",
                {"carrier": s["carrier"], "tracking_number": s["tracking_number"], "date": date,
                 "shipped": s["shipped"][:10], "address_match": s.get("address_match", True)})
        if s.get("signed_by"):
            add("shipment_signed", f"Signature captured at delivery ({s['delivered'][:10]})",
                {"tracking_number": s["tracking_number"], "date": s["delivered"][:10]})
        if s.get("packed_weight_g") and order:
            listing = records.listing(order["items"][0]["sku"])
            if listing and s["packed_weight_g"] < listing.get("net_weight_g", 0) * 0.9:
                fault.append(f"packed weight {s['packed_weight_g']} g is below the listed {listing['net_weight_g']} g")
        if s.get("damage_reported"):
            fault.append("carrier reported damage in transit")
    if reason == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" and not shipments:
        fault.append("no shipment or delivery record")

    refunds = records.refunds_for(invoice)
    for r in refunds:
        add("refund", f"Refund {r['refund_id']} of {currency} {r['amount']:.2f} issued {r['date']}",
            {"refund_id": r["refund_id"], "amount": r["amount"], "date": r["date"]})
    rets = records.returns_for(invoice)
    if reason == "CREDIT_NOT_PROCESSED":
        if rets and not refunds:
            fault.append(f"return received {rets[0]['received']} but no refund issued")
        if not rets and not refunds:
            risk.append("no return and no refund on file")

    if order and reason in ("MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED", "OTHER", "INCORRECT_AMOUNT"):
        for it in order["items"]:
            lst = records.listing(it["sku"])
            if lst:
                add("listing", f"Listing {lst['sku']} as published: {lst['title']}",
                    {"sku": lst["sku"], "title": lst["title"], "net_weight_g": lst.get("net_weight_g")})

    sub = records.subscription(invoice)
    if sub and reason == "CANCELED_RECURRING_BILLING":
        if sub.get("canceled") and order and sub["canceled"] < order["created"][:10]:
            fault.append(f"subscription was canceled {sub['canceled']}, before this charge")
        else:
            add("subscription_terms", f"Subscription terms accepted {sub['accepted']} (renews {sub['cycle']})",
                {"date": sub["accepted"], "cycle": sub["cycle"]})

    if reason == "DUPLICATE_TRANSACTION" and order:
        twins = [o for o in records.orders_by_buyer(order["buyer_email"])
                 if o["invoice_number"] != invoice
                 and abs((_ts(o["created"]) - _ts(order["created"])).total_seconds()) < 600
                 and o["total"] == order["total"]
                 and [i["sku"] for i in o["items"]] == [i["sku"] for i in order["items"]]]
        if twins:
            fault.append(f"order {twins[0]['invoice_number']} is an identical charge minutes apart")
        else:
            others = [o for o in records.orders_by_buyer(order["buyer_email"]) if o["invoice_number"] != invoice]
            if others:
                o = others[0]
                add("order", f"Separate order {o['invoice_number']} on {o['created'][:10]} with different items",
                    {"invoice": o["invoice_number"], "date": o["created"][:10], "amount": o["total"],
                     "items": [i["sku"] for i in o["items"]]})

    if reason == "UNAUTHORISED" and order:
        prior = [o for o in records.orders_by_buyer(order["buyer_email"])
                 if o["invoice_number"] != invoice and o["created"] < order["created"]]
        delivered_ok = any(s["status"] == "DELIVERED" and s.get("address_match", True) for s in shipments)
        if len(prior) >= 2 and delivered_ok:
            add("customer_history", f"{len(prior)} earlier orders from this buyer to the same address, none disputed",
                {"count": len(prior)})
        elif not prior:
            risk.append("first-time buyer")
            if not shipments or any(not s.get("address_match", True) for s in shipments):
                fault.append("first-time buyer and the goods did not go to a matching, delivered address")

    msgs = [m.get("content", "") for m in dispute.get("messages", []) if m.get("posted_by") == "BUYER"]
    return Casefile(dispute["dispute_id"], reason, dispute.get("status", ""),
                    dispute.get("dispute_life_cycle_stage", ""), amount, currency, invoice,
                    dispute.get("seller_response_due_date"), requested, items, fault, risk, msgs)
