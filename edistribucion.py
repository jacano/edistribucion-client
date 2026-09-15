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
    (the "massive download" page). The per-range API
    `WP_Measure_v3_CTRL.getChartPointsByRange` is not used: it covers only about
    35 days per call, so the full history needs many calls and does not scale.
    The period (P1 / P2 / P3) is worked out from the date and the hour with the
    2.0TD calendar.

Session: session.json (or the EDIST_SID environment variable). Commands:
  python edistribucion.py login [--save]        # log in with user and password
  python edistribucion.py import-cookies [FILE] # import a cookies.txt
  python edistribucion.py set-session --sid "X" # store a session by hand
  python edistribucion.py report [--json]       # full report for every CUPS
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
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from ctypes import wintypes
from datetime import date, datetime, timedelta

BASE = "https://zonaprivada.edistribucion.com"
SITE = BASE + "/areaprivada"
AURA_ENDPOINT = SITE + "/s/sfsites/aura"
HOME_PAGE = "/areaprivada/s/"
LOGIN_PAGE = "/areaprivada/s/login/"
MEASURELIST_PAGE = "/areaprivada/s/wp-measurelist-v4"
DETAIL_PAGE = "/areaprivada/s/wp-measure-detail-v4"
DOWNLOAD_PAGE = "/areaprivada/s/wp-massivemeasuredownload-v3"
NOTIFICATIONS_PAGE = "/areaprivada/s/wp-notificationslist"
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
    "notifications_list": ("WP_NotificationsList_CTRL.getListNotifications",
                           "apex://WP_NotificationsList_CTRL/ACTION$getListNotifications",
                           "markup://c:WP_NotificationsListForm"),
    "delete_notifications": ("WP_NotificationsList_CTRL.markAsDeleted",
                             "apex://WP_NotificationsList_CTRL/ACTION$markAsDeleted",
                             "markup://c:WP_NotificationsListForm"),
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

# HTTP and download settings.
HTTP_TIMEOUT = 40
DOWNLOAD_TIMEOUT = 90
DOWNLOAD_TYPE = 1                    # 1 = hourly curves
FILE_TYPES = ["01", "50", "51"]      # the portal file types to list
ZIP_WAIT_SECONDS = 3                 # seconds between two checks
ZIP_WAIT_LIMIT = 180                 # seconds to wait for the zip


_QUIET = False
_VERBOSE = False


def log(message):
    """Write a progress line to stderr, so stdout stays clean."""
    if not _QUIET:
        print(message, file=sys.stderr)


def debug(message):
    """Write a detail line, only with --verbose."""
    if _VERBOSE and not _QUIET:
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
            except (OSError, json.JSONDecodeError):
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


CREDENTIAL_SERVICE = "edistribucion-client"


def credential_backend():
    """Return the credential store of this system, or None.

    Windows uses the Data Protection API (DPAPI). macOS uses the Keychain via
    the `security` tool. Linux uses libsecret via the `secret-tool` tool.
    """
    if sys.platform == "win32":
        return "dpapi"
    if sys.platform == "darwin":
        return "keychain" if shutil.which("security") else None
    return "secret-tool" if shutil.which("secret-tool") else None


def _keychain_store(username, password):
    subprocess.run(["security", "add-generic-password", "-a", username, "-s",
                    CREDENTIAL_SERVICE, "-w", password, "-U"], check=True)


