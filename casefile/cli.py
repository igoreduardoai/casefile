"""Usage:
  python3 -m casefile.cli list                      # queue (fixtures unless PayPal sandbox keys are set)
  python3 -m casefile.cli show PP-D-1001            # casefile + recommendation + exact PayPal call
  python3 -m casefile.cli show PP-D-1001 --approve <token>   # sandbox only, needs keys
Flags: --fixtures (force offline), --no-llm
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .desk import Desk
from .paypal import FixtureDisputes, PayPalSandbox

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)  # fixtures are dated around this day


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    offline = "--fixtures" in argv or not os.environ.get("PAYPAL_CLIENT_ID")
    use_llm = "--no-llm" not in argv
    argv = [a for a in argv if a not in ("--fixtures", "--no-llm")]
    api = FixtureDisputes(ROOT / "fixtures" / "disputes") if offline else PayPalSandbox()
    desk = Desk(api, use_llm=use_llm, now=FIXTURE_NOW if offline else None)
    print(f"# source: {getattr(api, 'source', 'PAYPAL SANDBOX (live API)')}")
    if not argv or argv[0] == "list":
        for d in api.list_disputes():
            print(f"{d['dispute_id']:<12} {d['reason']:<40} {d['status']:<30} "
                  f"{d['dispute_amount']['currency_code']} {d['dispute_amount']['value']}")
        return 0
    if argv[0] == "show":
        plan = desk.prepare(argv[1])
        print(json.dumps(plan, indent=2))
        if "--approve" in argv:
            tok = argv[argv.index("--approve") + 1]
            if offline:
                print("# offline: nothing sent. Set PAYPAL_CLIENT_ID/SECRET to execute against the sandbox.")
                return 0
            print(json.dumps(desk.execute(plan, tok, api), indent=2))
        else:
            print(f"# nothing sent. To execute in the sandbox: --approve {plan['approval_token']}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
