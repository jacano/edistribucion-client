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

Session: session.json (or the EDIST_SID environment variable). Commands:
  python edistribucion.py login-backend [--save] # log in with user and password
  python edistribucion.py import-cookies [FILE]  # import a cookies.txt
  python edistribucion.py save --sid "<value>"   # save a value by hand
  python edistribucion.py cups                   # list supplies
  python edistribucion.py consume [--from YYYY-MM-DD] [--to YYYY-MM-DD]
                                  [--group hour|day|month|year] [--cont <id>] [--json]
  python edistribucion.py maxpower [--from YYYY-MM] [--to YYYY-MM] [--cont <id>] [--json]
"""
import argparse
import base64
import ctypes
import getpass
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from datetime import date, datetime, timedelta

BASE = "https://zonaprivada.edistribucion.com"
SITE = BASE + "/areaprivada"
AURA_ENDPOINT = SITE + "/s/sfsites/aura"
HOME_PAGE = "/areaprivada/s/"
LOGIN_PAGE = "/areaprivada/s/login/"
MEASURELIST_PAGE = "/areaprivada/s/wp-measurelist-v4"
DETAIL_PAGE = "/areaprivada/s/wp-measure-detail-v4"
MAXPOWER_PAGE = "/areaprivada/s/wp-maximeterhistogramdetail"

DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SESSION = os.path.join(DIR, "session.json")
DEFAULT_CREDENTIALS = os.path.join(DIR, "credentials.json")
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# Aura app framework UID for the community app (stable value).
FWUID = "WUdfaXlIZDNDQ0lZLWNFZDMtVGZ3d2tVMjdnTGFERUU2S3FfSVdrcU92bkExNC4xOTIuODM4ODYwOA"
APP_VERSION = "1712_xZHiuQoc1HHcvGz4vs6mGA"
LOGIN_APP_VERSION = "1634_zEBwUiHiCUzHoP9klFUc9g"

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
    "maximeter": ("WP_MaximeterHistogram_CTRL.getHistogramPoints",
                  "apex://WP_MaximeterHistogram_CTRL/ACTION$getHistogramPoints",
                  "markup://c:WP_MaximeterHistogramDetail"),
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


def aura_context():
    return json.dumps({"mode": "PROD", "fwuid": FWUID, "app": "siteforce:communityApp",
                       "loaded": {"APPLICATION@markup://siteforce:communityApp": APP_VERSION},
                       "dn": [], "globals": {}, "uad": True}, separators=(",", ":"))


# ---------------------------------------------------------------- credentials
class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def dpapi_protect(data):
    """Encrypt bytes with the Windows Data Protection API."""
    if os.name != "nt":
        raise RuntimeError("Credential encryption needs Windows.")
    in_blob, _keep = _to_blob(data)
    out_blob = _DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0x01, ctypes.byref(out_blob))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def dpapi_unprotect(data):
    """Decrypt bytes that dpapi_protect made."""
    if os.name != "nt":
        raise RuntimeError("Credential decryption needs Windows.")
    in_blob, _keep = _to_blob(data)
    out_blob = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0x01, ctypes.byref(out_blob))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def save_credentials(username, password, path=DEFAULT_CREDENTIALS):
    blob = base64.b64encode(dpapi_protect(password.encode("utf-8"))).decode("ascii")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"system": "dpapi", "username": username, "password": blob}, fh, indent=2)
    return path


def load_credentials(path=DEFAULT_CREDENTIALS):
    data = json.load(open(path, encoding="utf-8"))
    if data.get("system") != "dpapi":
        raise RuntimeError("Unknown credential storage: %s" % data.get("system"))
    password = dpapi_unprotect(base64.b64decode(data["password"])).decode("utf-8")
    return data.get("username"), password


# ---------------------------------------------------------------- backend login
def _jar_sid(jar):
    for cookie in jar:
        if cookie.name == "sid":
            return cookie.value
    return None


def _fetch(opener, url):
    with opener.open(urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT,
                          "Accept": "text/html,application/xhtml+xml"}), timeout=40) as response:
        return response.read().decode("utf-8", "replace")


def login_context():
    return json.dumps({"mode": "PROD", "fwuid": FWUID, "app": "siteforce:loginApp2",
                       "loaded": {"APPLICATION@markup://siteforce:loginApp2": LOGIN_APP_VERSION},
                       "dn": [], "globals": {}, "uad": True}, separators=(",", ":"))


def backend_login(username, password, start_url=""):
    """Log in with the portal login call. Return (sid, raw_response).

    The login page is a guest page. Its requests use `aura.token=null`.
    """
    page_uri = LOGIN_PAGE + "?language=es"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        BASE + page_uri,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with opener.open(request, timeout=40) as response:
        response.read()

    message = {"actions": [{"id": "1;a",
        "descriptor": "apex://LightningLoginFormController/ACTION$login",
        "callingDescriptor": "markup://c:WP_LoginForm",
        "params": {"username": username, "password": password, "startUrl": start_url}}]}
    body = urllib.parse.urlencode({
        "message": json.dumps(message, separators=(",", ":")),
        "aura.context": login_context(),
        "aura.pageURI": page_uri,
        "aura.token": "null"}).encode()
    request = urllib.request.Request(
        AURA_ENDPOINT + "?r=1&other.LightningLoginForm.login=1",
        data=body, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": BASE, "Referer": BASE + page_uri,
            "User-Agent": USER_AGENT, "Accept": "*/*"})
    with opener.open(request, timeout=40) as response:
        text = response.read().decode("utf-8", "replace")

    sid = _jar_sid(jar)
    if not sid:
        # The login action returns null. The response carries an
        # `aura:clientRedirect` with the frontdoor URL. That URL holds the
        # session as a query parameter. The frontdoor page then points to the
        # login flow, which finishes on the community landing page. Follow the
        # chain to set the session cookie.
        match = re.search(r"https://[^\"]*frontdoor\.jsp[^\"]*", text)
        front = None
        if match:
            front = match.group(0).replace("\\u0026", "&").replace("&amp;", "&")
        if front:
            try:
                body = _fetch(opener, front)
                flow = re.search(r"(?:https://[^\"']+)?(/areaprivada/loginflow/[^\"'\\ ]+)", body)
                if flow:
                    _fetch(opener, BASE + flow.group(1))
            except Exception:
                pass
            sid = _jar_sid(jar)
        if sid:
            try:
                _fetch(opener, BASE + HOME_PAGE)
            except Exception:
                pass
    return sid, text


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
                "cups_id": cups.get("Id"),
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

    def get_maximeter(self, cups_id, visibility_id, start_date, end_date):
        page = "%s?aId=%s&sId=%s" % (MAXPOWER_PAGE, cups_id, visibility_id)
        params = {"mapParams": {"startDate": start_date, "endDate": end_date,
                                "id": cups_id, "sIdentificador": visibility_id}}
        return self.call("maximeter", params, page).get("data", {})


# ---------------------------------------------------------------- parsing
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


def parse_cookies_file(path, domain=None):
    """Read a cookies file. Accepts Netscape cookies.txt or a JSON export.

    The browser extension 'Get cookies.txt LOCALLY' writes the Netscape format.
    When `domain` is given, keep only cookies for that domain. Return a dict of
    name -> value.
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
            if not name:
                continue
            if domain and domain not in (item.get("domain") or "").lower():
                continue
            cookies[name] = item.get("value")
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                if domain and domain not in parts[0].lower():
                    continue
                cookies[parts[5]] = parts[6]
    return cookies