def _keychain_load(username):
    result = subprocess.run(["security", "find-generic-password", "-a", username,
                             "-s", CREDENTIAL_SERVICE, "-w"],
                            check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _secret_tool_store(username, password):
    subprocess.run(["secret-tool", "store", "--label", CREDENTIAL_SERVICE,
                    "service", CREDENTIAL_SERVICE, "username", username],
                   input=password, text=True, check=True)


def _secret_tool_load(username):
    result = subprocess.run(["secret-tool", "lookup", "service", CREDENTIAL_SERVICE,
                             "username", username], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def save_credentials(username, password, path=DEFAULT_CREDENTIALS):
    system = credential_backend()
    if system is None:
        raise RuntimeError("--save needs a credential store. On Linux install "
                           "libsecret-tools (the secret-tool tool).")
    record = {"system": system, "username": username}
    if system == "dpapi":
        record["password"] = base64.b64encode(
            dpapi_protect(password.encode("utf-8"))).decode("ascii")
    elif system == "keychain":
        _keychain_store(username, password)
    else:
        _secret_tool_store(username, password)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    return path


def load_credentials(path=DEFAULT_CREDENTIALS):
    data = json.load(open(path, encoding="utf-8"))
    system = data.get("system")
    username = data.get("username")
    if system == "dpapi":
        password = dpapi_unprotect(base64.b64decode(data["password"])).decode("utf-8")
    elif system == "keychain":
        password = _keychain_load(username)
    elif system == "secret-tool":
        password = _secret_tool_load(username)
    else:
        raise RuntimeError("Unknown credential storage: %s" % system)
    return username, password


# ---------------------------------------------------------------- backend login
def _jar_sid(jar):
    for cookie in jar:
        if cookie.name == "sid":
            return cookie.value
    return None


def _fetch(opener, url):
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT,
                      "Accept": "text/html,application/xhtml+xml"})
    with opener.open(request, timeout=HTTP_TIMEOUT) as response:
        return response.read().decode("utf-8", "replace")


def login_context():
    return json.dumps({"mode": "PROD", "fwuid": FWUID, "app": "siteforce:loginApp2",
                       "loaded": {"APPLICATION@markup://siteforce:loginApp2": LOGIN_APP_VERSION},
                       "dn": [], "globals": {}, "uad": True}, separators=(",", ":"))


def portal_login(username, password, start_url=""):
    """Log in with the portal login call. Return (sid, raw_response).

    The login page is a guest page. Its requests use `aura.token=null`.
    """
    page_uri = LOGIN_PAGE + "?language=es"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        BASE + page_uri,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with opener.open(request, timeout=HTTP_TIMEOUT) as response:
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
    with opener.open(request, timeout=HTTP_TIMEOUT) as response:
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
            except (urllib.error.URLError, OSError):
                pass
            sid = _jar_sid(jar)
        if sid:
            try:
                _fetch(opener, BASE + HOME_PAGE)
            except (urllib.error.URLError, OSError):
                pass
    return sid, text


class Client:
    def __init__(self, session):
        self.session = session
        self._tokens = {}
        self.fwuid = FWUID
        self.app_version = APP_VERSION

    # --- low level HTTP ---
    def _request(self, method, url, data=None, extra_headers=None):
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if self.session.sid:
            headers["Cookie"] = self.session.cookie_header()
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                return response.status, response.headers, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read().decode("utf-8", "replace")

    def _read_context(self, text):
        """Refresh fwuid and app version from an Aura response context."""
        try:
            context = json.loads(text).get("context") or {}
        except json.JSONDecodeError:
            return
        if context.get("fwuid"):
            self.fwuid = context["fwuid"]
        for key, value in (context.get("loaded") or {}).items():
            if key.startswith("APPLICATION@markup://siteforce:communityApp"):
                self.app_version = value

    # --- anti-CSRF token delivered via Set-Cookie ---
    def token(self, page_uri, force=False):
        if not force and page_uri in self._tokens:
            return self._tokens[page_uri]
        debug("  token: GET %s" % page_uri)
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
        loaded = {"APPLICATION@markup://siteforce:communityApp": self.app_version}
        context = json.dumps(
            {"mode": "PROD", "fwuid": self.fwuid, "app": "siteforce:communityApp",
             "loaded": loaded, "dn": [], "globals": {}, "uad": True},
            separators=(",", ":"))
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
        except json.JSONDecodeError:
            raise RuntimeError("Non-JSON response: " + text[:200]) from None
        self._read_context(text)
        result = (payload.get("actions") or [{}])[0]
        if result.get("state") != "SUCCESS":
            raise RuntimeError(
                "Aura error (%s): %s" % (action, result.get("error") or result.get("state")))
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
        params = {"contId": contract_id, "visId": visibility_id}
        return self.call("get_info", params, page).get("data", {})

    def list_measure_cups(self, visibility_id):
        return self.call("measure_list", {"sIdentificador": visibility_id}, DOWNLOAD_PAGE)

    def create_zip(self, visibility_id, contract_ids, contracts, start_date, end_date):
        params = {"roleId": visibility_id, "lstCupsIds": contract_ids, "data": contracts,
                  "startDate": start_date, "endDate": end_date, "downloadType": DOWNLOAD_TYPE}
        return self.call("create_zip", params, DOWNLOAD_PAGE)

    def get_files(self, visibility_id):
        params = {"roleId": visibility_id, "type": FILE_TYPES}
        return self.call("get_files", params, DOWNLOAD_PAGE).get("data", {})

    def delete_file(self, transfer_id):
        return self.call("delete_file", {"transferId": transfer_id}, DOWNLOAD_PAGE)

    def list_notifications(self):
        return self.call("notifications_list", {}, NOTIFICATIONS_PAGE).get("lstNotifications", [])

    def delete_notifications(self, notification_ids):
        return self.call("delete_notifications", {"lstNotificationsIds": notification_ids},
                         NOTIFICATIONS_PAGE)

    def download_file(self, fileid):
        """Return the raw bytes of a file that get_files lists."""
        url = BASE + "/areaprivada/sfc/servlet.shepherd/version/download/" + fileid
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if self.session.sid:
            headers["Cookie"] = self.session.cookie_header()
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
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


