#!/usr/bin/env python3
"""
MCP (Model Context Protocol) server for e-distribucion.

Speaks MCP over stdio with no third-party dependencies and exposes tools that
let an agent query electricity consumption over plain HTTP (via edistribucion.py).
The session is read from EDIST_SID or from sesion.json.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edistribucion import (Client, Session, summarize, format_callback,  # noqa: E402
                           DEFAULT_SESSION, DEFAULT_CALLBACK)

PROTOCOL_VERSION = "2024-11-05"
KIND_LABELS = {"measured": "MEASURED", "estimated": "ESTIMATED",
               "mixed": "MIXED", "no_data": "NO DATA"}


def get_client():
    session = Session(path=DEFAULT_SESSION)
    if not session.sid:
        raise RuntimeError("No session. Run: python edistribucion.py save --sid <sid>")
    return Client(session)


def default_contract(account, supplies, contract):
    if contract:
        return contract
    for item in supplies:
        if not item.get("end"):
            return item["contract_id"]
    return supplies[0]["contract_id"]


def summary_text(summary, date_from, date_to, contract):
    lines = [
        "CUPS %s (contractId %s) from %s to %s" % (summary["cups"], contract, date_from, date_to),
        "Total: %s kWh | peak demand: %s kW" % (summary["total_kwh"], summary["peak_demand_kw"]),
        "Periods: %s" % summary["periods_kwh"],
        "Measured: %s kWh (%s h) | Estimated: %s kWh (%s h)" % (
            summary["measured_kwh"], summary["measured_hours"],
            summary["estimated_kwh"], summary["estimated_hours"]),
        "Daily detail:",
    ]
    for day in summary["days"]:
        lines.append("  %s  %8.3f kWh  %-9s %s" %
                     (day["date"], day["kwh"], KIND_LABELS[day["kind"]], day["periods"]))
    return "\n".join(lines)


def month_bounds(month):
    year, mon = int(month[:4]), int(month[5:7])
    first = date(year, mon, 1)
    last = date(year + (mon // 12), (mon % 12) + 1, 1) - timedelta(days=1)
    return first, last


# ---------------------------------------------------------------- tools
def tool_status(_args):
    client = get_client()
    account = client.whoami()
    supplies = client.list_supplies(account["visibility_id"])
    return json.dumps({"name": account["name"],
                       "supplies": [{"contract_id": item["contract_id"], "cups": item["cups"],
                                     "contracted_power_kw": item["contracted_power_kw"],
                                     "start": item["start"], "end": item["end"]}
                                    for item in supplies]}, ensure_ascii=False, indent=2)


def tool_supplies(_args):
    client = get_client()
    account = client.whoami()
    return json.dumps(client.list_supplies(account["visibility_id"]), ensure_ascii=False, indent=2)


def tool_read_callback(_args):
    if not os.path.exists(DEFAULT_CALLBACK):
        return "No callback yet. Open the portal, log in, and click the bookmarklet."
    payload = json.load(open(DEFAULT_CALLBACK, encoding="utf-8"))
    return format_callback(payload)


def tool_save_session(args):
    sid = args.get("sid")
    if not sid:
        raise RuntimeError("Missing sid")
    session = Session(sid=sid)
    session.save()
    account = Client(session).whoami()
    return "Session saved. User: %s" % account["name"]


def tool_periods(args):
    client = get_client()
    account = client.whoami()
    supplies = client.list_supplies(account["visibility_id"])
    contract = default_contract(account, supplies, args.get("cont"))
    info = client.get_info(contract, account["visibility_id"])
    return json.dumps({"cups": info.get("cups"), "minDate": info.get("minDate"),
                       "maxDate": info.get("maxDate"), "contract_id": contract,
                       "periods": [{"contract_id": item["contract_id"], "start": item["start"],
                                    "end": item["end"], "tariff": item["tariff"],
                                    "contracted_power_kw": item["contracted_power_kw"]}
                                   for item in supplies]}, ensure_ascii=False, indent=2)


def tool_month_consumption(args):
    client = get_client()
    account = client.whoami()
    supplies = client.list_supplies(account["visibility_id"])
    contract = default_contract(account, supplies, args.get("cont"))
    first, last = month_bounds(args["month"])
    date_to = min(last, date.today())
    info = client.get_info(contract, account["visibility_id"])
    date_from = first.isoformat()
    if info.get("minDate") and date_from < info["minDate"]:
        date_from = info["minDate"]
    if info.get("maxDate") and date_to.isoformat() > info["maxDate"]:
        date_to = datetime.strptime(info["maxDate"], "%Y-%m-%d").date()
    data = client.get_curve(contract, date_from, date_to.isoformat(), account["visibility_id"])
    summary = summarize(data)
    if args.get("json"):
        return json.dumps(summary, ensure_ascii=False, indent=2)
    return summary_text(summary, date_from, date_to.isoformat(), contract)


def tool_range_consumption(args):
    client = get_client()
    account = client.whoami()
    supplies = client.list_supplies(account["visibility_id"])
    contract = default_contract(account, supplies, args.get("cont"))
    data = client.get_curve(contract, args["from"], args["to"], account["visibility_id"])
    summary = summarize(data)
    if args.get("json"):
        return json.dumps(summary, ensure_ascii=False, indent=2)
    return summary_text(summary, args["from"], args["to"], contract)


TOOLS = [
    {"name": "edist_status",
     "description": "Account and supplies (CUPS) with contracted power.",
     "inputSchema": {"type": "object", "properties": {}},
     "fn": tool_status},
    {"name": "edist_supplies",
     "description": "List every supply (CUPS) with contracted power.",
     "inputSchema": {"type": "object", "properties": {}},
     "fn": tool_supplies},
    {"name": "edist_read_callback",
     "description": "Read the last result sent by the bookmarklet through the edist:// callback.",
     "inputSchema": {"type": "object", "properties": {}},
     "fn": tool_read_callback},
    {"name": "edist_save_session",
     "description": ("Save the session cookie. Use it after the agent reads the `sid` value "
                     "from the browser DevTools (for example from a portal request header)."),
     "inputSchema": {"type": "object", "properties": {
         "sid": {"type": "string", "description": "value of the sid cookie"}},
         "required": ["sid"]},
     "fn": tool_save_session},
    {"name": "edist_periods",
     "description": "Billing periods / contracts and the available date range.",
     "inputSchema": {"type": "object", "properties": {
         "cont": {"type": "string", "description": "optional contractId"}}},
     "fn": tool_periods},
    {"name": "edist_month_consumption",
     "description": ("Consumption for a full month, split by tariff period P1/P2/P3 and "
                     "flagged as measured or estimated."),
     "inputSchema": {"type": "object", "properties": {
         "month": {"type": "string", "description": "YYYY-MM, e.g. 2026-09"},
         "cont": {"type": "string", "description": "optional contractId"},
         "json": {"type": "boolean", "description": "return raw JSON instead of text"}},
         "required": ["month"]},
     "fn": tool_month_consumption},
    {"name": "edist_range_consumption",
     "description": "Consumption between two dates (YYYY-MM-DD), by period P1/P2/P3 and measured/estimated.",
     "inputSchema": {"type": "object", "properties": {
         "from": {"type": "string"}, "to": {"type": "string"},
         "cont": {"type": "string"}, "json": {"type": "boolean"}},
         "required": ["from", "to"]},
     "fn": tool_range_consumption},
]

TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


# ---------------------------------------------------------------- MCP stdio
def send(id_, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": id_}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(message):
    method = message.get("method")
    id_ = message.get("id")
    if method == "initialize":
        return send(id_, {
            "protocolVersion": message.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "edistribucion", "version": "1.0.0"},
        })
    if method in ("notifications/initialized", "initialized"):
        return
    if method == "ping":
        return send(id_, {})
    if method == "tools/list":
        return send(id_, {"tools": [{"name": t["name"], "description": t["description"],
                                     "inputSchema": t["inputSchema"]} for t in TOOLS]})
    if method == "tools/call":
        params = message.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOLS_BY_NAME:
            return send(id_, error={"code": -32602, "message": "unknown tool: %s" % name})
        try:
            text = TOOLS_BY_NAME[name]["fn"](arguments)
            return send(id_, {"content": [{"type": "text", "text": text}]})
        except Exception as exc:
            return send(id_, {"content": [{"type": "text", "text": "ERROR: %s" % exc}], "isError": True})
    if id_ is not None:
        return send(id_, error={"code": -32601, "message": "unsupported method: %s" % method})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except Exception:
            continue
        try:
            handle(message)
        except Exception as exc:
            if message.get("id") is not None:
                send(message["id"], error={"code": -32603, "message": str(exc)})


if __name__ == "__main__":
    main()
