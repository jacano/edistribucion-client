#!/usr/bin/env python3
"""
Local MITM proxy that captures the `sid` cookie during login.

The flow:
  1. Start a local HTTP proxy on 127.0.0.1.
  2. Open Chrome through the proxy with a temporary profile.
  3. You log in to the portal in that window.
  4. The proxy reads the `sid` cookie from the login response (Set-Cookie).
  5. The tool saves the session and closes the window.

Only the login goes through the proxy. Later data calls use plain HTTP with the
session cookie. The proxy forces HTTP/1.1 so the headers stay readable.

Needs the `cryptography` package (to make the temporary certificates).
"""
import datetime
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

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


class CertAuthority:
    def __init__(self, folder):
        self.folder = folder
        now = datetime.datetime.now(datetime.timezone.utc)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "edistribucion login proxy")])
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(self.key, hashes.SHA256())
        )
        self.ca_path = os.path.join(folder, "ca.crt")
        with open(self.ca_path, "wb") as fh:
            fh.write(self.cert.public_bytes(serialization.Encoding.PEM))
        self._leaves = {}

    def leaf(self, host):
        if host in self._leaves:
            return self._leaves[host]
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", host)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
            .issuer_name(self.cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
            .sign(self.key, hashes.SHA256())
        )
        cert_path = os.path.join(self.folder, "leaf_%s.pem" % safe)
        key_path = os.path.join(self.folder, "leaf_%s.key" % safe)
        with open(cert_path, "wb") as fh:
            fh.write(cert.public_bytes(serialization.Encoding.PEM))
            fh.write(self.cert.public_bytes(serialization.Encoding.PEM))
        with open(key_path, "wb") as fh:
            fh.write(key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
        self._leaves[host] = (cert_path, key_path)
        return self._leaves[host]


class LoginProxy:
    def __init__(self, port, on_sid):
        self.port = port
        self.on_sid = on_sid
        self.sid = None
        self.stop = threading.Event()
        self.folder = tempfile.mkdtemp(prefix="edist-login-proxy-")
        self.ca = CertAuthority(self.folder)
        self.socket = None

    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("127.0.0.1", self.port))
        self.socket.listen(100)
        self.socket.settimeout(1.0)
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        self.stop.set()
        try:
            self.socket.close()
        except Exception:
            pass

    def _accept(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            conn.settimeout(30)
            header = self._read_headers(conn)
            if not header:
                return
            first = header.split(b"\r\n", 1)[0].decode("latin1")
            if first.upper().startswith("CONNECT"):
                host_port = first.split()[1]
                host, _, port = host_port.partition(":")
                self._mitm(conn, host, int(port or "443"))
            else:
                self._plain(conn, header)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _read_headers(conn):
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 65536:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    def _mitm(self, conn, host, port):
        conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        cert_path, key_path = self.ca.leaf(host)
        client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        client_ctx.load_cert_chain(cert_path, key_path)
        client_ctx.set_alpn_protocols(["http/1.1"])
        tls_client = client_ctx.wrap_socket(conn, server_side=True)

        upstream = socket.create_connection((host, port), timeout=30)
        up_ctx = ssl.create_default_context()
        up_ctx.set_alpn_protocols(["http/1.1"])
        tls_up = up_ctx.wrap_socket(upstream, server_hostname=host)

        down = threading.Thread(target=self._pump, args=(tls_up, tls_client, True), daemon=True)
        up = threading.Thread(target=self._pump, args=(tls_client, tls_up, False), daemon=True)
        down.start()
        up.start()
        down.join()
        up.join()

    def _plain(self, conn, header):
        request_line = header.split(b"\r\n", 1)[0].decode("latin1")
        try:
            url = request_line.split()[1]
            host, _, path = url[len("http://"):].partition("/")
            host, _, port = host.partition(":")
            upstream = socket.create_connection((host, int(port or "80")), timeout=30)
            upstream.sendall(header)
            self._pump(upstream, conn, False)
            upstream.close()
        except Exception:
            pass

    def _pump(self, src, dst, scan):
        buf = b""
        try:
            while not self.stop.is_set():
                data = src.recv(65536)
                if not data:
                    break
                if scan:
                    buf = (buf + data)[-20000:]
                    self._scan(buf)
                dst.sendall(data)
        except Exception:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except Exception:
                pass

    def _scan(self, buf):
        low = buf.lower()
        pos = low.find(b"set-cookie:")
        while pos != -1 and not self.sid:
            end = buf.find(b"\r\n", pos)
            segment = buf[pos:end if end != -1 else pos + 2048]
            match = re.search(rb"(?i)\bsid=([^;\r\n]+)", segment)
            if match:
                self.sid = match.group(1).decode("latin1")
                if self.on_sid:
                    self.on_sid(self.sid)
                return
            pos = low.find(b"set-cookie:", pos + 1)


def default_user_data_dir():
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return os.path.join(base, "Google", "Chrome", "User Data")
    return None


def chrome_running():
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                             capture_output=True, text=True, timeout=15).stdout
        return "chrome.exe" in out.lower()
    except Exception:
        return False


def kill_chrome():
    if os.name != "nt":
        return
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def capture_sid(login_url, port=8765, timeout=240, user_data_dir=None, force=False):
    """Use the normal Chrome profile through the proxy and return the sid cookie.

    Chrome allows one instance per profile. So Chrome must be closed first.
    After the capture, Chrome reopens without the proxy.
    """
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("Chrome not found. Install Chrome or pass the path.")
    profile = user_data_dir or default_user_data_dir()
    if chrome_running():
        if not force:
            raise RuntimeError("Chrome is open. Close it first, or run with --force.")
        kill_chrome()
        time.sleep(2)

    result = {}
    proxy = LoginProxy(port, lambda sid: result.setdefault("sid", sid))
    proxy.start()
    args = [
        chrome,
        "--user-data-dir=" + profile,
        "--proxy-server=127.0.0.1:%d" % port,
        "--ignore-certificate-errors",
        "--no-first-run",
        "--no-default-browser-check",
        "--restore-last-session",
        login_url,
    ]
    subprocess.Popen(args)
    deadline = time.time() + timeout
    try:
        while time.time() < deadline and not proxy.sid:
            time.sleep(0.5)
    finally:
        proxy.close()
        kill_chrome()
    time.sleep(1)
    subprocess.Popen([chrome, "--restore-last-session"])
    return result.get("sid"), proxy.ca.ca_path


if __name__ == "__main__":
    sid, ca = capture_sid(sys.argv[1] if len(sys.argv) > 1 else "https://example.com")
    print("sid:", sid)
    print("ca:", ca)