def clock_hour(count, index):
    """Map the row index of a day (1 based) to the clock hour (0 to 23).

    The `Hora` column counts the rows of the day. A day of the change of the
    hour has 23 rows (spring) or 25 rows (autumn), not 24. The change is on a
    Sunday, so the hour does not change the period.
    """
    if count == 23 and index >= 3:
        hour = index
    elif count == 25 and index >= 4:
        hour = index - 2
    else:
        hour = index - 1
    return min(hour, 23)


def read_zip_rows(payload):
    """Return the rows of the hourly CSV files in the zip.

    Each row is (day, index, count, kwh, real). `index` counts from 1 inside
    the day. `count` is the number of rows of that day.
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
    rows = []
    for day in order:
        day_rows = days[day]
        count = len(day_rows)
        for index, (kwh, real) in enumerate(day_rows, start=1):
            rows.append((day, index, count, kwh, real))
    return rows


def zip_hours(payload):
    """Yield (day, hour, kwh, real) from the hourly CSV files in the zip."""
    for day, index, count, kwh, real in read_zip_rows(payload):
        yield day, clock_hour(count, index), kwh, real


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


def cookies_folders():
    """Return the folders to search for a cookies file, in this order."""
    return [os.path.join(os.path.expanduser("~"), "Downloads"), os.getcwd(), DIR]


def find_cookies_file():
    """Return the newest cookies file for the portal, by convention.

    The tool looks in the `Downloads` folder of your home, in the current
    folder and in the folder of the script. A file counts only when it is a
    `.txt` or `.json` file that mentions `edistribucion`. A name with `cookie`
    in it goes first. This avoids the cookie files of other sites.
    """
    best = None
    for folder in cookies_folders():
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
    sid, _ = portal_login(username, password)
    if not sid:
        return None
    session = Session(sid=sid, path=args.session)
    session.save()
    log("Stored session expired. Logged in again with the stored credentials.")
    return Client(session)


def load_context(args):
    client = build_client(args)
    log("Checking the session...")
    try:
        account = client.whoami()
    except (RuntimeError, urllib.error.URLError):
        account = None
        try:
            fresh = auto_login(args)
            if fresh is not None:
                client = fresh
                account = client.whoami()
        except (RuntimeError, urllib.error.URLError, OSError):
            account = None
        if account is None:
            raise
    log("Reading the list of supplies...")
    supplies = client.list_supplies(account["visibility_id"])
    return client, account, supplies


# ---------------------------------------------------------------- commands
def cmd_set_session(args):
    sid = (args.sid or "").strip().strip("\"'")
    if sid.startswith("sid="):
        sid = sid[4:].strip()
    session = Session(sid=sid or None, path=args.session)
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
    except (RuntimeError, urllib.error.URLError) as exc:
        print("Session saved, but the check failed:", exc, file=sys.stderr)
        sys.exit(1)


def cmd_import_cookies(args):
    path = args.file or find_cookies_file()
    if not path:
        print("No cookies file given, and no cookies file found.\n"
              "By default the tool uses the newest .txt or .json file that mentions\n"
              "edistribucion, in the Downloads folder, the current folder or the\n"
              "folder of the script. Export the cookies with the browser extension\n"
              "(see docs/AUTHENTICATION.md), or give the file:\n"
              "  edistribucion import-cookies <file>", file=sys.stderr)
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
    except (RuntimeError, urllib.error.URLError) as exc:
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


def ask_yes_no(question, default=False):
    """Ask a question on the terminal. Return the default when not interactive."""
    if not sys.stdin.isatty():
        return default
    hint = "Y/n" if default else "y/N"
    try:
        reply = input("%s [%s]: " % (question, hint)).strip().lower()
    except EOFError:
        return default
    if not reply:
        return default
    return reply in ("y", "yes")


def cmd_login(args):
    username = args.user
    password = args.password
    from_file = False
    if not (username and password) and os.path.exists(args.credentials):
        username, password = load_credentials(args.credentials)
        from_file = True
    if not username:
        username = input("NIF, passport or NIE: ").strip()
    if not password:
        password = getpass.getpass("Password: ")
    if not (username and password):
        print("Need a user and a password.", file=sys.stderr)
        sys.exit(1)

    print("Logging in by backend...")
    try:
        sid, text = portal_login(username, password)
    except (RuntimeError, urllib.error.URLError, OSError) as exc:
        print("Login request failed:", exc, file=sys.stderr)
        sys.exit(1)
    if not sid:
        print("The portal did not return a session. Raw response:", file=sys.stderr)
        print(text[:600], file=sys.stderr)
        sys.exit(1)

    session = Session(sid=sid, path=args.session)
    session.save()
    print("Session saved to", args.session)
    if not args.save and not from_file:
        args.save = ask_yes_no("Save the credentials for the auto login?")
    if args.save:
        path = save_credentials(username, password, args.credentials)
        print("Credentials saved with %s to %s" % (credential_backend(), path))
    try:
        account = Client(session).whoami()
        print("Login OK. User:", account["name"])
    except (RuntimeError, urllib.error.URLError) as exc:
        print("Session saved, but the check failed:", exc, file=sys.stderr)
        sys.exit(1)


def measure_tariff(listing, contracts):
    """Return the tariff name of a contract group, from the measure list."""
    wanted = {item["contract_id"] for item in contracts}
    for row in listing.get("lstCups") or []:
        if row.get("Id") in wanted and row.get("rate"):
            return row["rate"]
    return None


def download_notification_ids(notifications, known):
    """Return the ids of the new download notifications."""
    ids = []
    for item in notifications:
        identifier = item.get("Id")
        if not identifier or identifier in known:
            continue
        if "wp-massivemeasuredownload" in (item.get("URL__c") or ""):
            ids.append(identifier)
    return ids


def delete_download_leftovers(client, transfer_id, known_notifications, keep):
    """Delete the zip file and the notification of this run, unless keep is true."""
    if keep:
        log("The zip and the notification stay on the portal (--keep).")
        return
    try:
        client.delete_file(transfer_id)
        log("Zip deleted.")
    except (RuntimeError, urllib.error.URLError) as exc:
        log("Could not delete the zip: %s" % exc)
    try:
        notifications = client.list_notifications()
    except (RuntimeError, urllib.error.URLError) as exc:
        log("Could not read the notifications: %s" % exc)
        return
    ids = download_notification_ids(notifications, known_notifications)
    if not ids:
        return
    try:
        client.delete_notifications(ids)
        log("Notification deleted." if len(ids) == 1
            else "Notifications deleted: %d." % len(ids))
    except (RuntimeError, urllib.error.URLError) as exc:
        log("Could not delete the notifications: %s" % exc)


def _download_measure_zip(client, account, contracts, listing, wait_seconds, keep):
    """Ask the portal for one zip with all the hourly curves of a CUPS.

    The portal makes the zip in the background. This waits until the file
    appears in the download list, then returns its bytes. After the read it
    deletes the zip and its notification, unless keep is true.
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
    known_notifications = {item.get("Id") for item in client.list_notifications()}
    log("Requesting the zip (%s -> %s). The portal makes it in the background." % (start, end))
    client.create_zip(visibility, contract_ids, records, start, end)
    attempts = max(1, wait_seconds // ZIP_WAIT_SECONDS)
    for attempt in range(attempts):
        time.sleep(ZIP_WAIT_SECONDS)
        waited = (attempt + 1) * ZIP_WAIT_SECONDS
        log("  Waiting for the zip... %d s" % waited)
        files = client.get_files(visibility).get("lstFiles") or []
        fresh = [item for item in files if item.get("fileid") not in known]
        if fresh:
            title = fresh[0].get("Title")
            fileid = fresh[0]["fileid"]
            log("Zip ready: %s. Downloading..." % title)
            payload = client.download_file(fileid)
            log("Downloaded %.1f KiB." % (len(payload) / 1024.0))
            delete_download_leftovers(client, fresh[0]["Id"], known_notifications, keep)
            return payload
    raise RuntimeError("The portal did not make the zip in time (%d s)." % wait_seconds)


def fetch_hours(client, account, contracts, listing, wait_seconds=ZIP_WAIT_LIMIT, keep=False):
    """Download the zip and return {(day, hour): (kwh, real)}."""
    payload = _download_measure_zip(client, account, contracts, listing, wait_seconds, keep)
    hours = {}
    if payload:
        for day, hour, kwh, real in zip_hours(payload):
            key = (day, hour)
            old = hours.get(key)
            if old is None or (real and not old[1]):
                hours[key] = (kwh, real)
    log("Read %d hours from the zip." % len(hours))
    return hours


def aggregate(hours):
    """Build the consumption aggregates from {(day, hour): (kwh, real)}."""
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
    last_real = None
    day_counts = {}

    def bucket(group, key):
        return groups[group].setdefault(key, {"real_kwh": 0.0, "estimated_kwh": 0.0,
                                              "real_hours": 0, "estimated_hours": 0})

    # The status of each day, for the recent zoom. This keeps the pending days.
    for (day, _hour), (kwh, real) in hours.items():
        counts = day_counts.setdefault(day, {"real": 0, "estimated": 0, "kwh": 0.0})
        counts["kwh"] += kwh
        counts["real" if real else "estimated"] += 1
    pending_days = {day for day, value in day_counts.items()
                    if value["kwh"] == 0 and value["estimated"] and not value["real"]}

    for (day, hour), (kwh, real) in sorted(hours.items()):
        if day in pending_days:
            continue
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
            if last_real is None or day > last_real:
                last_real = day
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
        "last_real": last_real,
        "day_counts": day_counts,
    }


