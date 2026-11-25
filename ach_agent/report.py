"""Turns a run into the triage report people read (Markdown) and a JSON file
other systems can pick up (for example, a case-management queue)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


SHORT_ARGS = ("return_id", "account_id", "code", "partner", "query", "action_stated")


def money(x) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def write(run: dict, folder: Path) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    md, js = folder / "triage_report.md", folder / "latest_run.json"
    md.write_text(markdown(run))
    js.write_text(json.dumps(run, indent=2, default=str))
    return md, js


def markdown(run: dict) -> str:
    m, t, b, ac = run["meta"], run["totals"], run["briefing"], run["agent_checks"]
    d0 = date.fromisoformat(run["as_of"])
    day = f"{d0:%b} {d0.day}, {d0.year}"
    mode = (f"Claude agent (`{m['model']}`), {m['turns']} turns, {m['tool_calls']} tool calls"
            if m["mode"] == "agent" else "Offline: rules engine and template text, no AI")
    L = [f"# ACH return triage: {day}", "", f"**Mode:** {mode}", ""]

    if b:
        L += [f"> **{b.get('headline', '')}**", ">", f"> {b.get('leadership_summary', '')}", ""]

    L += ["| Returned deposits | Total returned | Deficits created | Positions that may need selling "
          "| Unsecured shortfall | Need a person | Fraud escalations |",
          "|---:|---:|---:|---:|---:|---:|---:|",
          f"| {t['returns']} | {money(t['total_returned'])} | {money(t['deficits'])} | "
          f"{money(t['covered_by_positions'])} | **{money(t['uncovered'])}** | {t['need_human_review']} | "
          f"{t['fraud_escalations']} |", ""]

    if b.get("key_risks"):
        L += ["## What needs attention", ""]
        for i, k in enumerate(b["key_risks"], 1):
            L.append(f"{i}. **{k.get('title', '')}** ({', '.join(k.get('return_ids', []))}): {k.get('why', '')}")
        L.append("")

    L += ["## Partner return rates vs. Nacha limits", "",
          "Trailing 60 days, including today's returns.", "",
          "| Partner | Unauthorized (limit 0.5%) | Administrative (limit 3%) | Overall (limit 15%) | Status |",
          "|---|---:|---:|---:|---|"]
    for p in run["partner_risk"]:
        cells = [f"{p['metrics'][k]['rate_pct']:.2f}%" + (" ⚠" if p["metrics"][k]["status"] != "ok" else "")
                 for k in ("unauthorized", "administrative", "overall")]
        L.append(f"| {p['partner']} | " + " | ".join(cells) + f" | **{p['status'].upper()}** |")
    L.append("")

    L += ["## Action queue (most severe first)", "",
          "| Return | Account | Code | Amount | Deficit | Action | Retry | Person needed | Notice |",
          "|---|---|---|---:|---:|---|---|---|---|"]
    for c in run["cases"]:
        r, d, n = c["return"], c["decision"], c["notice"]
        L.append(f"| {r['return_id']} | {r['account_id']} | {r['return_code']} | {money(r['amount'])} | "
                 f"{money(d['exposure'].get('deficit'))} | `{d['action']}` | {'yes' if d['retry'] else 'no'} | "
                 f"{'yes' if d['human_review'] else 'no'} | {n['status'] if n else 'missing'} |")
    L.append("")

    L += ["## Case details", ""]
    for c in run["cases"]:
        r, d, n = c["return"], c["decision"], c["notice"]
        L += [f"### {r['return_id']}: {r['return_code']}, {money(r['amount'])}, {d['severity'].upper()}", "",
              f"**Action:** `{d['action']}` · retry: {'yes' if d['retry'] else 'no'} · "
              f"restrict buying power: {'yes' if d['restrict_buying_power'] else 'no'} · "
              f"person needed: {'yes' if d['human_review'] else 'no'}", "",
              "**Why:**", *[f"- {x}" for x in d["reasons"]], ""]
        if r.get("addenda_info"):
            L += [f"**Bank addenda (untrusted):** `{r['addenda_info']}`", ""]
        if n:
            failed = [k for k, ok in n["checks"].items() if not ok]
            L += [f"**Partner notice ({n['status']}{': ' + ', '.join(failed) if failed else ''}):** {n['notice']}", ""]
        if c["needs_attention"]:
            L += ["**⚠ Agent check failed:** " + ", ".join(k for k, ok in c["checks"].items() if not ok), ""]
        L += [f"**Approval:** {c['approval']}", ""]

    L += ["## Agent reliability checks", "",
          f"- Briefing submitted: {'yes' if ac['briefing_submitted'] else 'no'}",
          f"- Policy decision checked for {ac['policy_checked']}/{ac['returns']} returns",
          f"- Partner notices ready to send: {ac['notices_ready']}/{ac['returns']}",
          f"- Notices blocked by checks: {', '.join(ac['notices_blocked']) or 'none'}",
          f"- Extra reviews the agent added: {', '.join(ac['reviews_added_by_agent']) or 'none'}"]
    if m["mode"] == "agent":
        L.append(f"- Tokens: {m['input_tokens']:,} in / {m['output_tokens']:,} out · {m['seconds']}s"
                 + (" · ⚠ hit the turn limit" if m.get("hit_turn_limit") else ""))
    L += ["", "<details><summary>Every tool call, in order</summary>", ""]
    L += [f"{i}. `{c['tool']}({', '.join(f'{k}={v!r}' for k, v in c['args'].items() if k in SHORT_ARGS)})`"
          + (" ⚠ error" if c["error"] else "") for i, c in enumerate(run["trace"], 1)]
    L += ["", "</details>", "", "_All data is fictional._", ""]
    return "\n".join(L)
