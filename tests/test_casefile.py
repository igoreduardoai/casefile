import json
import unittest
from pathlib import Path

from casefile.cli import FIXTURE_NOW
from casefile.desk import Desk
from casefile.evidence import build_casefile
from casefile.paypal import FixtureDisputes, PayPalSandbox, SANDBOX
from casefile.records import MerchantRecords
from casefile.verify import normalize, sentences, verify

ROOT = Path(__file__).resolve().parent.parent
API = FixtureDisputes(ROOT / "fixtures" / "disputes")


class FakeClient:
    base = SANDBOX

    def __init__(self):
        self.calls = []

    def provide_evidence(self, *a):
        self.calls.append(("provide_evidence", a)); return {"ok": True}

    def accept_claim(self, *a):
        self.calls.append(("accept_claim", a)); return {"ok": True}


class FakeLiveClient(FakeClient):
    base = "https://api-m.paypal.com"


def desk():
    return Desk(API, use_llm=False, now=FIXTURE_NOW)


class TestGate(unittest.TestCase):
    def test_no_call_without_token(self):
        plan, c = desk().prepare("PP-D-1001"), FakeClient()
        self.assertFalse(desk().execute(plan, None, c)["executed"])
        self.assertFalse(desk().execute(plan, "wrong", c)["executed"])
        self.assertEqual(c.calls, [])

    def test_call_with_matching_token(self):
        plan, c = desk().prepare("PP-D-1001"), FakeClient()
        r = desk().execute(plan, plan["approval_token"], c)
        self.assertTrue(r["executed"])
        self.assertEqual(c.calls[0][0], "provide_evidence")

    def test_token_bound_to_plan(self):
        a, b = desk().prepare("PP-D-1001"), desk().prepare("PP-D-1004")
        self.assertNotEqual(a["approval_token"], b["approval_token"])
        self.assertFalse(desk().execute(b, a["approval_token"], FakeClient())["executed"])

    def test_refuses_live_paypal(self):
        plan = desk().prepare("PP-D-1001")
        r = desk().execute(plan, plan["approval_token"], FakeLiveClient())
        self.assertFalse(r["executed"])

    def test_sandbox_constant(self):
        self.assertEqual(PayPalSandbox.base, "https://api-m.sandbox.paypal.com")

    def test_refund_goes_to_accept_claim(self):
        plan = desk().prepare("PP-D-1002")
        self.assertEqual(plan["action"], "REFUND")
        self.assertEqual(plan["call"]["method"], "accept_claim")

    def test_no_action_has_no_call(self):
        plan = desk().prepare("PP-D-1018")
        self.assertIsNone(plan["call"])
        self.assertFalse(desk().execute(plan, plan["approval_token"], FakeClient())["executed"])


class TestPacket(unittest.TestCase):
    def test_tracking_in_payload(self):
        plan = desk().prepare("PP-D-1004")
        evs = {e["evidence_type"]: e for e in plan["call"]["args"][1]["evidences"]}
        self.assertIn("tracking_info", evs["PROOF_OF_FULFILLMENT"]["evidence_info"])
        self.assertLessEqual(len(evs["PROOF_OF_FULFILLMENT"]["notes"]), 2000)

    def test_refund_ids_in_payload(self):
        plan = desk().prepare("PP-D-1007")
        ev = plan["call"]["args"][1]["evidences"][0]
        self.assertEqual(ev["evidence_type"], "PROOF_OF_REFUND")
        self.assertTrue(ev["evidence_info"]["refund_ids"])

    def test_fixture_source_is_labeled(self):
        self.assertIn("FIXTURE", desk().prepare("PP-D-1001")["source"])

    def test_injection_does_not_change_decision_or_notes(self):
        plan = desk().prepare("PP-D-1021")
        self.assertEqual(plan["action"], "FIGHT")
        self.assertNotIn("500", plan["notes"]["text"])

    def test_payload_shape_matches_docs(self):
        plan = desk().prepare("PP-D-1001")
        json.dumps(plan["call"])  # serializable
        self.assertEqual(set(plan["call"]["args"][1]), {"evidences"})


class TestVerifier(unittest.TestCase):
    def setUp(self):
        self.cf = build_casefile(API.get_dispute("PP-D-1001"), MerchantRecords())

    def test_normalize_typography(self):
        t = normalize("Order JT\u20111001 for USD\u202f42.00 [ E1 ].")
        self.assertEqual(t, "Order JT-1001 for USD 42.00 [E1].")
        self.assertEqual(verify(t, self.cf, "FIGHT"), [])

    def test_citation_after_period(self):
        self.assertEqual(sentences("Placed 2026-10-02. [E1] Delivered 2026-10-07. [E2]"),
                         ["Placed 2026-10-02. [E1]", "Delivered 2026-10-07. [E2]"])

    def test_wrong_number_blocked(self):
        self.assertTrue(verify("Delivered on 2026-10-09 [E2].", self.cf, "FIGHT"))


if __name__ == "__main__":
    unittest.main()