def collect_consumption(client, account, contracts, listing, wait_seconds=ZIP_WAIT_LIMIT,
                        keep=False):
    """Download the history and return the aggregates."""
    return aggregate(fetch_hours(client, account, contracts, listing, wait_seconds, keep))


def _groups_list(group_dict):
    return [{
        "key": key,
        "real_kwh": round(value["real_kwh"], 3),
        "estimated_kwh": round(value["estimated_kwh"], 3),
        "real_hours": value["real_hours"],
        "estimated_hours": value["estimated_hours"],
    } for key, value in sorted(group_dict.items())]


def _max_demand(client, account, cups_id, year_from, year_to):
    """Return the maximum demanded power per month, with the date and the hour."""
    monthly = {}
    for year in range(year_from, year_to + 1):
        data = client.get_maximeter(
            cups_id, account["visibility_id"], "1/%d" % year, "12/%d" % year)
        for point in data.get("lstData", []):
            if not point.get("valid"):
                continue
            date = point.get("date") or ""
            parts = date.split("-")
            key = "%s-%s" % (parts[2], parts[1]) if len(parts) == 3 else date
            monthly[key] = {"kw": point.get("value"), "date": date, "hour": point.get("hour")}
    return monthly


def day_status(counts):
    """Return R, E, M, P or . for a day.

    R real, E estimated, M mixed, P pending (estimated, but no reading yet),
    . no data.
    """
    if not counts:
        return "."
    if counts["real"] and counts["estimated"]:
        return "M"
    if counts["estimated"]:
        return "P" if counts["kwh"] == 0 else "E"
    return "R"


