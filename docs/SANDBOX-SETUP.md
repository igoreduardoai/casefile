# Sandbox setup (free)
1. Log in at https://developer.paypal.com (free account).
2. Apps & Credentials → **Sandbox** → Create App (type Merchant). Copy Client ID and Secret into `.env` (never commit it).
3. Testing Tools → Sandbox Accounts: use the default Business (seller) and Personal (buyer) accounts, or create them.
4. Make a sandbox purchase from the buyer to the seller (Orders v2 create + capture; script planned: `scripts/sandbox_purchase.py`).
5. Open a dispute on that purchase as the buyer, either in the sandbox website (log in at https://www.sandbox.paypal.com as the buyer → Resolution Center) or with the sandbox-only `POST /v1/customer/disputes` (needs buyer consent and a `PayPal-Auth-Assertion` header; docs: https://developer.paypal.com/disputes/test-go-live).
6. `python3 -m casefile.cli list` → `show <id>` → `--approve <token>`.
7. Sandbox-only: `require-evidence` moves a dispute to WAITING_FOR_SELLER_RESPONSE; `adjudicate` settles it (BUYER_FAVOR / SELLER_FAVOR) so the full life cycle can be shown on video.
