#!/usr/bin/env python3
"""
Unofficial, HTTP-only client for e-distribucion (zonaprivada.edistribucion.com).

No browser and no third-party dependencies (standard library only).

How it works (Salesforce Experience Cloud / Aura):
  - The authenticated session lives in the `sid` cookie.
  - The anti-CSRF `aura.token` does not need to be decoded: the server returns
    it on the `Set-Cookie` header `__Host-ERIC_PROD...=eyJ...` every time a
    community page is loaded. This client reads it from there and reuses it,
    refreshing automatically when needed.
  - Actions are invoked with POST to `/s/sfsites/aura` using
    message / aura.context / aura.pageURI / aura.token.

Session: sesion.json (or the EDIST_SID environment variable). Commands:
  python edistribucion.py login
  python edistribucion.py save --sid "<sid cookie value>"
  python edistribucion.py status
  python edistribucion.py cups
  python edistribucion.py periods [--cont <contId>]
  python edistribucion.py month --month 2026-09 [--cont <contId>] [--json]
  python edistribucion.py range --from 2026-09-01 --to 2026-09-30 [--cont <contId>] [--json]
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta

BASE = "https://zonaprivada.edistribucion.com"
SITE = BASE + "/areaprivada"
AURA_ENDPOINT = SITE + "/s/sfsites/aura"
HOME_PAGE = "/areaprivada/s/"
LOGIN_PAGE = "/areaprivada/s/login/"
MEASURELIST_PAGE = "/areaprivada/s/wp-measurelist-v4"
DETAIL_PAGE = "/areaprivada/s/wp-measure-detail-v4"

DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SESSION = os.path.join(DIR, "sesion.json")
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# Aura app framework UID for the community app (stable value).
FWUID = "WUdfaXlIZDNDQ0lZLWNFZDMtVGZ3d2tVMjdnTGFERUU2S3FfSVdrcU92bkExNC4xOTIuODM4ODYwOA"
APP_VERSION = "1712_xZHiuQoc1HHcvGz4vs6mGA"

# action alias -> (URL route, server descriptor, calling component)
ACTIONS = {
    "login_info": ("WP_Monitor_CTRL.getLoginInfo",
                   "apex://WP_Monitor_CTRL/ACTION$getLoginInfo",
                   "markup://c:WP_Monitor"),
    "list_cups": ("WP_Measure_v3_CTRL.getListCups",
                  "apex://WP_Measure_v3_CTRL/ACTION$getListCups",
                  "markup://c:WP_Measure_List_v4"),
    "get_info": ("WP_Measure_v3_CTRL.getInfo",
                 "apex://WP_Measure_v3_CTRL/ACTION$getInfo",
                 "markup://c:WP_Measure_Detail_v4"),
    "curve": ("WP_Measure_v3_CTRL.getChartPointsByRange",
              "apex://WP_Measure_v3_CTRL/ACTION$getChartPointsByRange",
              "markup://c:WP_Measure_Detail_Filter_By_Dates_v3"),
}

METHODS = {"R": "measured", "E": "estimated", "C": "calculated"}


# ---------------------------------------------------------------- session/HTTP
class Session:
    """Holds the session cookies and persists them to disk."""

    def __init__(self, sid=None, cookies=None, path=DEFAULT_SESSION):
        self.path = path
        self.cookies = {}
        if os.path.exists(path):
            try:
                data = json.load(open(path, encoding="utf-8"))
                self.cookies = data.get("cookies", {})
            except Exception:
                pass
        if sid:
            self.cookies["sid"] = sid
        elif os.environ.get("EDIST_SID") and "sid" not in self.cookies:
            self.cookies["sid"] = os.environ["EDIST_SID"]
        if cookies:
            self.cookies.update(cookies)

    @property
    def sid(self):
        return self.cookies.get("sid")

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"cookies": self.cookies}, fh, ensure_ascii=False, indent=2)

    def cookie_header(self):
        return "; ".join("%s=%s" % (k, v) for k, v in self.cookies.items())


class Client:
    def __init__(self, session):
        self.session = session
        self._tokens = {}

    # --- low level HTTP ---
    def _request(self, method, url, data=None, extra_headers=None):
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if self.session.sid:
            headers["Cookie"] = self.session.cookie_header()
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.status, response.headers, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read().decode("utf-8", "replace")

    # --- anti-CSRF token delivered via Set-Cookie ---
    def token(self, page_uri, force=False):
        if not force and page_uri in self._tokens:
            return self._tokens[page_uri]
        status, headers, _ = self._request(
            "GET", BASE + page_uri,
            extra_headers={"Accept": "text/html,application/xhtml+xml"})
        token = None
        for cookie in (headers.get_all("Set-Cookie") or []):
            match = re.match(r"(__Host-ERIC[A-Za-z0-9_\-]*)=([^;]+)", cookie)
            if match and match.group(2).startswith("eyJ"):
                token = match.group(2)
        if not token:
            raise RuntimeError("Could not obtain aura.token (expired session?). HTTP %s" % status)
        self._tokens[page_uri] = token
        return token

    # --- generic Aura call ---
    def call(self, action, params, page_uri, retry=True):
        route, descriptor, calling = ACTIONS[action]
        token = self.token(page_uri)
        message = json.dumps({"actions": [{"id": "1;a", "descriptor": descriptor,
                                           "callingDescriptor": calling, "params": params}]},
                             separators=(",", ":"))
        context = json.dumps({"mode": "PROD", "fwuid": FWUID, "app": "siteforce:communityApp",
                              "loaded": {"APPLICATION@markup://siteforce:communityApp": APP_VERSION},
                              "dn": [], "globals": {}, "uad": True}, separators=(",", ":"))
        body = urllib.parse.urlencode({"message": message, "aura.context": context,
                                       "aura.pageURI": page_uri, "aura.token": token}).encode()
        status, _, text = self._request(
            "POST", "%s?r=1&other.%s=1" % (AURA_ENDPOINT, route), data=body,
            extra_headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                           "Origin": BASE, "Referer": BASE + page_uri})
        if "/*ERROR*/" in text and retry:
            # stale token: refresh once and retry
            self.token(page_uri, force=True)
            return self.call(action, params, page_uri, retry=False)
        try:
            payload = json.loads(text)
        except Exception:
            raise RuntimeError("Non-JSON response: " + text[:200])
        result = (payload.get("actions") or [{}])[0]
        if result.get("state") != "SUCCESS":
            raise RuntimeError("Aura error (%s): %s" % (action, result.get("error") or result.get("state")))
        return result.get("returnValue")

    # --- high level API ---
    def whoami(self):
        result = self.call("login_info", {"serviceNumber": ""}, HOME_PAGE)
        auth = result.get("authList") or []
        return {
            "name": result.get("Name"),
            "visibility_id": (result.get("visibility") or {}).get("Id"),
            "profiles": [item.get("label") for item in auth],
            "auth_list": auth,
        }

    def list_supplies(self, visibility_id):
        result = self.call("list_cups", {"sIdentificador": visibility_id}, MEASURELIST_PAGE)
        supplies = []
        for contract in (result.get("data") or {}).get("lstContAux", []):
            cups = contract.get("CUPs__r") or {}
            power = {key.replace("Requested_power_", "P").replace("__c", ""): value
                     for key, value in contract.items()
                     if key.startswith("Requested_power_") and value is not None}
            supplies.append({
                "contract_id": contract.get("Id"),
                "cups": cups.get("Name"),
                "tariff": contract.get("Tariff_Code_Description__c"),
                "type_pm": contract.get("Type_PM__c"),
                "start": contract.get("Version_start_date__c"),
                "end": contract.get("Version_end_date__c"),
                "address": cups.get("Provisioning_address__c"),
                "city": cups.get("NS_Town_Description__c"),
                "postal_code": cups.get("NS_Postal_Code__c"),
                "voltage": cups.get("type_of_tension__c"),
                "contracted_power_kw": power,
            })
        return supplies

    def get_info(self, contract_id, visibility_id):
        page = "%s?aId=%s&vis=%s" % (DETAIL_PAGE, contract_id, visibility_id)
        return self.call("get_info", {"contId": contract_id, "visId": visibility_id}, page).get("data", {})

    def get_curve(self, contract_id, date_from, date_to, visibility_id=None):
        page = DETAIL_PAGE
        if visibility_id:
            page = "%s?aId=%s&vis=%s" % (DETAIL_PAGE, contract_id, visibility_id)
        params = {"contId": contract_id, "type": "4", "startDate": date_from, "endDate": date_to}
        return self.call("curve", params, page).get("data", {})


# ---------------------------------------------------------------- parsing
def _date_sort_key(value):
    try:
        return datetime.strptime(value, "%d/%m/%Y")
    except Exception:
        return datetime.max


def parse_curve(data):
    """Normalize returnValue.data from getChartPointsByRange into a flat list."""
    rows = []
    flat = []
    for item in (data.get("lstData") or []):
        if isinstance(item, list):
            flat.extend(item)
        elif isinstance(item, dict):
            flat.append(item)
    for item in flat:
        period = item.get("tariffPeriod")
        rows.append({
            "date": item.get("date"),
            "hour": item.get("hour"),
            "kwh": item.get("valueDouble"),
            "period": ("P" + str(period)) if period else None,
            "real": bool(item.get("real")),
            "method": METHODS.get(item.get("obtainingMethod"), item.get("obtainingMethod")),
            "invoiced": bool(item.get("invoiced")),
            "valid": bool(item.get("valid")),
        })
    return rows


def summarize(data):
    """Totals per day, per tariff period (P1/P2/P3) and measured vs estimated."""
    rows = parse_curve(data)
    periods = {}
    days = {}
    total = measured_kwh = estimated_kwh = 0.0
    for row in rows:
        kwh = row["kwh"] or 0.0
        total += kwh
        if row["period"]:
            periods[row["period"]] = round(periods.get(row["period"], 0.0) + kwh, 3)
        day = days.setdefault(row["date"], {"date": row["date"], "kwh": 0.0, "periods": {},
                                            "measured_hours": 0, "estimated_hours": 0})
        day["kwh"] = round(day["kwh"] + kwh, 3)
        if row["period"]:
            day["periods"][row["period"]] = round(day["periods"].get(row["period"], 0.0) + kwh, 3)
        if row["method"] == "measured":
            day["measured_hours"] += 1
            measured_kwh += kwh
        elif row["method"] == "estimated":
            day["estimated_hours"] += 1
            estimated_kwh += kwh

    day_list = [days[key] for key in sorted(days, key=_date_sort_key)]
    for day in day_list:
        if day["estimated_hours"] and day["measured_hours"]:
            day["kind"] = "mixed"
        elif day["estimated_hours"]:
            day["kind"] = "estimated"
        elif day["measured_hours"]:
            day["kind"] = "measured"
        else:
            day["kind"] = "no_data"

    return {
        "cups": data.get("cupsName"),
        "total_kwh": round(total, 3),
        "total_api_kwh": float((data.get("totalValue") or "0").replace(",", ".")),
        "peak_demand_kw": data.get("maxPerMonth"),
        "periods_kwh": periods,
        "measured_kwh": round(measured_kwh, 3),
        "estimated_kwh": round(estimated_kwh, 3),
        "measured_hours": sum(day["measured_hours"] for day in day_list),
        "estimated_hours": sum(day["estimated_hours"] for day in day_list),
        "days": day_list,
        "hourly": rows,
    }


def parse_cookies_file(path):
    """Read a cookies file. Accepts Netscape cookies.txt or a JSON export.

    The browser extension 'Get cookies.txt LOCALLY' writes the Netscape format.
    Return a dict of name -> value.
    """
    text = open(path, encoding="utf-8", errors="replace").read()
    cookies = {}
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("cookies", data)
        for item in data:
            name = item.get("name")
            if name:
                cookies[name] = item.get("value")
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    return cookies


# ---------------------------------------------------------------- CLI helpers
KIND_LABELS = {"measured": "MEASURED", "estimated": "ESTIMATED",
               "mixed": "MIXED", "no_data": "NO DATA"}


def build_client(args):
    return Client(Session(sid=getattr(args, "sid", None), path=args.session))


def load_context(args):
    client = build_client(args)
    account = client.whoami()
    supplies = client.list_supplies(account["visibility_id"])
    return client, account, supplies


def default_contract(account, supplies, contract):
    if contract:
        return contract
    for item in supplies:
        if not item.get("end"):
            return item["contract_id"]
    return supplies[0]["contract_id"]


def print_summary(summary, date_from, date_to, contract, as_json):
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print("CUPS:", summary["cups"], "| contractId:", contract)
    print("Range:", date_from, "->", date_to)
    print("Total:", summary["total_kwh"], "kWh | peak demand:", summary["peak_demand_kw"], "kW")
    print("Periods (kWh):", summary["periods_kwh"])
    print("Measured:", summary["measured_kwh"], "kWh (%d h)" % summary["measured_hours"],
          "| Estimated:", summary["estimated_kwh"], "kWh (%d h)" % summary["estimated_hours"])
    print("\nDaily detail:")
    for day in summary["days"]:
        print("  %s  %8.3f kWh  %-9s %s" %
              (day["date"], day["kwh"], KIND_LABELS[day["kind"]], day["periods"]))


# ---------------------------------------------------------------- commands
def cmd_save(args):
    session = Session(sid=args.sid, path=args.session)
    if args.cookie:
        for pair in args.cookie.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                session.cookies[key] = value
    session.save()
    print("Session saved to", args.session)
    print("cookies:", ", ".join(session.cookies.keys()))


def cmd_import_cookies(args):
    cookies = parse_cookies_file(args.file)
    session = Session(path=args.session)
    session.cookies.update(cookies)
    session.save()
    print("Imported %d cookies into %s" % (len(cookies), args.session))
    print("sid found:", "yes" if session.cookies.get("sid") else "no")


COOKIE_NAMES = ("sid", "oid", "sid_Client", "inst", "clientSrc")


def extract_cookies_from_text(text):
    """Find cookie pairs in a Cookie header or a cURL line."""
    found = {}
    for name in COOKIE_NAMES:
        match = re.search(r"(?:^|[;\s'\"]|:)%s=([^;'\"\s]+)" % re.escape(name), text)
        if match:
            found[name] = match.group(1)
    return found


def cmd_login(args):
    print("Opening the login page in your browser...")
    webbrowser.open(BASE + LOGIN_PAGE)
    print()
    print("Log in to the portal. Then choose how to return the session:")
    print("  1. Paste a line from DevTools (the Cookie header, or 'Copy as cURL').")
    print("  2. Import a cookies.txt file.")
    print("  3. Let the agent read it with the Chrome MCP.")
    method = args.method or (input("Choose 1, 2 or 3 [1]: ").strip() or "1")

    session = Session(path=args.session)
    if method == "1":
        text = input("Paste the Cookie header or cURL line: ").strip()
        cookies = extract_cookies_from_text(text)
        if not cookies.get("sid"):
            print("No sid found in the text.", file=sys.stderr)
            sys.exit(1)
        session.cookies.update(cookies)
    elif method == "2":
        path = input("Path to cookies.txt [cookies.txt]: ").strip() or "cookies.txt"
        cookies = parse_cookies_file(path)
        if not cookies.get("sid"):
            print("No sid found in", path, file=sys.stderr)
            sys.exit(1)
        session.cookies.update(cookies)
    elif method == "3":
        print("Ask the agent: 'save my e-distribucion session'.")
        print("The agent uses the Chrome MCP and calls the tool edist_save_session.")
        return
    else:
        print("Unknown method:", method, file=sys.stderr)
        sys.exit(1)

    session.save()
    print("Session saved to", args.session)
    try:
        account = Client(session).whoami()
        print("Login OK. User:", account["name"])
    except Exception as exc:
        print("Session saved, but the check failed:", exc, file=sys.stderr)
        sys.exit(1)


def cmd_status(args):
    client, account, supplies = load_context(args)
    print(json.dumps({"name": account["name"], "supplies": len(supplies),
                      "cups": [{"contract_id": item["contract_id"], "cups": item["cups"],
                                "contracted_power_kw": item["contracted_power_kw"],
                                "start": item["start"], "end": item["end"]}
                               for item in supplies]}, ensure_ascii=False, indent=2))


def cmd_cups(args):
    _, _, supplies = load_context(args)
    print(json.dumps(supplies, ensure_ascii=False, indent=2))


def cmd_periods(args):
    client, account, supplies = load_context(args)
    contract = default_contract(account, supplies, args.cont)
    info = client.get_info(contract, account["visibility_id"])
    print("CUPS:", info.get("cups"), "| available:", info.get("minDate"), "->", info.get("maxDate"))
    print("\nBilling periods / contracts:")
    for item in supplies:
        if not args.cont or item["contract_id"] == contract:
            print("  %-14s %s -> %s  tariff=%s  power=%s" %
                  (item["contract_id"], item["start"], item["end"] or "(open)",
                   item["tariff"], item["contracted_power_kw"]))


def _month_bounds(month):
    year, mon = int(month[:4]), int(month[5:7])
    first = date(year, mon, 1)
    last = date(year + (mon // 12), (mon % 12) + 1, 1) - timedelta(days=1)
    return first, last


def cmd_month(args):
    client, account, supplies = load_context(args)
    contract = default_contract(account, supplies, args.cont)
    first, last = _month_bounds(args.month)
    date_to = min(last, date.today())
    info = client.get_info(contract, account["visibility_id"])
    date_from = first.isoformat()
    if info.get("minDate") and date_from < info["minDate"]:
        date_from = info["minDate"]
    if info.get("maxDate") and date_to.isoformat() > info["maxDate"]:
        date_to = datetime.strptime(info["maxDate"], "%Y-%m-%d").date()
    data = client.get_curve(contract, date_from, date_to.isoformat(), account["visibility_id"])
    summary = summarize(data)
    if not args.json:
        print("Month %s (available %s -> %s)" % (args.month, date_from, date_to.isoformat()))
    print_summary(summary, date_from, date_to.isoformat(), contract, args.json)


def cmd_range(args):
    client, account, supplies = load_context(args)
    contract = default_contract(account, supplies, args.cont)
    data = client.get_curve(contract, args.date_from, args.date_to, account["visibility_id"])
    print_summary(summarize(data), args.date_from, args.date_to, contract, args.json)


def cmd_parse(args):
    raw = json.load(open(args.file, encoding="utf-8"))
    if "actions" in raw:
        data = raw["actions"][0]["returnValue"]["data"]
    else:
        data = raw.get("returnValue", {}).get("data", raw)
    print(json.dumps(summarize(data), ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(
        description="Unofficial HTTP-only client for e-distribucion (no browser)")
    parser.add_argument("--session", default=DEFAULT_SESSION, help="path to the session file")
    parser.add_argument("--sid", help="value of the sid cookie")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--session", default=argparse.SUPPRESS)
    common.add_argument("--sid", default=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    save = sub.add_parser("save", parents=[common], help="store the session cookie")
    save.add_argument("--cookie", help="extra cookies: 'k=v; k2=v2'")
    save.set_defaults(func=cmd_save)

    imp = sub.add_parser("import-cookies", parents=[common],
                         help="import cookies from a cookies.txt (Netscape) or JSON file")
    imp.add_argument("file", help="path to cookies.txt or JSON export")
    imp.set_defaults(func=cmd_import_cookies)

    login = sub.add_parser("login", parents=[common],
                           help="open the login page and save the session")
    login.add_argument("--method", choices=["1", "2", "3"],
                       help="1 paste, 2 cookies file, 3 agent")
    login.set_defaults(func=cmd_login)

    sub.add_parser("status", parents=[common],
                   help="account and supplies").set_defaults(func=cmd_status)
    sub.add_parser("cups", parents=[common], help="list supplies").set_defaults(func=cmd_cups)

    periods = sub.add_parser("periods", parents=[common], help="billing periods / contracts")
    periods.add_argument("--cont")
    periods.set_defaults(func=cmd_periods)

    month = sub.add_parser("month", parents=[common],
                           help="consumption for a full month (P1/P2/P3, measured/estimated)")
    month.add_argument("--month", required=True, help="YYYY-MM, e.g. 2026-09")
    month.add_argument("--cont")
    month.add_argument("--json", action="store_true")
    month.set_defaults(func=cmd_month)

    rng = sub.add_parser("range", parents=[common], help="consumption for a date range")
    rng.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    rng.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    rng.add_argument("--cont")
    rng.add_argument("--json", action="store_true")
    rng.set_defaults(func=cmd_range)

    parse = sub.add_parser("parse", parents=[common], help="parse a previously saved response")
    parse.add_argument("--file", required=True)
    parse.set_defaults(func=cmd_parse)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