def month_map(day_counts):
    """Return year -> 12 symbols (R, E, M or .). Pending days are ignored."""
    years = {}
    for day, counts in day_counts.items():
        status = day_status(counts)
        if status in (".", "P"):
            continue
        row = years.setdefault(day.year, ["."] * 12)
        index = day.month - 1
        if row[index] == ".":
            row[index] = status
        elif row[index] != status:
            row[index] = "M"
    return {year: "".join(row) for year, row in years.items()}


def recent_ranges(day_counts, last_day, days=90):
    """Return the status of the last days as a list of ranges."""
    start = last_day - timedelta(days=days - 1)
    ranges = []
    run_start = run_end = None
    run_status = None
    day = start
    while day <= last_day:
        status = day_status(day_counts.get(day))
        if run_start is None:
            run_start = run_end = day
            run_status = status
        elif status == run_status and (day - run_end).days == 1:
            run_end = day
        else:
            ranges.append((run_start, run_end, run_status))
            run_start = run_end = day
            run_status = status
        day += timedelta(days=1)
    if run_start is not None:
        ranges.append((run_start, run_end, run_status))
    return ranges


def _print_kwh_table(title, key_label, rows):
    """Print a table with a real column, an estimated column and a total."""
    print(title)
    print("    %-8s %11s %11s %11s" % (key_label, "real kWh", "est. kWh", "total kWh"))
    for group in rows:
        real = group["real_kwh"]
        estimated = group["estimated_kwh"]
        print("    %-8s %11.3f %11.3f %11.3f"
              % (group["key"], real, estimated, real + estimated))


