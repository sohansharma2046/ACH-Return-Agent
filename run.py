"""Triage today's returned ACH deposits.

    python run.py              uses Claude if ANTHROPIC_API_KEY is set, otherwise runs offline
    python run.py --offline    rules engine and template text only, no AI, no key needed
    python run.py --review     approve or reject each action in the terminal

Writes reports/triage_report.md (for people) and reports/latest_run.json (for other systems).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ach_agent.agent import MODEL, run_agent, run_offline
from ach_agent.data import SampleData
from ach_agent.report import write
from ach_agent.tools import Toolbox


def review(run: dict) -> None:
    """Human in the loop: nothing happens until a person approves it."""
    for c in run["cases"]:
        r, d = c["return"], c["decision"]
        print(f"\n{r['return_id']}  {r['return_code']}  ${r['amount']:,.2f}  {d['severity'].upper()}  ->  {d['action']}")
        for reason in d["reasons"]:
            print(f"   - {reason}")
        if c["notice"]:
            print(f"   Notice ({c['notice']['status']}): {c['notice']['notice']}")
        answer = ""
        while answer not in ("y", "n", "s"):
            answer = input("   Approve? [y]es / [n]o / [s]kip: ").strip().lower()
        c["approval"] = {"y": "approved", "n": "rejected", "s": "pending"}[answer]


def main() -> None:
    p = argparse.ArgumentParser(description="ACH Return Triage Agent")
    p.add_argument("--offline", action="store_true", help="no AI: rules engine and template text")
    p.add_argument("--review", action="store_true", help="approve or reject each action")
    p.add_argument("--batch", type=Path, help="CSV of returned deposits (default: data/returns_batch.csv)")
    p.add_argument("--out", type=Path, default=Path("reports"))
    args = p.parse_args()

    box = Toolbox(SampleData(batch_file=args.batch))
    if args.offline or not os.environ.get("ANTHROPIC_API_KEY"):
        if not args.offline:
            print("No ANTHROPIC_API_KEY found, so running offline (rules only). Set a key to run the AI agent.")
        run = run_offline(box)
    else:
        import anthropic
        print(f"Running the agent with {MODEL} on {len(box.batch)} returned deposits...")
        run = run_agent(box, anthropic.Anthropic())

    if args.review:
        review(run)
    md, js = write(run, args.out)

    t, b = run["totals"], run["briefing"]
    print(f"\n{b.get('headline', '')}\n")
    print(f"  {t['returns']} returns · ${t['total_returned']:,.2f} returned · ${t['deficits']:,.2f} in deficits · "
          f"${t['uncovered']:,.2f} unsecured · {t['need_human_review']} need a person · "
          f"{t['fraud_escalations']} fraud escalations")
    for c in run["cases"][:5]:
        r, d = c["return"], c["decision"]
        print(f"  {d['severity'].upper():6} {r['return_id']} {r['return_code']} ${r['amount']:>9,.2f}  {d['action']}")
    flagged = [c["return"]["return_id"] for c in run["cases"] if c["needs_attention"]]
    if flagged:
        print(f"\n  Agent checks failed on: {', '.join(flagged)}. See the report.")
    print(f"\nReport: {md}\nData for other systems: {js}")


if __name__ == "__main__":
    main()