def find_cookies_file():
    """Find the newest cookies file for the portal in the Downloads folders.

    Only files that mention `edistribucion` count. This avoids other cookie
    exports, such as files for other sites.
    """
    home = os.path.expanduser("~")
    best = None
    for folder_name in ("Downloads", "Descargas"):
        folder = os.path.join(home, folder_name)
        if not os.path.isdir(folder):
            continue
        for entry in os.listdir(folder):
            lower = entry.lower()
            if not (lower.endswith(".txt") or lower.endswith(".json")):
                continue
            path = os.path.join(folder, entry)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read().lower()
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if "edistribucion" not in text:
                continue
            score = 1 if "cookie" in lower else 0
            if best is None or (score, mtime) > (best[0], best[1]):
                best = (score, mtime, path)
    return best[2] if best else None


# ---------------------------------------------------------------- CLI helpers
def build_client(args):
    return Client(Session(sid=getattr(args, "sid", None), path=args.session))


def auto_login(args):
    """Log in with the stored credentials when the session is not valid.

    Auto login is enabled when the credentials file exists.
    """
    if not os.path.exists(DEFAULT_CREDENTIALS):
        return None
    username, password = load_credentials(DEFAULT_CREDENTIALS)
    sid, _ = backend_login(username, password)
    if not sid:
        return None
    session = Session(sid=sid, path=args.session)
    session.save()
    print("Stored session expired. Logged in again with the stored credentials.",
          file=sys.stderr)
    return Client(session)