def _print_summary(reports):
    """Print one line per CUPS with the totals."""
    print("CUPS SUMMARY")
    print("  %-3s %-24s %-8s %11s %11s %11s"
          % ("#", "CUPS", "Tariff", "Real kWh", "Est. kWh", "Total kWh"))
    for index, result in enumerate(reports, start=1):
        real = result["real_kwh"]
        estimated = result["estimated_kwh"]
        print("  %-3d %-24s %-8s %11.3f %11.3f %11.3f"
              % (index, result["cups"], result["tariff"], real, estimated, real + estimated))
    print("  %-3s %-24s %-8s %11.3f %11.3f %11.3f"
          % ("-", "Total", "", sum(r["real_kwh"] for r in reports),
             sum(r["estimated_kwh"] for r in reports),
             sum(r["real_kwh"] + r["estimated_kwh"] for r in reports)))
    print()


def _print_report(result, titled=True):
    power = result["contracted_power_kw"]
    power_txt = ", ".join("%s %s kW" % (name, value) for name, value in sorted(power.items()))
    if titled:
        print("REPORT")
        print("CUPS:", result["cups"])
    print("Tariff:", result["tariff"])
    print("Contracted power:", power_txt or "-")
    print("Period:", result["from"], "->", result["to"])
    print()
    print("CONSUMPTION")
    names = sorted(result["periods_real_kwh"])
    real_periods = result["periods_real_kwh"]
    estimated_periods = result["periods_estimated_kwh"]
    rows = [
        ("Real", result["real_kwh"], result["real_hours"], real_periods),
        ("Estimated", result["estimated_kwh"], result["estimated_hours"], estimated_periods),
        ("Total", result["real_kwh"] + result["estimated_kwh"],
         result["real_hours"] + result["estimated_hours"],
         {name: real_periods.get(name, 0.0) + estimated_periods.get(name, 0.0)
          for name in names}),
    ]
    print("  %-11s %10s %16s  %s" % ("Consumption", "kWh", "hours",
                                     "  ".join("%9s" % name for name in names)))
    for label, kwh, hours, periods in rows:
        cells = "  ".join("%9.3f" % periods.get(name, 0.0) for name in names)
        print("  %-11s %10.3f %16s  %s" % (
            label, kwh, "%d h (%d d)" % (hours, round(hours / 24.0)), cells))
    print("  By year")
    print("    %-7s %11s %11s %11s   %14s %14s"
          % ("Year", "real kWh", "est. kWh", "total kWh", "real hours", "est. hours"))
    for group in result["consumption_by_year"]:
        real = group["real_kwh"]
        estimated = group["estimated_kwh"]
        real_h = group["real_hours"]
        estimated_h = group["estimated_hours"]
        print("    %-7s %11.3f %11.3f %11.3f   %14s %14s"
              % (group["key"], real, estimated, real + estimated,
                 "%d h (%d d)" % (real_h, round(real_h / 24.0)),
                 "%d h (%d d)" % (estimated_h, round(estimated_h / 24.0))))

    print("  By year period")
    header = "    %-7s" % "Year"
    for name in names:
        header += "  %10s %10s" % (name + " real", name + " est")
    print(header)
    for year, periods in sorted(result["periods_by_year"].items()):
        line = "    %-7s" % year
        for name in names:
            slot = periods.get(name, {})
            line += "  %10.3f %10.3f" % (slot.get("real", 0.0), slot.get("estimated", 0.0))
        print(line)

    _print_kwh_table("  By month", "Month", result["consumption_by_month"])
    _print_kwh_table("  By hour of day", "Hour", result["consumption_by_hour"])
    print()
    print("MAXIMUM PER YEAR")
    print("  Peak hour: the most energy in one hour (kWh). Peak demand: the top")
    print("  15 minute power (kW), from the portal. They can be on other days.")
    print("  %-4s  %10s  %-20s  %11s  %s"
          % ("Year", "Peak hour", "When", "Peak demand", "When"))
    hourly = result["max_hourly_by_year"]
    demand = result["max_demand_by_year"]
    for year in sorted(set(hourly) | set(demand)):
        peak = hourly.get(year)
        power = demand.get(year)
        peak_kwh = "%.3f kWh" % peak["kwh"] if peak else "-"
        peak_when = "%s %s" % (peak["date"], peak["hour"]) if peak else "-"
        power_kw = "%.3f kW" % power["kw"] if power else "-"
        power_when = ("%s %s" % (power["date"].replace("-", "/"), power["hour"])
                      if power else "-")
        print("  %-4s  %10s  %-20s  %11s  %s"
              % (year, peak_kwh, peak_when, power_kw, power_when))
    print()
    recent = result["recent"]
    labels = {"R": "real", "E": "estimated", "M": "mixed",
              "P": "pending (no reading yet)", ".": "no data"}
    print("RECENT (last 3 months)")
    print("  Today:        %s" % recent["today"])
    if recent["last_reading"]:
        print("  Last reading: %s (%s, %d days old)"
              % (recent["last_reading"], labels[recent["last_status"]], recent["delay_days"]))
    print("  Ranges:")
    for item in recent["ranges"]:
        span = (item["from"] if item["from"] == item["to"]
                else "%s..%s" % (item["from"], item["to"]))
        print("    %-24s %s" % (span, labels[item["status"]]))
    print()
    if result["has_estimated"]:
        print("READING MAP (R real, E estimated, M mixed, . no data)")
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        print("%-6s" % "" + " ".join(month.center(3) for month in months))
        for year in sorted(result["month_map"]):
            cells = [result["month_map"][year][index].center(3) for index in range(12)]
            print(("%-6s" % year + " ".join(cells)).rstrip())
    else:
        print("No estimated data. All the data is real.")


