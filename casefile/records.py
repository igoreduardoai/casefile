"""Merchant-side records (the seller's own systems). Offline JSON for the demo shop."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "fixtures" / "merchant"


class MerchantRecords:
    def __init__(self, directory: Path | str = DEFAULT_DIR):
        d = Path(directory)
        self.orders = json.loads((d / "orders.json").read_text())
        self.shipments = json.loads((d / "shipments.json").read_text())
        self.refunds = json.loads((d / "refunds.json").read_text())
        self.returns = json.loads((d / "returns.json").read_text())
        self.listings = json.loads((d / "listings.json").read_text())
        self.subscriptions = json.loads((d / "subscriptions.json").read_text())
        self.policy = json.loads((d / "policy.json").read_text())

    def order(self, invoice: str) -> dict | None:
        return next((o for o in self.orders if o["invoice_number"] == invoice), None)

    def shipments_for(self, invoice: str) -> list[dict]:
        return [s for s in self.shipments if s["invoice_number"] == invoice]

    def refunds_for(self, invoice: str) -> list[dict]:
        return [r for r in self.refunds if r["invoice_number"] == invoice]

    def returns_for(self, invoice: str) -> list[dict]:
        return [r for r in self.returns if r["invoice_number"] == invoice]

    def listing(self, sku: str) -> dict | None:
        return next((l for l in self.listings if l["sku"] == sku), None)

    def subscription(self, invoice: str) -> dict | None:
        return next((s for s in self.subscriptions if s["invoice_number"] == invoice), None)

    def orders_by_buyer(self, email: str) -> list[dict]:
        return [o for o in self.orders if o.get("buyer_email") == email]
