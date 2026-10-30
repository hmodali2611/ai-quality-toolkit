"""
The agent under test: a tool-using order-support agent.

  v1  follows the policy: look up the order, check eligibility BEFORE creating a return,
      escalate legal threats and angry customers to a human, ask for an order id when missing.
  v2  a "fewer tool calls = faster" prompt change. With the mock planner it skips the
      eligibility check (refunding an ineligible order), guesses delivery dates instead of
      tracking, and stops escalating. Exactly the regressions agent evals exist to catch.

AGENT_PROVIDER=mock (default, offline) or openai (real function calling with OPENAI_API_KEY).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field

from .tools import TOOL_SPECS, Backend

POLICY = {
    "v1": "You are ShopLite's order-support agent. Always look up the order first. Before create_return you MUST call "
    "check_return_eligibility and only create the return if eligible. Use track_shipment for delivery questions. "
    "Escalate legal threats or very angry customers with escalate_to_human. If no order id is given, ask for it.",
    "v2": "You are ShopLite's order-support agent. Minimize tool calls to keep latency low.",
}


@dataclass
class AgentRun:
    task: str
    final_answer: str
    tool_calls: list[dict] = field(default_factory=list)
    returns_created: list[str] = field(default_factory=list)


class SupportAgent:
    def __init__(self, version: str = "v1", provider: str | None = None, max_steps: int = 6):
        if version not in POLICY:
            raise ValueError(f"unknown version {version}")
        self.version, self.max_steps = version, max_steps
        self.provider = (provider or os.environ.get("AGENT_PROVIDER", "mock")).lower()

    def run(self, task: str) -> AgentRun:
        backend = Backend()
        answer = self._openai(task, backend) if self.provider == "openai" else self._mock(task, backend)
        return AgentRun(task, answer, backend.calls, backend.returns_created)

    # ---- deterministic planner standing in for a model ---------------------------------------
    def _mock(self, task: str, b: Backend) -> str:
        t = task.lower()
        m = re.search(r"\b([A-Z]\d{3})\b", task, re.I)
        order_id = m.group(1).upper() if m else None
        escalate = re.search(r"lawyer|sue|legal|furious|unacceptable", t)

        if escalate and self.version == "v1":
            b.call("escalate_to_human", {"summary": task[:200]})
            return "I'm sorry about this. I've passed your case to a human specialist who will contact you shortly."
        if not order_id:
            return "I can help with that. Could you share your order number (for example A100)?"

        order = b.call("lookup_order", {"order_id": order_id})
        if "error" in order:
            return f"I couldn't find order {order_id}. Could you double-check the order number?"

        if re.search(r"return|refund|send (it )?back", t):
            if self.version == "v1":
                elig = b.call("check_return_eligibility", {"order_id": order_id})
                if not elig["eligible"]:
                    return f"I'm sorry, order {order_id} can't be returned: {elig['reason']}."
            ret = b.call("create_return", {"order_id": order_id, "reason": "customer request"})
            return f"Your return {ret['return_id']} is created. A refund of ${ret['refund']:.2f} will be issued."

        if re.search(r"where|track|arrive|delivery|shipping status", t):
            if self.version == "v1":
                ship = b.call("track_shipment", {"order_id": order_id})
                if "error" in ship:
                    return f"Order {order_id} is {order['status'].replace('_', ' ')}; there is no active shipment to track."
                return f"Order {order_id} is on its way with {ship['carrier']}, arriving {ship['eta']}."
            return f"Order {order_id} should arrive in a few days."  # v2 guesses

        return f"Order {order_id}: {order['item']}, status {order['status'].replace('_', ' ')}."

    # ---- real model with function calling ----------------------------------------------------
    def _openai(self, task: str, b: Backend) -> str:
        tools = [
            {"type": "function", "function": {"name": s["name"], "description": s["description"],
             "parameters": {"type": "object", "properties": {k: {"type": v} for k, v in s["params"].items()},
                            "required": list(s["params"])}}}
            for s in TOOL_SPECS
        ]
        messages = [{"role": "system", "content": POLICY[self.version]}, {"role": "user", "content": task}]
        for _ in range(self.max_steps):
            body = {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "temperature": 0, "messages": messages, "tools": tools}
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                headers={"content-type": "application/json", "authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            )
            with urllib.request.urlopen(req, timeout=60) as res:
                msg = json.loads(res.read())["choices"][0]["message"]
            messages.append(msg)
            if not msg.get("tool_calls"):
                return msg.get("content") or ""
            for call in msg["tool_calls"]:
                result = b.call(call["function"]["name"], json.loads(call["function"]["arguments"] or "{}"))
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
        return "I couldn't finish this request."