def _build_report(client, account, cups, group, listing, wait_seconds, keep):
    """Build the report of one CUPS. Return None when the CUPS has no data."""
    visibility = account["visibility_id"]
    current = next((item for item in group if not item.get("end")), group[-1])
    log("Reading the tariff...")
    tariff = measure_tariff(listing, group)
    if tariff and not tariff.startswith(SUPPORTED_TARIFF):
        raise RuntimeError("Unsupported tariff: %s. This tool supports 2.0TD only."
                           % tariff)
    data = collect_consumption(client, account, group, listing, wait_seconds, keep)
    if not data["from"]:
        log("  No data for this CUPS.")
        return None
    log("Reading the contracted power...")
    contracted = client.get_contracted_power(current["contract_id"], visibility)
    log("Reading the maximum demanded power (%d-%d)..."
        % (data["from"].year, data["to"].year))
    monthly_power = _max_demand(client, account, current["cups_id"],
                                data["from"].year, data["to"].year)
    year_power = {}
    for month_key, info in monthly_power.items():
        year = int(month_key.split("-")[0])
        if year not in year_power or info["kw"] > year_power[year]["kw"]:
            year_power[year] = info
    counts = data["day_counts"]
    window_end = max(counts) if counts else data["to"]
    today = date.today()
    last_value = max((day for day, value in counts.items() if value["kwh"] > 0),
                     default=None)
    ranges = recent_ranges(counts, window_end)
    return {
        "cups": cups,
        "tariff": tariff,
        "contracted_power_kw": contracted,
        "from": data["from"].isoformat(),
        "to": data["to"].isoformat(),
        "last_real": data["last_real"].isoformat() if data["last_real"] else None,
        "recent": {
            "today": today.isoformat(),
            "to": window_end.isoformat(),
            "last_reading": last_value.isoformat() if last_value else None,
            "last_status": day_status(counts.get(last_value)) if last_value else None,
            "delay_days": (today - last_value).days if last_value else None,
            "ranges": [{"from": first.isoformat(), "to": end.isoformat(), "status": status}
                       for first, end, status in ranges],
        },
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
        "month_map": month_map(counts),
        "consumption_by_year": _groups_list(data["groups"]["year"]),
        "consumption_by_month": _groups_list(data["groups"]["month"]),
        "consumption_by_hour": _groups_list(data["groups"]["hour"]),
        "max_hourly_by_year": {str(y): {"kwh": round(v[0], 3), "date": v[1], "hour": v[2]}
                               for y, v in sorted(data["year_peak"].items())},
        "max_hourly_by_month": {k: {"kwh": round(v[0], 3), "date": v[1], "hour": v[2]}
                                for k, v in sorted(data["month_peak"].items())},
        "max_demand_by_year": {str(y): v for y, v in sorted(year_power.items())},
        "max_demand_by_month": monthly_power,
    }