def load_context(args):
    client = build_client(args)
    try:
        account = client.whoami()
    except Exception:
        account = None
        try:
            client = auto_login(args) or client
            account = client.whoami() if client is not None else None
        except Exception:
            account = None
        if account is None:
            raise
    supplies = client.list_supplies(account["visibility_id"])
    return client, account, supplies


def default_contract(account, supplies, contract):
    if contract:
        return contract
    for item in supplies:
        if not item.get("end"):
            return item["contract_id"]
    return supplies[0]["contract_id"]


# ---------------------------------------------------------------- commands
def cmd_save(args):
    session = Session(sid=args.sid, path=args.session)
    if args.text:
        session.cookies.update(extract_cookies_from_text(args.text))
    if args.cookie:
        for pair in args.cookie.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                session.cookies[key] = value
    if not session.sid:
        print("No sid value found. Pass --sid or --text.", file=sys.stderr)
        sys.exit(1)
    session.save()
    print("Session saved to", args.session)
    print("cookies:", ", ".join(session.cookies.keys()))
    try:
        account = Client(session).whoami()
        print("Login OK. User:", account["name"])
    except Exception as exc:
        print("Session saved, but the check failed:", exc, file=sys.stderr)
        sys.exit(1)


def cmd_import_cookies(args):
    path = args.file or find_cookies_file()
    if not path:
        print("No cookies file given, and none found in Downloads.", file=sys.stderr)
        sys.exit(1)
    if not args.file:
        print("Using", path)
    cookies = parse_cookies_file(path, domain="edistribucion")
    if not cookies.get("sid"):
        print("No sid found in", path, file=sys.stderr)
        sys.exit(1)
    session = Session(path=args.session)
    session.cookies.update(cookies)
    session.save()
    print("Imported %d cookies into %s" % (len(cookies), args.session))
    try:
        account = Client(session).whoami()
        print("Login OK. User:", account["name"])
    except Exception as exc:
        print("Session saved, but the check failed:", exc, file=sys.stderr)
        sys.exit(1)


COOKIE_NAMES = ("sid", "oid", "sid_Client", "inst", "clientSrc")


def extract_cookies_from_text(text):
    """Find cookie pairs in a Cookie header or a cURL line."""
    found = {}
    for name in COOKIE_NAMES:
        match = re.search(r"(?:^|[;\s'\"]|:)%s=([^;'\"\s]+)" % re.escape(name), text)
        if match:
            found[name] = match.group(1)
    return found


def cmd_login_backend(args):
    username = args.user
    password = args.password
    if not (username and password) and os.path.exists(args.credentials):
        username, password = load_credentials(args.credentials)
    if not username:
        username = input("NIF, passport or NIE: ").strip()
    if not password:
        password = getpass.getpass("Password: ")
    if not (username and password):
        print("Need a user and a password.", file=sys.stderr)
        sys.exit(1)

    print("Logging in by backend...")
    try:
        sid, text = backend_login(username, password)
    except Exception as exc:
        print("Login request failed:", exc, file=sys.stderr)
        sys.exit(1)
    if not sid:
        print("The portal did not return a session. Raw response:", file=sys.stderr)
        print(text[:600], file=sys.stderr)
        sys.exit(1)

    session = Session(sid=sid, path=args.session)
    session.save()
    print("Session saved to", args.session)
    if args.save:
        path = save_credentials(username, password, args.credentials)
        print("Credentials saved (encrypted with Windows DPAPI) to", path)
    try:
        account = Client(session).whoami()
        print("Login OK. User:", account["name"])
    except Exception as exc:
        print("Session saved, but the check failed:", exc, file=sys.stderr)
        sys.exit(1)


