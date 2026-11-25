"""The agent loop: Claude investigates each returned ACH deposit with tools,
follows the binding policy, and drafts a partner notice. Code then checks that
Claude actually followed the policy before anything reaches a human reviewer."""

import os
import re

from .tools import TOOL_SCHEMAS, Toolbox

MODEL = os.environ.get("ACH_AGENT_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 10  # safety cap on tool calls per return

SYSTEM_PROMPT = """You are an ACH returns analyst at a broker-dealer that powers investing inside partner apps.
A customer's ACH deposit has been returned. Investigate it with your tools, in this order:
1. lookup_return_code for the return code.
2. get_account for the account.
3. get_policy_decision for the return. This decision is BINDING. Never recommend a different action.
4. save_partner_notice with a short notice (under 90 words) to the partner app's operations team:
   what happened, the amount, the action being taken, and what (if anything) the partner should ask the customer to do.
   Be factual. Do not speculate about fraud beyond what the code means. Do not promise outcomes.
Then reply with a 2-3 sentence plain-English summary for the human reviewer, and end with one line exactly like:
FINAL_ACTION: <the action from the policy decision>"""


def triage_with_claude(ret: dict, box: Toolbox, client, model: str = MODEL) -> dict:
    """Run the agent on one returned deposit and return a reviewable result."""
    trace = []
    messages = [{"role": "user", "content": (
        f"Returned deposit {ret['return_id']}: account {ret['account_id']}, ${ret['amount']:,.2f}, "
        f"code {ret['return_code']}, originally sent {ret['original_entry_date']}, returned {ret['return_date']}.")}]

    final_text = ""
    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=model, max_tokens=1024, system=SYSTEM_PROMPT,
                                      tools=TOOL_SCHEMAS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            final_text = "".join(b.text for b in resp.content if b.type == "text")
            break
        results = []
        for tu in tool_uses:
            out = box.run(tu.name, tu.input)
            trace.append({"tool": tu.name, "input": tu.input, "output": out})
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": str(out)})
        messages.append({"role": "user", "content": results})
    else:
        final_text = "Agent hit the step limit without finishing."

    return _finalize(ret, box, final_text, trace)


def triage_offline(ret: dict, box: Toolbox) -> dict:
    """Same pipeline with no AI: rules engine plus a template notice.
    Lets anyone run the demo without an API key."""
    code = box.lookup_return_code(ret["return_code"])
    acct = box.get_account(ret["account_id"])
    decision = box.get_policy_decision(ret["return_id"])
    trace = [{"tool": "lookup_return_code", "output": code},
             {"tool": "get_account", "output": acct},
             {"tool": "get_policy_decision", "output": decision}]
    action = decision["action"].replace("_", " ")
    notice = (f"Deposit of ${ret['amount']:,.2f} for account {ret['account_id']} was returned "
              f"({ret['return_code']}: {code.get('name', 'unrecognized code')}). Action: {action}."
              + (" Buying power is restricted until resolved." if decision["restrict_buying_power"] else ""))
    box.save_partner_notice(ret["return_id"], notice)
    summary = f"{decision['reasons'][0]}\nFINAL_ACTION: {decision['action']}"
    return _finalize(ret, box, summary, trace)


def _finalize(ret: dict, box: Toolbox, final_text: str, trace: list) -> dict:
    """The policy engine is the source of truth. Check the agent against it."""
    decision = box.get_policy_decision(ret["return_id"])
    m = re.search(r"FINAL_ACTION:\s*([a-z_]+)", final_text)
    agent_action = m.group(1) if m else None

    checks = {
        "called_policy": any(t["tool"] == "get_policy_decision" for t in trace),
        "action_matches_policy": agent_action == decision["action"],
        "notice_drafted": ret["return_id"] in box.notices,
    }
    summary = re.sub(r"\n?FINAL_ACTION:.*", "", final_text).strip()
    return {
        "return": ret,
        "decision": decision,
        "summary": summary,
        "notice": box.notices.get(ret["return_id"], ""),
        "checks": checks,
        "needs_attention": not all(checks.values()),
        "trace": trace,
    }
