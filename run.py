"""Run the ACH Return Triage Agent on a batch of returned deposits.

    python run.py --offline          # no API key needed: rules engine + templates
    python run.py                    # uses Claude (needs ANTHROPIC_API_KEY)
    python run.py --auto-approve     # skip the human approval prompts
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from ach_agent.agent import MODEL, triage_offline, triage_with_claude
from ach_agent.tools import Toolbox, load_batch

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def review(result: dict, auto: bool) -> str:
    """Human-in-the-loop: a person approves each action before it happens."""
    r, d = result["return"], result["decision"]
    print("\n" + "-" * 72)
    print(f"{r['return_id']}  {r['account_id']}  ${r['amount']:,.2f}  {r['return_code']}   severity: {d['severity'].upper()}")
    print(f"Action: {d['action']}")
    print(f"Summary: {result['summary']}")
    print(f"Partner notice: {result['notice']}")
    if result["needs_attention"]:
        failed = [k for k, v in result["checks"].items() if not v]
        print(f"!! Agent check failed: {', '.join(failed)}. Review carefully.")
    if auto:
        return "auto-approved"
    while True:
        ans = input("Approve this action? [y]es / [n]o / [s]kip: ").strip().lower()
        if ans in ("y", "n", "s"):
            return {"y": "approved", "n": "rejected", "s": "skipped"}[ans]


def write_report(results: list, mode: str, path: Path) -> None:
    lines = [f"# ACH return triage report", "",
             f"Generated {datetime.now():%Y-%m-%d %H:%M} · mode: {mode} · {len(results)} returns", "",
             "| Return | Account | Amount | Code | Severity | Action | Human review | Decision |",
             "|---|---|---:|---|---|---|---|---|"]
    for x in results:
        r, d = x["return"], x["decision"]
        lines.append(f"| {r['return_id']} | {r['account_id']} | ${r['amount']:,.2f} | {r['return_code']} | "
                     f"{d['severity']} | {d['action']} | {'required' if d['human_review_required'] else '-'} | {x['review']} |")
    for x in results:
        r, d = x["return"], x["decision"]
        lines += ["", f"## {r['return_id']}: {r['return_code']}, ${r['amount']:,.2f}", "",
                  f"**Action:** {d['action']}  ", f"**Why:** " + " ".join(d["reasons"]), "",
                  f"**Summary:** {x['summary']}", "", f"**Partner notice:** {x['notice']}", "",
                  f"**Agent checks:** " + ", ".join(f"{k} {'✓' if v else '✗'}" for k, v in x["checks"].items()),
                  f"**Tools called:** " + " → ".join(t["tool"] for t in x["trace"])]
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main():
    p = argparse.ArgumentParser(description="ACH Return Triage Agent")
    p.add_argument("--offline", action="store_true", help="run without Claude (rules engine + template notices)")
    p.add_argument("--auto-approve", action="store_true", help="skip human approval prompts")
    p.add_argument("--batch", type=Path, help="CSV of returned deposits (default: data/returns_batch.csv)")
    p.add_argument("--out", type=Path, default=Path("reports/triage_report.md"))
    args = p.parse_args()

    batch = load_batch(args.batch)
    box = Toolbox(batch)

    if args.offline:
        mode, run = "offline (rules only)", lambda r: triage_offline(r, box)
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("Set ANTHROPIC_API_KEY, or run with --offline.")
        import anthropic
        client = anthropic.Anthropic()
        mode, run = f"agent ({MODEL})", lambda r: triage_with_claude(r, box, client)

    print(f"Triaging {len(batch)} returned deposits · {mode}")
    results = [run(r) for r in batch]
    results.sort(key=lambda x: SEV_ORDER[x["decision"]["severity"]])  # worst first
    for x in results:
        x["review"] = review(x, args.auto_approve)

    write_report(results, mode, args.out)
    high = sum(x["decision"]["severity"] == "high" for x in results)
    print(f"\nDone. {high} high-severity returns. Report saved to {args.out}")


if __name__ == "__main__":
    main()