def cmd_cups(args):
    _, _, supplies = load_context(args)
    print(json.dumps(supplies, ensure_ascii=False, indent=2))


CHUNK_DAYS = 35


def _group_key(group, day, hour):
    if group == "hour":
        return "%02d" % int(hour[:2])
    if group == "day":
        return day.isoformat()
    if group == "month":
        return "%04d-%02d" % (day.year, day.month)
    return "%04d" % day.year


def _compress_dates(days):
    """Turn a sorted list of dates into short ranges."""
    days = sorted(days)
    parts = []
    start = prev = None
    for day in days:
        if start is None:
            start = prev = day
        elif (day - prev).days == 1:
            prev = day
        else:
            parts.append((start, prev))
            start = prev = day
    if start is not None:
        parts.append((start, prev))
    out = []
    for first, last in parts:
        out.append(first.isoformat() if first == last else "%s..%s" % (first, last))
    return out


def cmd_consume(args):
    client, account, supplies = load_context(args)
    contracts = supplies
    if args.cont:
        contracts = [item for item in supplies if item["contract_id"] == args.cont]
        if not contracts:
            print("Unknown contract:", args.cont, file=sys.stderr)
            sys.exit(1)

    ranges = []
    for item in contracts:
        info = client.get_info(item["contract_id"], account["visibility_id"])
        dmin, dmax = info.get("minDate"), info.get("maxDate")
        if not dmin or not dmax:
            continue
        if args.date_from and args.date_from > dmin:
            dmin = args.date_from
        if args.date_to and args.date_to < dmax:
            dmax = args.date_to
        if dmin <= dmax:
            ranges.append((item["contract_id"], dmin, dmax))

    seen = set()
    buckets = {}
    periods_real = {"P1": 0.0, "P2": 0.0, "P3": 0.0}
    total_real = total_estimated = 0.0
    real_hours = estimated_hours = 0
    estimated_days = set()
    first = last = None

    for cid, dmin, dmax in ranges:
        cur = datetime.strptime(dmin, "%Y-%m-%d").date()
        end = datetime.strptime(dmax, "%Y-%m-%d").date()
        while cur <= end:
            chunk_end = min(cur + timedelta(days=CHUNK_DAYS - 1), end)
            data = client.get_curve(cid, cur.isoformat(), chunk_end.isoformat(),
                                    account["visibility_id"])
            for row in parse_curve(data):
                key = (row["date"], row["hour"])
                if key in seen:
                    continue
                seen.add(key)
                kwh = row["kwh"] or 0.0
                day = datetime.strptime(row["date"], "%d/%m/%Y").date()
                bucket = buckets.setdefault(_group_key(args.group, day, row["hour"]),
                                            {"real_kwh": 0.0, "estimated_kwh": 0.0,
                                             "real_hours": 0, "estimated_hours": 0})
                if row["method"] == "measured":
                    bucket["real_kwh"] += kwh
                    bucket["real_hours"] += 1
                    total_real += kwh
                    real_hours += 1
                    if row["period"] in periods_real:
                        periods_real[row["period"]] += kwh
                else:
                    bucket["estimated_kwh"] += kwh
                    bucket["estimated_hours"] += 1
                    total_estimated += kwh
                    estimated_hours += 1
                    estimated_days.add(day)
                if first is None or day < first:
                    first = day
                if last is None or day > last:
                    last = day
            cur = chunk_end + timedelta(days=1)

    groups = []
    for key in sorted(buckets):
        value = buckets[key]
        groups.append({
            "key": key,
            "real_kwh": round(value["real_kwh"], 3),
            "estimated_kwh": round(value["estimated_kwh"], 3),
            "real_hours": value["real_hours"],
            "estimated_hours": value["estimated_hours"],
        })
    result = {
        "from": first.isoformat() if first else None,
        "to": last.isoformat() if last else None,
        "group": args.group,
        "real_kwh": round(total_real, 3),
        "estimated_kwh": round(total_estimated, 3),
        "real_hours": real_hours,
        "estimated_hours": estimated_hours,
        "periods_real_kwh": {k: round(v, 3) for k, v in periods_real.items()},
        "estimated_days": _compress_dates(estimated_days),
        "groups": groups,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("Period:", result["from"], "->", result["to"], "| group:", args.group)
    print("Real:", result["real_kwh"], "kWh (%d h)" % real_hours,
          "| Estimated:", result["estimated_kwh"], "kWh (%d h)" % estimated_hours)
    print("Real periods:", result["periods_real_kwh"])
    if result["estimated_days"]:
        print("Estimated dates:", ", ".join(result["estimated_days"]))
    else:
        print("Estimated dates: none")
    print("By %s (real kWh | estimated kWh):" % args.group)
    for group in groups:
        print("  %-12s %10.3f | %10.3f" % (
            group["key"], group["real_kwh"], group["estimated_kwh"]))


def cmd_maxpower(args):
    client, account, supplies = load_context(args)
    contract = default_contract(account, supplies, args.cont)
    supply = next((item for item in supplies if item["contract_id"] == contract), supplies[0])
    cups_id = supply.get("cups_id")
    if not cups_id:
        print("No CUPS id for the contract.", file=sys.stderr)
        sys.exit(1)

    if args.date_to:
        year, month = [int(part) for part in args.date_to.split("-")[:2]]
    else:
        today = date.today()
        year, month = today.year, today.month
    end = "%d/%d" % (month, year)
    if args.date_from:
        y0, m0 = [int(part) for part in args.date_from.split("-")[:2]]
    else:
        total = year * 12 + (month - 1) - 11
        y0, m0 = total // 12, total % 12 + 1
    start = "%d/%d" % (m0, y0)

    data = client.get_maximeter(cups_id, account["visibility_id"], start, end)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print("CUPS:", data.get("cups"), "| contractId:", contract)
    print("Period:", start, "->", end)
    print("Contracted power:", data.get("requestedPower"), "kW")
    print("Maximum:", data.get("maxValue"))
    print("Monthly maxima:")
    for point in data.get("lstData", []):
        if not point.get("valid"):
            print("  %s  no data" % point.get("date"))
            continue
        periods = point.get("periodData") or {}
        period_txt = " ".join("P%s=%s" % (key[1:], value.get("fmtVal"))
                              for key, value in periods.items() if value.get("val"))
        print("  %s  %s kW  %s" % (point.get("date"), point.get("value"), period_txt))


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
    save.add_argument("--text", help="a Cookie header or a cURL line that holds the session")
    save.set_defaults(func=cmd_save)

    imp = sub.add_parser("import-cookies", parents=[common],
                         help="import cookies from a cookies.txt (Netscape) or JSON file")
    imp.add_argument("file", nargs="?", help="path to cookies.txt or JSON export (default: newest in Downloads)")
    imp.set_defaults(func=cmd_import_cookies)

    backend = sub.add_parser("login-backend", parents=[common],
                             help="log in with user and password, no browser")
    backend.add_argument("--user", help="NIF, passport or NIE")
    backend.add_argument("--password", help="the password (or you are asked for it)")
    backend.add_argument("--save", action="store_true",
                         help="store the credentials encrypted with Windows DPAPI")
    backend.add_argument("--credentials", default=DEFAULT_CREDENTIALS,
                         help="path to the credentials file")
    backend.set_defaults(func=cmd_login_backend)

    sub.add_parser("cups", parents=[common], help="list supplies").set_defaults(func=cmd_cups)

    consume = sub.add_parser("consume", parents=[common],
                             help="aggregate consumption by hour, day, month or year")
    consume.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    consume.add_argument("--to", dest="date_to", help="YYYY-MM-DD")
    consume.add_argument("--group", choices=["hour", "day", "month", "year"],
                         default="day", help="group by hour of day, day, month or year")
    consume.add_argument("--cont")
    consume.add_argument("--json", action="store_true")
    consume.set_defaults(func=cmd_consume)

    mp = sub.add_parser("maxpower", parents=[common],
                        help="maximum demanded power per month")
    mp.add_argument("--from", dest="date_from", help="YYYY-MM")
    mp.add_argument("--to", dest="date_to", help="YYYY-MM")
    mp.add_argument("--cont")
    mp.add_argument("--json", action="store_true")
    mp.set_defaults(func=cmd_maxpower)
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
