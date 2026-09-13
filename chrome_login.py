#!/usr/bin/env python3
"""
Launch Chrome, let the user log in, and capture the session cookie.

The tool starts Chrome with its own profile and a remote debugging port. It
connects over the DevTools Protocol and reads the `sid` cookie. The DevTools
Protocol sees HttpOnly cookies, so no code injection is needed.

Standard library only: the WebSocket client is small and built in.
"""
import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse

CHROME_CANDIDATES = [
    os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
]


def find_chrome():
    for path in CHROME_CANDIDATES:
        if path and os.path.exists(path):
            return path
    return None


def default_profile_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "edistribucion-client", "chrome-profile")


# ---------------------------------------------------------------- websocket
def ws_connect(url):
    parts = urlparse(url)
    host = parts.hostname
    port = parts.port or 80
    sock = socket.create_connection((host, port), timeout=30)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        "GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
        "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n" % (parts.path or "/", host, port, key)
    )
    sock.sendall(request.encode())
    reply = b""
    while b"\r\n\r\n" not in reply:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("WebSocket handshake failed.")
        reply += chunk
    if b"101" not in reply.split(b"\r\n", 1)[0]:
        raise RuntimeError("WebSocket handshake failed: " + reply.decode("latin1", "replace")[:160])
    return sock


def ws_send(sock, text):
    data = text.encode("utf-8")
    mask = os.urandom(4)
    header = bytearray([0x81])
    length = len(data)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", length)
    header += mask
    masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
    sock.sendall(bytes(header) + masked)


def _read_exact(sock, count):
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise RuntimeError("WebSocket closed.")
        data += chunk
    return data


def ws_recv(sock):
    first, second = _read_exact(sock, 2)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _read_exact(sock, 8))[0]
    payload = _read_exact(sock, length)
    if opcode == 0x9:  # ping
        sock.sendall(b"\x8a\x80" + b"\x00\x00\x00\x00")
        return ws_recv(sock)
    if opcode == 0x8:  # close
        raise RuntimeError("WebSocket closed by peer.")
    return payload.decode("utf-8", "replace")


class DevTools:
    def __init__(self, ws_url):
        self.sock = ws_connect(ws_url)
        self.counter = 0

    def call(self, method, params=None):
        self.counter += 1
        ws_send(self.sock, json.dumps({"id": self.counter, "method": method, "params": params or {}}))
        while True:
            message = json.loads(ws_recv(self.sock))
            if message.get("id") == self.counter:
                if "error" in message:
                    raise RuntimeError("DevTools error: %s" % message["error"])
                return message.get("result", {})

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def wait_devtools(port, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2) as response:
                return json.loads(response.read().decode("utf-8", "replace"))["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Chrome did not open the debugging port %d." % port)


def _kill_profile(profile_dir):
    if os.name != "nt":
        return
    script = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
              "Where-Object { $_.CommandLine -like '*%s*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" % profile_dir.replace("'", "''"))
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=30)
    except Exception:
        pass


def capture_sid(login_url, profile_dir=None, port=9333, timeout=300, keep_open=False):
    """Open Chrome, wait for the user to log in, return the sid cookie."""
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("Chrome not found. Install Chrome.")
    profile_dir = profile_dir or default_profile_dir()
    os.makedirs(profile_dir, exist_ok=True)

    ws_url = None
    try:
        ws_url = wait_devtools(port, timeout=3)
    except Exception:
        args = [
            chrome,
            "--user-data-dir=" + profile_dir,
            "--remote-debugging-port=%d" % port,
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--restore-last-session",
            login_url,
        ]
        subprocess.Popen(args)
        ws_url = wait_devtools(port, timeout=60)

    tools = DevTools(ws_url)
    sid = None
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = tools.call("Storage.getCookies")
            for cookie in result.get("cookies", []):
                if cookie.get("name") == "sid" and "edistribucion" in cookie.get("domain", ""):
                    sid = cookie.get("value")
                    break
            if sid:
                break
            time.sleep(1)
    finally:
        tools.close()
        if not keep_open:
            _kill_profile(profile_dir)
    return sid


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://zonaprivada.edistribucion.com/areaprivada/s/login/"
    value = capture_sid(url, keep_open="--keep-open" in sys.argv)
    print("sid:", "found" if value else "not found")
