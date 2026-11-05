# Devpost page draft (PayPal AI Hackathon) - not submitted

**Name:** Casefile
**Tagline:** An evidence-first AI dispute desk for small PayPal sellers: the rules decide, the AI writes, a verifier checks every fact, the seller approves.

## Inspiration
When a buyer opens a PayPal dispute, small sellers have a few days to respond. Most refund everything or send a generic note with no evidence. Each chargeback costs US merchants about $128 in handling and third-party fees on top of the lost sale (Mastercard/Javelin, 2025).

## What it does
Casefile reads open disputes through the PayPal Disputes API, including the evidence PayPal asks the seller for. It builds a numbered casefile (E1..En) from the seller's orders, shipments, refunds and listings. A deterministic rule engine picks FIGHT, REFUND or NO_ACTION. It flags cases the seller should lose, so they are not contested. An LLM writes the response notes, citing evidence ids. A claim-level verifier blocks any number, date, tracking or refund id that is not in the cited evidence. It also blocks contact-data leaks, refund promises in a FIGHT, and notes over 2,000 characters. Casefile then shows the exact `provide-evidence` or `accept-claim` call, and nothing is sent until the seller approves with a token bound to that plan.

## How we built it
Python standard library only. Modules: paypal.py (sandbox-only REST client), evidence.py, decide.py, writer.py (Groq `openai/gpt-oss-120b`, with a template fallback), verify.py, desk.py, cli.py. Evals use 24 synthetic disputes across 7 PayPal dispute reasons, with labels frozen before the first run.

## Results (from evals/last_results*.json)
- Decision matches label: always-refund baseline 38% (9/24), always-fight baseline 54% (13/24), Casefile 100% (24/24). This is in-sample: the same person wrote the labels and the rules.
- Requested evidence attached on FIGHT cases: Casefile 16/16, generic baseline 0/16.
- Verifier attack suite: 12/12 handled.
- LLM drafts accepted by the verifier: 8/13. The rejected drafts fell back to the template.

## Challenges / Limits
Synthetic fixtures only. No real seller yet. Sandbox run: [fill in after keys are set, or state "not run"].

## What's next
A full sandbox dispute lifecycle on camera, a held-out case set written independently, and a web queue UI.

**Built with:** python, paypal-disputes-api, paypal-rest-api, groq, gpt-oss-120b, llm
**Repo:** https://github.com/igoreduardoai/casefile  **Video:** [YouTube link]
