# Casefile: an evidence-first AI dispute desk for small PayPal sellers

> Status: work in progress for the PayPal AI Hackathon (Devpost, Oct 1 – Nov 12, 2026). Repository created Oct 30, 2026.
> Until sandbox keys are configured, everything below runs **offline on synthetic fixtures** and every output is labeled `FIXTURE`.

**Problem.** When a buyer opens a PayPal dispute, a small seller has a few days to answer with the right evidence. Most of them either refund everything or answer with a generic note and no evidence. Each chargeback costs U.S. merchants about **$128 in handling and third-party fees** on top of the lost sale ($82 internal + $46 third-party; Mastercard/Javelin, 2025: https://www.mastercard.com/us/en/news-and-trends/Insights/2025/what-s-the-true-cost-of-a-chargeback-in-2025.html).

**What Casefile does**
1. Reads open disputes from the **PayPal Disputes API** (`GET /v1/customer/disputes`, `GET /v1/customer/disputes/{id}`), including the evidence types PayPal requests from the seller (`evidences[].source == REQUESTED_FROM_SELLER`).
2. Pulls the seller's own records (orders, shipments, refunds, returns, listings, subscriptions) and builds a **casefile**: numbered evidence items `E1..En`, each with the exact facts it can prove.
3. **Decides deterministically**: FIGHT (provide evidence), REFUND (accept claim) or NO_ACTION. The rule engine flags cases where the seller is at fault (never shipped, true duplicate, refund owed, packed less than listed) so the seller doesn't fight disputes it should lose. The LLM never decides money.
4. An **LLM writes the response notes** (Groq free tier, `openai/gpt-oss-120b`) citing evidence ids.
5. A **verifier** checks every sentence: each fact must cite an evidence id, and every number, date, tracking or refund id must appear in the cited evidence. It also blocks buyer contact data, refund promises in a FIGHT, and notes over PayPal's 2,000-character limit. If the draft fails, Casefile uses a deterministic template and shows why.
6. Builds the exact PayPal call (`provide-evidence` with `tracking_info` / `refund_ids`, or `accept-claim`) and shows it. **Nothing is sent until the seller approves** by echoing a token bound to that exact plan. The client is hard-coded to the sandbox.

## Run it (about 1 minute, $0, Python 3.10+, standard library only)
```bash
python3 -m casefile.cli list                         # dispute queue (fixtures)
python3 -m casefile.cli show PP-D-1004 --no-llm      # casefile, decision, notes, exact PayPal call
python3 -m evals.run_evals                           # offline evals
python3 -m unittest -q                               # 15 tests
```
Optional: set `GROQ_API_KEY` (free at console.groq.com) to let the LLM write the notes, and run `python3 -m evals.run_evals --llm`.

## Evals (current numbers, `evals/last_results*.json`)
24 synthetic disputes covering 7 PayPal dispute reasons, with labels written by hand and frozen before the first run (`evals/gold.json`).

| | Decision matches label | Requested evidence attached (gold FIGHT cases) |
|---|---|---|
| Baseline B0: always refund | 38% (9/24) | n/a |
| Baseline B1: always fight with a generic note | 54% (13/24) | 0/16 |
| **Casefile** | **100% (24/24)** | **16/16** |

- Verifier attacks: **12/12** handled (hallucinated tracking number, wrong delivery date, invented refund amount, uncited fact, unknown evidence id, email and phone leaks, refund promise in a FIGHT, >2,000 chars, echoed prompt injection; two clean drafts pass).
- LLM writer (Groq free tier, 13 FIGHT cases, Oct 30 run): **8/13** drafts accepted by the verifier. The 5 rejections attributed a product SKU to a shipment record that doesn't contain it; those cases fell back to the template.
- **Limits.** The labels and the rules were written by the same person, so 100% on this set is an in-sample check of the pipeline, not proof that the policy is right for a real shop. The handling cost ($25 per contested case) is an editable assumption in `fixtures/merchant/policy.json`. No real seller has used Casefile yet.

## PayPal sandbox mode
Set `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` from a sandbox app at https://developer.paypal.com/dashboard/applications/sandbox. Then `list` and `show` read real sandbox disputes, and `show <id> --approve <token>` sends the planned call. See `docs/SANDBOX-SETUP.md` for creating a test dispute and driving it through `require-evidence` and `adjudicate` (sandbox-only endpoints).
Sandbox status as of Oct 30: **not run yet** (no keys configured).

## Architecture
`paypal.py` (sandbox REST client + offline fixture reader) → `evidence.py` (casefile from seller records) → `decide.py` (deterministic action) → `writer.py` (LLM or template) → `verify.py` (claim-level checks) → `desk.py` (plan, approval token, execute) → `cli.py`.

All data in `fixtures/` is synthetic (a fictional shop, "Juniper Tea Co."). Not legal or financial advice. MIT licensed.
