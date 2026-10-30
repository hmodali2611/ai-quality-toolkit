"""Fake order-support backend the agent acts on. Every call is logged so evals can inspect it."""

from __future__ import annotations

from dataclasses import dataclass, field

ORDERS = {
    "A100": {"item": "Wireless Earbuds", "price": 49.0, "status": "delivered", "days_since_delivery": 10, "used": False},
    "A200": {"item": "Phone Case", "price": 19.0, "status": "delivered", "days_since_delivery": 45, "used": False},
    "A300": {"item": "Smart Watch", "price": 199.0, "status": "in_transit", "carrier": "UPS", "eta": "Nov 3"},
}

TOOL_SPECS = [
    {"name": "lookup_order", "description": "Get an order's item, price and status.", "params": {"order_id": "string"}},
    {"name": "check_return_eligibility", "description": "Check if an order can be returned (30-day window, unused).", "params": {"order_id": "string"}},
    {"name": "create_return", "description": "Create a return and refund. Only after eligibility is confirmed.", "params": {"order_id": "string", "reason": "string"}},
    {"name": "track_shipment", "description": "Get carrier and ETA for an order in transit.", "params": {"order_id": "string"}},
    {"name": "escalate_to_human", "description": "Hand the conversation to a human agent.", "params": {"summary": "string"}},
]


@dataclass
class Backend:
    calls: list[dict] = field(default_factory=list)
    returns_created: list[str] = field(default_factory=list)

    def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name == "call":
            result = {"error": f"unknown tool {name}"}
        else:
            try:
                result = fn(**args)
            except TypeError as e:
                result = {"error": f"bad arguments: {e}"}
        self.calls.append({"name": name, "args": args, "result": result})
        return result

    def lookup_order(self, order_id: str) -> dict:
        order = ORDERS.get(order_id.upper())
        return {"order_id": order_id.upper(), **order} if order else {"error": f"order {order_id} not found"}

    def check_return_eligibility(self, order_id: str) -> dict:
        order = ORDERS.get(order_id.upper())
        if not order:
            return {"error": f"order {order_id} not found"}
        if order["status"] != "delivered":
            return {"eligible": False, "reason": "order has not been delivered yet"}
        if order["days_since_delivery"] > 30:
            return {"eligible": False, "reason": f"delivered {order['days_since_delivery']} days ago; the return window is 30 days"}
        return {"eligible": True, "reason": "within the 30-day window"}

    def create_return(self, order_id: str, reason: str = "") -> dict:
        self.returns_created.append(order_id.upper())
        return {"return_id": f"RMA-{order_id.upper()}", "refund": ORDERS.get(order_id.upper(), {}).get("price")}

    def track_shipment(self, order_id: str) -> dict:
        order = ORDERS.get(order_id.upper(), {})
        if order.get("status") != "in_transit":
            return {"error": "no active shipment"}
        return {"carrier": order["carrier"], "eta": order["eta"]}

    def escalate_to_human(self, summary: str) -> dict:
        return {"ticket": "HUMAN-1", "summary": summary}
