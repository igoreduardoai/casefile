"""Which merchant records can answer which PayPal evidence type.

PayPal tells the seller what it wants: the dispute details response lists
`evidences[]` with `source == REQUESTED_FROM_SELLER`. When that list is empty
we fall back to a per-reason default. Evidence type and reason names follow the
Disputes v1 API (developer.paypal.com/docs/api/customer-disputes/v1/).
"""

# evidence_type -> record kinds that can satisfy it
EVIDENCE_SOURCES = {
    "PROOF_OF_FULFILLMENT": ["shipment_delivered", "shipment_in_transit", "digital_delivery"],
    "PROOF_OF_DELIVERY_SIGNATURE": ["shipment_signed"],
    "PROOF_OF_REFUND": ["refund"],
    "ITEM_DESCRIPTION": ["listing"],
    "BILLING_AGREEMENT": ["subscription_terms"],
    "PROOF_OF_RECEIPT_COPY": ["order"],
    "OTHER": ["order", "listing", "message", "digital_delivery", "customer_history"],
}

# reason -> default evidence types if PayPal did not list any
DEFAULT_REQUESTS = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": ["PROOF_OF_FULFILLMENT"],
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": ["ITEM_DESCRIPTION"],
    "UNAUTHORISED": ["PROOF_OF_FULFILLMENT", "OTHER"],
    "CREDIT_NOT_PROCESSED": ["PROOF_OF_REFUND"],
    "DUPLICATE_TRANSACTION": ["OTHER"],
    "INCORRECT_AMOUNT": ["PROOF_OF_RECEIPT_COPY"],
    "CANCELED_RECURRING_BILLING": ["BILLING_AGREEMENT"],
    "PAYMENT_BY_OTHER_MEANS": ["OTHER"],
    "PROBLEM_WITH_REMITTANCE": ["OTHER"],
    "OTHER": ["OTHER"],
}


def requested_types(dispute: dict) -> list[str]:
    req = [e["evidence_type"] for e in dispute.get("evidences", [])
           if e.get("source") == "REQUESTED_FROM_SELLER"]
    if req:
        return sorted(set(req), key=req.index)
    return list(DEFAULT_REQUESTS.get(dispute.get("reason", "OTHER"), ["OTHER"]))
