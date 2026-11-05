# Casefile demo video (target 2:45, screen only, no face)
On-screen label: "Narration: Igor's own voice, cloned with ElevenLabs (synthetic voice)". Name PayPal and AI on screen.

0:00-0:20 Problem. A small seller gets a PayPal dispute; a few days to answer. Chargebacks cost US merchants ~$128 in fees on top of the sale (Mastercard/Javelin 2025).
0:20-0:45 Queue: `python3 -m casefile.cli list` (Disputes API `GET /v1/customer/disputes`; FIXTURE label until sandbox keys exist).
0:45-1:25 One case: `show PP-D-1004 --no-llm`. Requested evidence (REQUESTED_FROM_SELLER) -> casefile E1..En -> deterministic FIGHT/REFUND/NO_ACTION. The LLM never decides money.
1:25-1:55 LLM notes + verifier: every number/date/tracking id must be in the cited evidence; show one blocked hallucinated tracking number.
1:55-2:15 Approval gate: exact `provide-evidence` / `accept-claim` call, sent only with the plan-bound token; sandbox-only base URL.
2:15-2:35 Evals: B0 always refund 38%, B1 always fight 54%, Casefile 24/24 (in-sample), 16/16 requested evidence attached, verifier attacks 12/12, LLM drafts 8/13 accepted.
2:35-2:45 Limits (synthetic fixtures, same author wrote labels and rules, no real seller yet) + repo github.com/igoreduardoai/casefile.
If sandbox keys arrive: replace 0:20-0:45 and 1:55-2:15 with real sandbox calls (create dispute -> require-evidence -> provide-evidence -> adjudicate).
