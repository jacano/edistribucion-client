#!/usr/bin/env python3
"""
Read the portal session from the running Chrome over the DevTools Protocol.

The user logs in to the portal in their normal Chrome. This module connects to
Chrome with the DevTools Protocol and reads the `sid` cookie. The DevTools
Protocol sees HttpOnly cookies, so no code injection is needed.

The user turns on remote debugging one time:

    chrome://inspect/#remote-debugging

Chrome then writes `DevToolsActivePort` in its user data directory. This module
reads that file, connects to the browser WebSocket endpoint, and calls
`Storage.getCookies`.

Standard library only: the WebSocket client is small and built in.
"""
import base64
import json
import os
import socket
import struct
import time
from urllib.parse import urlparse


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
        sock.sendall(b"\x8a\x80\x00\x00\x00\x00")
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


# ---------------------------------------------------------------- capture
def default_user_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Google", "Chrome", "User Data")


def capture_sid(user_data_dir=None, timeout=30):
    """Read the portal sid from the running Chrome. Return None if not found."""
    user_data_dir = user_data_dir or default_user_data_dir()
    port_file = os.path.join(user_data_dir, "DevToolsActivePort")
    if not os.path.exists(port_file):
        raise RuntimeError(
            "Remote debugging is off. Open chrome://inspect/#remote-debugging "
            "in Chrome and turn it on.")
    with open(port_file, encoding="utf-8") as fh:
        lines = [line.strip() for line in fh.read().splitlines() if line.strip()]
    ws_url = "ws://127.0.0.1:%s%s" % (lines[0], lines[1])
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
    return sid


if __name__ == "__main__":
    print("sid:", "found" if capture_sid() else "not found")