def cmd_report(args):
    client, account, supplies = load_context(args)
    visibility = account["visibility_id"]
    names = sorted({item["cups"] for item in supplies if item["cups"]})
    listing = client.list_measure_cups(visibility).get("data") or {}
    reports = []
    for cups in names:
        log("CUPS %s" % cups)
        group = [item for item in supplies if item["cups"] == cups]
        result = _build_report(client, account, cups, group, listing, args.wait, args.keep)
        if result:
            reports.append(result)
    if not reports:
        print("No data.", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return
    many = len(reports) > 1
    if many:
        _print_summary(reports)
    for index, result in enumerate(reports, start=1):
        if many:
            print("=" * 60)
            print("  CUPS %d of %d   %s" % (index, len(reports), result["cups"]))
            print("=" * 60)
            _print_report(result, titled=False)
            if index < len(reports):
                print()
        else:
            _print_report(result)


COMMANDS = ("set-session", "import-cookies", "login", "report")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Unofficial HTTP-only client for e-distribucion (no browser)")
    parser.add_argument("--session", default=DEFAULT_SESSION, help="path to the session file")
    parser.add_argument("--sid", help="value of the sid cookie")
    parser.add_argument("--wait", type=int, default=ZIP_WAIT_LIMIT,
                        help="seconds to wait for the portal zip (default %d)" % ZIP_WAIT_LIMIT)
    parser.add_argument("--keep", action="store_true",
                        help="keep the zip and the notification on the portal")
    parser.add_argument("--quiet", action="store_true", help="do not print the progress")
    parser.add_argument("--verbose", action="store_true", help="print more detail")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--session", default=argparse.SUPPRESS)
    common.add_argument("--sid", default=argparse.SUPPRESS)
    common.add_argument("--wait", type=int, default=argparse.SUPPRESS)
    common.add_argument("--keep", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    session_cmd = sub.add_parser("set-session", parents=[common],
                                 help="store a session value that you already have")
    session_cmd.add_argument("--cookie", help="extra cookies: 'k=v; k2=v2'")
    session_cmd.add_argument("--text",
                             help="a Cookie header or a cURL line that holds the session")
    session_cmd.set_defaults(func=cmd_set_session)

    imp = sub.add_parser("import-cookies", parents=[common],
                         help="import cookies from a cookies.txt (Netscape) or JSON file")
    imp.add_argument("file", nargs="?",
                     help="path to the cookies file (default: the newest .txt or .json "
                          "that mentions edistribucion, in Downloads, the current folder "
                          "or the folder of the script)")
    imp.set_defaults(func=cmd_import_cookies)

    login_cmd = sub.add_parser("login", parents=[common],
                               help="log in with user and password, no browser")
    login_cmd.add_argument("--user", help="NIF, passport or NIE")
    login_cmd.add_argument("--password", help="the password (or you are asked for it)")
    login_cmd.add_argument("--save", action="store_true",
                           help="store the credentials in the credential store of the system")
    login_cmd.add_argument("--credentials", default=DEFAULT_CREDENTIALS,
                           help="path to the credentials file")
    login_cmd.set_defaults(func=cmd_login)

    report = sub.add_parser("report", parents=[common],
                            help="full report for every CUPS (all data available)")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not any(argument in COMMANDS for argument in argv):
        argv.append("report")
    args = build_parser().parse_args(argv)
    global _QUIET, _VERBOSE
    _QUIET = getattr(args, "quiet", False)
    _VERBOSE = getattr(args, "verbose", False)
    try:
        args.func(args)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
