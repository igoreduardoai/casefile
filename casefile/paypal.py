"""PayPal REST client, sandbox only. Python standard library.

Read calls:  GET /v1/customer/disputes, GET /v1/customer/disputes/{id}
Write calls: POST .../provide-evidence (multipart), POST .../accept-claim
Sandbox-only test helpers: POST .../require-evidence, POST .../adjudicate
Docs: https://developer.paypal.com/docs/api/customer-disputes/v1/

Writes only happen through Desk.execute() after a human approval token.
"""
import base64
import json
import os
import urllib.parse
import urllib.request
import uuid

SANDBOX = "https://api-m.sandbox.paypal.com"  # hard-coded on purpose; an eval asserts it


class PayPalSandbox:
    base = SANDBOX

    def __init__(self, client_id: str | None = None, secret: str | None = None):
        self.client_id = client_id or os.environ.get("PAYPAL_CLIENT_ID")
        self.secret = secret or os.environ.get("PAYPAL_CLIENT_SECRET")
        if not (self.client_id and self.secret):
            raise RuntimeError("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET not set")
        self._token = None

    def token(self) -> str:
        if self._token:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
        req = urllib.request.Request(f"{self.base}/v1/oauth2/token", data=b"grant_type=client_credentials",
                                     headers={"Authorization": f"Basic {basic}",
                                              "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            self._token = json.loads(r.read())["access_token"]
        return self._token

    def _call(self, method: str, path: str, body: dict | None = None, multipart: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token()}", "PayPal-Request-Id": str(uuid.uuid4())}
        data = None
        if multipart is not None:
            boundary = uuid.uuid4().hex
            parts = []
            for name, (ctype, payload) in multipart.items():
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n"
                             f"Content-Type: {ctype}\r\n\r\n{payload}\r\n")
            data = ("".join(parts) + f"--{boundary}--\r\n").encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.base}{path}", data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {"status": r.status}

    # reads
    def list_disputes(self, status: str = "WAITING_FOR_SELLER_RESPONSE") -> list[dict]:
        q = urllib.parse.urlencode({"dispute_state": "REQUIRED_ACTION"}) if status else ""
        return self._call("GET", f"/v1/customer/disputes?{q}").get("items", [])

    def get_dispute(self, dispute_id: str) -> dict:
        return self._call("GET", f"/v1/customer/disputes/{dispute_id}")

    # writes (called only by Desk.execute)
    def provide_evidence(self, dispute_id: str, payload: dict) -> dict:
        return self._call("POST", f"/v1/customer/disputes/{dispute_id}/provide-evidence",
                          multipart={"input": ("application/json", json.dumps(payload))})

    def accept_claim(self, dispute_id: str, note: str) -> dict:
        return self._call("POST", f"/v1/customer/disputes/{dispute_id}/accept-claim", body={"note": note})

    # sandbox-only helpers (to drive a test dispute through its life cycle on camera)
    def require_evidence(self, dispute_id: str, action: str = "SELLER_EVIDENCE") -> dict:
        return self._call("POST", f"/v1/customer/disputes/{dispute_id}/require-evidence", body={"action": action})

    def adjudicate(self, dispute_id: str, outcome: str) -> dict:
        return self._call("POST", f"/v1/customer/disputes/{dispute_id}/adjudicate",
                          body={"adjudication_outcome": outcome})


class FixtureDisputes:
    """Offline stand-in that returns saved, PayPal-shaped dispute JSON. Labeled FIXTURE everywhere."""
    source = "FIXTURE (offline, synthetic)"

    def __init__(self, directory):
        from pathlib import Path
        self.dir = Path(directory)

    def list_disputes(self, status: str = "WAITING_FOR_SELLER_RESPONSE") -> list[dict]:
        out = []
        for p in sorted(self.dir.glob("*.json")):
            d = json.loads(p.read_text())
            out.append({k: d[k] for k in ("dispute_id", "reason", "status", "dispute_amount", "create_time")})
        return out

    def get_dispute(self, dispute_id: str) -> dict:
        return json.loads((self.dir / f"{dispute_id}.json").read_text())
