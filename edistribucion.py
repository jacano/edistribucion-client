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
  - The full hourly history comes as one zip from `WP_Measure_v3_CTRL.createZip`
    (the "massive download" page). This needs far fewer calls than one call per
    month of data. The period (P1 / P2 / P3) is worked out from the date and the
    hour with the 2.0TD calendar.

Session: session.json (or the EDIST_SID environment variable). Commands:
  python edistribucion.py login-backend [--save] # log in with user and password
  python edistribucion.py import-cookies [FILE]  # import a cookies.txt
  python edistribucion.py save --sid "<value>"   # save a value by hand
  python edistribucion.py report [--json]        # full report for every CUPS
"""
import argparse
import base64
import csv
import ctypes
import getpass
import http.cookiejar
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from ctypes import wintypes
from datetime import date, datetime

BASE = "https://zonaprivada.edistribucion.com"
SITE = BASE + "/areaprivada"
AURA_ENDPOINT = SITE + "/s/sfsites/aura"
HOME_PAGE = "/areaprivada/s/"
LOGIN_PAGE = "/areaprivada/s/login/"
MEASURELIST_PAGE = "/areaprivada/s/wp-measurelist-v4"
DETAIL_PAGE = "/areaprivada/s/wp-measure-detail-v4"
DOWNLOAD_PAGE = "/areaprivada/s/wp-massivemeasuredownload-v3"
MAXPOWER_PAGE = "/areaprivada/s/wp-maximeterhistogramdetail"
ATR_PAGE = "/areaprivada/s/wp-atrcontractdetail"

DIR = os.path.dirname(os.path.abspath(__file__))


def state_path(name):
    """Return the path of a local state file (the session, the credentials).

    Use a file next to the script or in the current folder when it exists, so
    the source layout keeps its files. Else use the user config folder, so an
    installed tool can write the files outside its package.
    """
    for folder in (DIR, os.getcwd()):
        beside = os.path.join(folder, name)
        if os.path.exists(beside):
            return beside
    base = (os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
            or os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(base, "edistribucion", name)


DEFAULT_SESSION = state_path("session.json")
DEFAULT_CREDENTIALS = state_path("credentials.json")
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
    "measure_list": ("WP_Measure_v3_CTRL.getListCups",
                     "apex://WP_Measure_v3_CTRL/ACTION$getListCups",
                     "markup://c:WP_Massive_Measure_Download_v3"),
    "create_zip": ("WP_Measure_v3_CTRL.createZip",
                   "apex://WP_Measure_v3_CTRL/ACTION$createZip",
                   "markup://c:WP_Massive_Measure_Filter2_v3"),
    "get_files": ("WP_Download_Transfer_CTRL.getFiles",
                  "apex://WP_Download_Transfer_CTRL/ACTION$getFiles",
                  "markup://c:WP_Download_Transfer_Table"),
    "delete_file": ("WP_Download_Transfer_CTRL.deleteFile",
                    "apex://WP_Download_Transfer_CTRL/ACTION$deleteFile",
                    "markup://c:WP_Download_Transfer_Table"),
    "maximeter": ("WP_MaximeterHistogram_CTRL.getHistogramPoints",
                  "apex://WP_MaximeterHistogram_CTRL/ACTION$getHistogramPoints",
                  "markup://c:WP_MaximeterHistogramDetail"),
    "atr_detail": ("WP_ContractATRDetail_CTRL.getATRDetail",
                   "apex://WP_ContractATRDetail_CTRL/ACTION$getATRDetail",
                   "markup://c:WP_SuppliesATRDetailForm"),
}

# National holidays with a fixed date. All their hours are off-peak (P3).
# The portal uses the same set, so the dates with no fixed date (Easter) are not
# off-peak.
FIXED_HOLIDAYS = {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}

# This tool only knows the 2.0TD tariff (three periods: P1, P2, P3).
SUPPORTED_TARIFF = "2.0"


def log(message):
    """Write a progress line to stderr, so stdout stays clean."""
    print(message, file=sys.stderr)


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
        log("  token: GET %s" % page_uri)
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
        log("  call: %s" % route)
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

    def list_measure_cups(self, visibility_id):
        return self.call("measure_list", {"sIdentificador": visibility_id}, DOWNLOAD_PAGE)

    def create_zip(self, visibility_id, contract_ids, contracts, start_date, end_date):
        params = {"roleId": visibility_id, "lstCupsIds": contract_ids, "data": contracts,
                  "startDate": start_date, "endDate": end_date, "downloadType": 1}
        return self.call("create_zip", params, DOWNLOAD_PAGE)

    def get_files(self, visibility_id):
        params = {"roleId": visibility_id, "type": ["01", "50", "51"]}
        return self.call("get_files", params, DOWNLOAD_PAGE).get("data", {})

    def delete_file(self, transfer_id):
        return self.call("delete_file", {"transferId": transfer_id}, DOWNLOAD_PAGE)

    def download_file(self, fileid):
        """Return the raw bytes of a file that get_files lists."""
        url = BASE + "/areaprivada/sfc/servlet.shepherd/version/download/" + fileid
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if self.session.sid:
            headers["Cookie"] = self.session.cookie_header()
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.read()

    def get_maximeter(self, cups_id, visibility_id, start_date, end_date):
        page = "%s?aId=%s&sId=%s" % (MAXPOWER_PAGE, cups_id, visibility_id)
        params = {"mapParams": {"startDate": start_date, "endDate": end_date,
                                "id": cups_id, "sIdentificador": visibility_id}}
        return self.call("maximeter", params, page).get("data", {})

    def get_contracted_power(self, contract_id, visibility_id):
        """Return the contracted power per period, for example {"P1": 4.0, "P2": 4.0}."""
        page = "%s?atrid=%s&vis=%s" % (ATR_PAGE, contract_id, visibility_id)
        params = {"atrId": contract_id, "visSelected": visibility_id}
        rows = self.call("atr_detail", params, page).get("data", [])
        power = {}
        for row in rows:
            title = row.get("title") or ""
            value = row.get("value")
            if title.startswith("Potencia contratada") and value:
                number = title.replace("Potencia contratada", "").strip().split(" ")[0]
                try:
                    power["P" + number] = float(str(value).replace(",", "."))
                except ValueError:
                    pass
        return power


# ---------------------------------------------------------------- parsing
def tariff_period(day, hour):
    """Return P1, P2 or P3 for a date and a clock hour, on the 2.0TD tariff."""
    if day.weekday() >= 5 or (day.month, day.day) in FIXED_HOLIDAYS:
        return "P3"
    if 10 <= hour < 14 or 18 <= hour < 22:
        return "P1"
    if 8 <= hour < 10 or 14 <= hour < 18 or 22 <= hour < 24:
        return "P2"
    return "P3"


def zip_hours(payload):
    """Yield (day, hour, kwh, real) from the hourly CSV files in the zip.

    The Hora column counts the hours of the day, so a day of the change of the
    hour has 23 or 25 rows. The change is always in a Sunday (all P3), so the
    exact hour does not change the period.
    """
    days = {}
    order = []
    names = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            upper = name.upper()
            if upper.endswith("_HORARIO.CSV") and not upper.endswith("_CCH_CONS.CSV"):
                names.append(name)
        for name in sorted(names):
            with archive.open(name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                reader = csv.reader(text, delimiter=";")
                header = next(reader, None)
                cols = {value.strip().upper(): index for index, value in enumerate(header or [])}
                i_date = cols.get("FECHA")
                i_kwh = cols.get("AE_KWH")
                i_flag = cols.get("REAL/ESTIMADO")
                if i_date is None or i_kwh is None or i_flag is None:
                    continue
                width = max(i_date, i_kwh, i_flag)
                for row in reader:
                    if len(row) <= width:
                        continue
                    day = datetime.strptime(row[i_date], "%d/%m/%Y").date()
                    value = row[i_kwh].replace(",", ".").strip()
                    kwh = float(value) if value else 0.0
                    if day not in days:
                        days[day] = []
                        order.append(day)
                    days[day].append((kwh, row[i_flag].strip().upper().startswith("R")))
    for day in order:
        rows = days[day]
        count = len(rows)
        for index, (kwh, real) in enumerate(rows, start=1):
            if count == 23 and index >= 3:
                hour = index
            elif count == 25 and index >= 4:
                hour = index - 2
            else:
                hour = index - 1
            yield day, min(hour, 23), kwh, real


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
    log("Checking the session...")
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
    log("Reading the list of supplies...")
    supplies = client.list_supplies(account["visibility_id"])
    return client, account, supplies


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


def measure_tariff(listing, contracts):
    """Return the tariff name of a contract group, from the measure list."""
    wanted = {item["contract_id"] for item in contracts}
    for row in listing.get("lstCups") or []:
        if row.get("Id") in wanted and row.get("rate"):
            return row["rate"]
    return None


def _download_measure_zip(client, account, contracts, listing):
    """Ask the portal for one zip with all the hourly curves of a CUPS.

    The portal makes the zip in the background. This waits until the file
    appears in the download list, then returns its bytes.
    """
    visibility = account["visibility_id"]
    wanted = {item["contract_id"] for item in contracts}
    contract_ids = [value for value in (listing.get("lstIds") or []) if value in wanted]
    records = [row for row in (listing.get("lstCups") or []) if row.get("Id") in wanted]
    if not contract_ids:
        return None
    starts = [item["start"] for item in contracts if item.get("start")]
    ends = [item.get("end") or date.today().isoformat() for item in contracts]
    start = datetime.strptime(min(starts), "%Y-%m-%d").strftime("%d/%m/%Y")
    end = datetime.strptime(max(ends), "%Y-%m-%d").strftime("%d/%m/%Y")

    known = {item.get("fileid") for item in (client.get_files(visibility).get("lstFiles") or [])}
    log("Requesting the zip (%s -> %s). The portal makes it in the background." % (start, end))
    client.create_zip(visibility, contract_ids, records, start, end)
    for attempt in range(60):
        time.sleep(3)
        log("  Waiting for the zip... %d s" % ((attempt + 1) * 3))
        files = client.get_files(visibility).get("lstFiles") or []
        fresh = [item for item in files if item.get("fileid") not in known]
        if fresh:
            title = fresh[0].get("Title")
            fileid = fresh[0]["fileid"]
            log("Zip ready: %s. Downloading..." % title)
            payload = client.download_file(fileid)
            log("Downloaded %.1f KiB. Deleting the zip from the portal." % (len(payload) / 1024.0))
            try:
                client.delete_file(fresh[0]["Id"])
                log("Zip deleted.")
            except Exception as exc:
                log("Could not delete the zip: %s" % exc)
            return payload
    raise RuntimeError("The portal did not make the zip in time.")


def collect_consumption(client, account, contracts, listing):
    """Read the full history from the zip and return the aggregates."""
    groups = {"year": {}, "month": {}, "hour": {}}
    periods_real = {"P1": 0.0, "P2": 0.0, "P3": 0.0}
    periods_estimated = {"P1": 0.0, "P2": 0.0, "P3": 0.0}
    periods_year = {}
    total_real = total_estimated = 0.0
    real_hours = estimated_hours = 0
    estimated_days = set()
    year_peak = {}
    month_peak = {}
    first = last = None
    hours = {}

    def bucket(group, key):
        return groups[group].setdefault(key, {"real_kwh": 0.0, "estimated_kwh": 0.0,
                                              "real_hours": 0, "estimated_hours": 0})

    payload = _download_measure_zip(client, account, contracts, listing)
    if payload:
        for day, hour, kwh, real in zip_hours(payload):
            key = (day, hour)
            old = hours.get(key)
            if old is None or (real and not old[1]):
                hours[key] = (kwh, real)
    log("Read %d hours from the zip." % len(hours))

    for (day, hour), (kwh, real) in sorted(hours.items()):
        hour_key = "%02d" % hour
        period = tariff_period(day, hour)
        for group, gkey in (("year", "%04d" % day.year),
                            ("month", "%04d-%02d" % (day.year, day.month)),
                            ("hour", hour_key)):
            entry = bucket(group, gkey)
            if real:
                entry["real_kwh"] += kwh
                entry["real_hours"] += 1
            else:
                entry["estimated_kwh"] += kwh
                entry["estimated_hours"] += 1
        year_slot = periods_year.setdefault(day.year, {name: {"real": 0.0, "estimated": 0.0}
                                                       for name in ("P1", "P2", "P3")})
        year_slot[period]["real" if real else "estimated"] += kwh
        target = periods_real if real else periods_estimated
        if period in target:
            target[period] += kwh
        label = "%02d - %02d h" % (hour, hour + 1)
        if real:
            total_real += kwh
            real_hours += 1
            if day.year not in year_peak or kwh > year_peak[day.year][0]:
                year_peak[day.year] = (kwh, day.strftime("%d/%m/%Y"), label)
            month_key = "%04d-%02d" % (day.year, day.month)
            if month_key not in month_peak or kwh > month_peak[month_key][0]:
                month_peak[month_key] = (kwh, day.strftime("%d/%m/%Y"), label)
        else:
            total_estimated += kwh
            estimated_hours += 1
            estimated_days.add(day)
        if first is None or day < first:
            first = day
        if last is None or day > last:
            last = day

    return {
        "groups": groups,
        "periods_real_kwh": periods_real,
        "periods_estimated_kwh": periods_estimated,
        "periods_year": periods_year,
        "real_kwh": total_real,
        "estimated_kwh": total_estimated,
        "real_hours": real_hours,
        "estimated_hours": estimated_hours,
        "estimated_days": estimated_days,
        "year_peak": year_peak,
        "month_peak": month_peak,
        "from": first,
        "to": last,
    }


def _groups_list(group_dict):
    return [{
        "key": key,
        "real_kwh": round(value["real_kwh"], 3),
        "estimated_kwh": round(value["estimated_kwh"], 3),
        "real_hours": value["real_hours"],
        "estimated_hours": value["estimated_hours"],
    } for key, value in sorted(group_dict.items())]


def _max_demand(client, account, cups_id, year_from, year_to):
    monthly = {}
    for year in range(year_from, year_to + 1):
        data = client.get_maximeter(cups_id, account["visibility_id"], "1/%d" % year, "12/%d" % year)
        for point in data.get("lstData", []):
            if point.get("valid"):
                monthly[point["date"]] = point["value"]
    return monthly


def hours_days(hours):
    """Return the hours and the same time in days, for example 15911 hours (663 days)."""
    return "%d hours (%d days)" % (hours, round(hours / 24.0))


def _print_report(result):
    print("REPORT")
    print("CUPS:", result["cups"])
    print("Tariff:", result["tariff"])
    print("Contracted power:", result["contracted_power_kw"], "kW")
    print("Period:", result["from"], "->", result["to"])
    print()
    print("CONSUMPTION")
    print("  Total real:", result["real_kwh"], "kWh in", hours_days(result["real_hours"]))
    print("  Total estimated:", result["estimated_kwh"], "kWh in",
          hours_days(result["estimated_hours"]))
    print("  Periods real:", result["periods_real_kwh"])
    print("  Periods estimated:", result["periods_estimated_kwh"])
    print("  By year (real | estimated kWh, real | estimated hours):")
    for group in result["consumption_by_year"]:
        print("    %s  %10.3f | %10.3f  | %6d h (%3d d) | %6d h (%3d d)" % (
            group["key"], group["real_kwh"], group["estimated_kwh"],
            group["real_hours"], round(group["real_hours"] / 24.0),
            group["estimated_hours"], round(group["estimated_hours"] / 24.0)))
        for name, slot in result["periods_by_year"].get(group["key"], {}).items():
            print("      %s  %8.3f | %8.3f" % (name, slot["real"], slot["estimated"]))
    print("  By month (real | estimated kWh):")
    for group in result["consumption_by_month"]:
        print("    %s  %10.3f | %10.3f" % (
            group["key"], group["real_kwh"], group["estimated_kwh"]))
    print("  By hour of day (real | estimated kWh):")
    for group in result["consumption_by_hour"]:
        print("    %s  %10.3f | %10.3f" % (
            group["key"], group["real_kwh"], group["estimated_kwh"]))
    print()
    print("MAX HOURLY CONSUMPTION")
    for year, value in result["max_hourly_by_year"].items():
        print("  %s  %.3f kWh  (%s %s)" % (year, value["kwh"], value["date"], value["hour"]))
    print()
    print("MAX DEMANDED POWER (monthly, from the portal)")
    for year, value in result["max_demand_by_year"].items():
        print("  %s  %.3f kW  (%s)" % (year, value["kw"], value["date"]))
    print()
    if result["has_estimated"]:
        print("WARNING: there are estimated consumptions.")
        print("  Estimated:", result["estimated_kwh"], "kWh in",
              hours_days(result["estimated_hours"]))
        print("  Estimated dates:", ", ".join(result["estimated_days"]))
    else:
        print("No estimated consumptions. All data is real.")


def cmd_report(args):
    client, account, supplies = load_context(args)
    visibility = account["visibility_id"]
    names = sorted({item["cups"] for item in supplies if item["cups"]})
    reports = []
    printed = 0
    for cups in names:
        group = [item for item in supplies if item["cups"] == cups]
        current = next((item for item in group if not item.get("end")), group[-1])
        log("CUPS %s" % cups)
        log("Reading the tariff...")
        listing = client.list_measure_cups(visibility).get("data") or {}
        tariff = measure_tariff(listing, group)
        if tariff and not tariff.startswith(SUPPORTED_TARIFF):
            raise RuntimeError("Unsupported tariff: %s. This tool supports 2.0TD only."
                               % tariff)
        data = collect_consumption(client, account, group, listing)
        if not data["from"]:
            log("  No data for this CUPS.")
            continue
        log("Reading the contracted power...")
        contracted = client.get_contracted_power(current["contract_id"], visibility)
        log("Reading the maximum demanded power (%d-%d)..."
            % (data["from"].year, data["to"].year))
        monthly_power = _max_demand(client, account, current["cups_id"],
                                    data["from"].year, data["to"].year)
        year_power = {}
        for date_str, value in monthly_power.items():
            year = int(date_str.split("-")[2])
            if year not in year_power or value > year_power[year][0]:
                year_power[year] = (value, date_str)
        result = {
            "cups": cups,
            "tariff": tariff,
            "contracted_power_kw": contracted,
            "from": data["from"].isoformat(),
            "to": data["to"].isoformat(),
            "real_kwh": round(data["real_kwh"], 3),
            "estimated_kwh": round(data["estimated_kwh"], 3),
            "real_hours": data["real_hours"],
            "estimated_hours": data["estimated_hours"],
            "periods_real_kwh": {k: round(v, 3) for k, v in data["periods_real_kwh"].items()},
            "periods_estimated_kwh": {k: round(v, 3)
                                      for k, v in data["periods_estimated_kwh"].items()},
            "periods_by_year": {str(year): {name: {"real": round(slot["real"], 3),
                                                   "estimated": round(slot["estimated"], 3)}
                                            for name, slot in sorted(periods.items())}
                                for year, periods in sorted(data["periods_year"].items())},
            "has_estimated": bool(data["estimated_days"]),
            "estimated_days": _compress_dates(data["estimated_days"]),
            "consumption_by_year": _groups_list(data["groups"]["year"]),
            "consumption_by_month": _groups_list(data["groups"]["month"]),
            "consumption_by_hour": _groups_list(data["groups"]["hour"]),
            "max_hourly_by_year": {str(y): {"kwh": round(v[0], 3), "date": v[1], "hour": v[2]}
                                   for y, v in sorted(data["year_peak"].items())},
            "max_hourly_by_month": {k: {"kwh": round(v[0], 3), "date": v[1], "hour": v[2]}
                                    for k, v in sorted(data["month_peak"].items())},
            "max_demand_by_year": {str(y): {"kw": v[0], "date": v[1]}
                                   for y, v in sorted(year_power.items())},
            "max_demand_by_month": monthly_power,
        }
        reports.append(result)
        if not args.json:
            if printed > 0:
                print()
                print("=" * 60)
                print()
            _print_report(result)
            printed += 1
    if not reports:
        print("No data.", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))


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

    report = sub.add_parser("report", parents=[common],
                            help="full report for every CUPS (all data available)")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["report"]
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
