"""Verifier for the seller's dispute notes. Deterministic; runs on every draft.

Rules (a draft that breaks any rule is rejected and replaced by the template):
  V1 every sentence that states a fact cites at least one evidence id like [E2]
  V2 every cited id exists in the casefile
  V3 every number (amount, date, tracking/refund id) in a sentence appears in the
     facts of an evidence item cited in that sentence, or is the dispute amount
  V4 PayPal's notes limit: at most 2000 characters
  V5 no promises or admissions the decision did not make (refund/offer words in a FIGHT)
  V6 no buyer contact data (emails, phone numbers)
"""
import re

from .evidence import Casefile

CITE = re.compile(r"\[(E\d+)\]")
NUM = re.compile(r"(?<![A-Za-z])(?:\d{4}-\d{2}-\d{2}|\d+(?:[.,]\d+)*)(?![A-Za-z])")
TOKEN = re.compile(r"\b(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{5,}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
PROMISE = re.compile(r"\b(refund(ed)? you|we will refund|full refund|partial refund|we accept|our fault|we apologi[sz]e for the error)\b", re.I)


def _flat(v) -> list[str]:
    if isinstance(v, (list, tuple)):
        return [x for i in v for x in _flat(i)]
    if isinstance(v, float):
        return [f"{v:.2f}", f"{v:g}"]
    return [str(v)]


def _norm(n: str) -> str:
    n = n.replace(",", "")
    try:
        f = float(n)
        return f"{f:.2f}" if "." in n else str(int(f))
    except ValueError:
        return n


_TYPO = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
                       "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2007": " "})


def normalize(text: str) -> str:
    """Typography only: unicode hyphens/spaces -> ASCII, '[ E1 ]' -> '[E1]'. Never changes content."""
    return re.sub(r"\[\s*(E\d+)\s*\]", r"[\1]", text.translate(_TYPO))


def sentences(text: str) -> list[str]:
    """Split into sentences; a citation written after the period ('... 2026-10-07. [E2]') stays with its sentence."""
    out: list[str] = []
    for s in (x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text)):
        if not s:
            continue
        m = re.match(r"^((?:\[E\d+\][\s,;]*)+)(.*)$", s)
        if m and out:
            out[-1] += " " + m.group(1).strip()
            s = m.group(2).strip()
            if not s:
                continue
        out.append(s)
    return out


def verify(text: str, cf: Casefile, action: str) -> list[str]:
    errs = []
    ids = cf.by_id()
    if len(text) > 2000:
        errs.append(f"V4 notes are {len(text)} chars (> 2000)")
    scrub = re.sub(r"\d{4}-\d{2}-\d{2}", " ", TOKEN.sub(" ", text))
    if EMAIL.search(text) or PHONE.search(scrub):
        errs.append("V6 contains buyer contact data")
    if action == "FIGHT" and PROMISE.search(text):
        errs.append(f"V5 promise/admission in a FIGHT: '{PROMISE.search(text).group(0)}'")
    allowed_global = {_norm(f"{cf.amount:.2f}"), _norm(cf.dispute_id)}
    for s in sentences(text):
        cites = CITE.findall(s)
        for c in cites:
            if c not in ids:
                errs.append(f"V2 cites unknown {c}: '{s[:60]}'")
        body = CITE.sub("", s)
        tokens = set(TOKEN.findall(body))
        nums = set(NUM.findall(TOKEN.sub(" ", body))) | tokens
        nums = {n for n in nums if not re.fullmatch(r"\d", n)}  # single digits ("1 package") are fine
        if not nums:
            continue
        if not cites:
            stray = {n for n in nums if _norm(n) not in allowed_global}
            if stray:
                errs.append(f"V1 uncited facts {sorted(stray)}: '{s[:60]}'")
            continue
        known = set(allowed_global)
        for c in cites:
            if c in ids:
                for v in ids[c].facts.values():
                    known |= {_norm(x) for x in _flat(v)}
        for n in nums:
            if _norm(n) not in known:
                errs.append(f"V3 '{n}' not in cited evidence {cites}: '{s[:60]}'")
    return errs
