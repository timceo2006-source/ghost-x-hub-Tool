# PWFKeys SDK v2.0  ·  build 1pi2b4d  ·  python  ·  app 8f5c522f-3e72-4078-b3ed-f7c6dd364f8d  ·  generated 2026-09-25 UTC
# Auto-generated — regenerate from the SDK Generator instead of editing by hand.

# Requires: pip install requests cryptography
import requests
import platform
import subprocess
import json as _json
import base64
import hashlib
import hmac
import os
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding


class CryptoEnvelope:
    """AES-256-CBC envelope encryption — mirrors the server's PayloadCrypto."""
    MAX_DRIFT = 300  # seconds — keep in sync with the server

    def __init__(self, app_secret):
        self.enc_key = hashlib.sha256(("enc:" + app_secret).encode()).digest()
        self.mac_key = hashlib.sha256(("mac:" + app_secret).encode()).digest()

    def encrypt(self, data):
        raw = _json.dumps(data).encode()
        iv = os.urandom(16)
        padder = padding.PKCS7(128).padder()
        padded = padder.update(raw) + padder.finalize()
        encryptor = Cipher(algorithms.AES(self.enc_key), modes.CBC(iv)).encryptor()
        ct = encryptor.update(padded) + encryptor.finalize()
        p = base64.b64encode(iv + ct).decode()
        t = int(time.time())
        s = hmac.new(self.mac_key, (p + str(t)).encode(), hashlib.sha256).hexdigest()
        return _json.dumps({"p": p, "t": t, "s": s})

    def decrypt(self, envelope_json):
        env = _json.loads(envelope_json)
        if not all(k in env for k in ("p", "t", "s")):
            raise ValueError("Invalid envelope format")
        p, t, s = env["p"], int(env["t"]), env["s"]

        expected = hmac.new(self.mac_key, (p + str(t)).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, s):
            raise ValueError("HMAC verification failed")

        if abs(int(time.time()) - t) > self.MAX_DRIFT:
            raise ValueError("Request expired (replay protection) - check the system clock")

        combined = base64.b64decode(p)
        iv, ct = combined[:16], combined[16:]
        decryptor = Cipher(algorithms.AES(self.enc_key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ct) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        raw = unpadder.update(padded) + unpadder.finalize()
        return _json.loads(raw)


class PWFLicense:
    BASE_URL = "https://pwfauth.com"
    APP_SECRET = "ea3e876c7d3a28937cd5ccd798b85a0d08951a7d89289480f789f9a39fb0eef1"

    def __init__(self):
        self.crypto = CryptoEnvelope(self.APP_SECRET)
        self.session = requests.Session()
        self.session.headers.update({
            "X-App-Secret": self.APP_SECRET,
            "Content-Type": "application/json",
        })
        self.session_id = None
        self.license_key = None
        self.heartbeat_interval = 30  # seconds; overwritten from the login response

    # Heartbeat replies that mean the session is gone for good — stop and log out.
    # (Kept in sync with api/auth/heartbeat.php.)
    KILL_CODES = {"BANNED", "PAUSED", "EXPIRED", "HWID_RESET", "MAINTENANCE",
                  "SESSION_REVOKED", "SESSION_EXPIRED", "SESSION_MISMATCH"}

    # How many CONSECUTIVE failed heartbeats end the session locally. Without this,
    # blocking the license domain in a firewall would keep the app running forever
    # while the server has long since dropped the session.
    MAX_HEARTBEAT_FAILURES = 3

    def get_hwid(self):
        """Stable per-machine id. Windows goes through CIM — wmic was deprecated and
        is GONE from Windows 11 24H2, so anything built on it silently degrades."""
        try:
            if platform.system() == "Windows":
                out = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-CimInstance Win32_BaseBoard).SerialNumber"],
                    stderr=subprocess.DEVNULL, creationflags=0x08000000)  # no console window
                serial = out.decode(errors="ignore").strip()
                if serial:
                    return serial
                return platform.node()
            with open("/etc/machine-id") as f:
                return f.read().strip()
        except Exception:
            return platform.node()

    def _parse_reply(self, res):
        """Shared reply handler for every transport. Surfaces HTTP/transport
        failures with a readable message instead of a cryptic JSON error, then
        transparently decrypts the body when the server enveloped it."""
        raw = res.text or ""
        if not raw.strip():
            raise RuntimeError(f"License server returned HTTP {res.status_code} with an empty body.")
        try:
            probe = _json.loads(raw)
        except ValueError:
            # Not JSON at all — usually a proxy/CDN error page or a wrong base URL.
            raise RuntimeError(
                f"License server returned HTTP {res.status_code} with a non-JSON body. "
                "Check the API base URL.")
        if isinstance(probe, dict) and all(k in probe for k in ("p", "t", "s")):
            return self.crypto.decrypt(raw)
        if res.status_code >= 400 and not (isinstance(probe, dict) and "success" in probe):
            raise RuntimeError(f"License server returned HTTP {res.status_code}.")
        return probe  # plain server response (its own success/error_code shape)

    def _post(self, endpoint, body):
        """Encrypt the request, send it, and hand the reply to _parse_reply."""
        encrypted = self.crypto.encrypt(body)
        res = self.session.post(self.BASE_URL + endpoint, data=encrypted, timeout=15)
        return self._parse_reply(res)

    def login(self, license_key):
        # login.php also activates the key on first use — no separate activate call.
        result = self._post("/api/auth/login.php", {
            "license_key": license_key,
            "hwid": self.get_hwid(),
        })
        if result.get("success"):
            self.session_id = result.get("session_id")
            self.license_key = license_key
            self.heartbeat_interval = int(result.get("heartbeat_interval", 30))
        return result

    def check_key(self, license_key):
        """Lightweight status + feature-map check WITHOUT opening a session
        (no device seat is consumed). Handy for a launcher/splash screen."""
        return self._post("/api/auth/check-key.php", {"license_key": license_key})

    def heartbeat(self):
        if not self.session_id:
            return None
        return self._post("/api/auth/heartbeat.php", {
            "session_id": self.session_id,
            "license_key": self.license_key,
        })

    def run_heartbeat(self, on_revoked):
        """Blocking loop (run it on a background thread). Pings on the server's
        interval and REACTS to the kill switch: the moment an admin bans / pauses /
        expires / resets or revokes the key, the heartbeat returns success=False and
        we call on_revoked(error_code, message) then stop.

        A single network blip is retried, but MAX_HEARTBEAT_FAILURES consecutive
        failures also end the session with NETWORK_LOST — the server drops the
        session anyway, so firewalling this domain must not leave a working app."""
        failures = 0
        while self.session_id:
            time.sleep(self.heartbeat_interval)
            try:
                r = self.heartbeat()
            except Exception:
                r = None
            if r is None:
                if not self.session_id:
                    return                      # logged out meanwhile
                failures += 1
                if failures >= self.MAX_HEARTBEAT_FAILURES:
                    self.session_id = None
                    on_revoked("NETWORK_LOST",
                               "Cannot reach the license server. "
                               "Please check your connection and sign in again.")
                    return
                continue                        # transient — retry next tick
            failures = 0
            if r.get("success"):
                continue
            code = r.get("error_code", "")
            if code in self.KILL_CODES:
                self.session_id = None          # session is dead server-side
                on_revoked(code, r.get("message", ""))
                return
            # Unknown non-success: treat as transient and keep trying.

    def _get(self, endpoint, bearer_key=None):
        """GET whose RESPONSE is enveloped (X-App-Secret rides on the session)."""
        headers = {"Authorization": "Bearer " + bearer_key} if bearer_key else {}
        res = self.session.get(self.BASE_URL + endpoint, headers=headers, timeout=15)
        return self._parse_reply(res)

    def _post_plain(self, endpoint, body):
        """POST plain JSON — endpoints that do NOT speak the envelope."""
        res = self.session.post(self.BASE_URL + endpoint, data=_json.dumps(body), timeout=15)
        return self._parse_reply(res)

    # App metadata + social links + server "what's new" (name, version, download URL, maintenance flags).
    def get_app_info(self):
        return self._get("/api/app/info.php")

    # Remote texts for THIS license (per-key overrides win over app defaults). Key rides in Authorization: Bearer.
    def get_texts(self):
        return self._get("/api/app/text.php", self.license_key)

    # Fetch the active promo / announcement slides configured for this app.
    def get_slides(self):
        return self._post("/api/app/slides.php", {"action": "get_slides"})

    # Ask for a newer build on the stable channel. Returns update_available + version/sha256/download_url.
    def check_update(self, current_version):
        return self._post("/api/update/check.php", {"v": current_version, "channel": "stable", "hwid": self.get_hwid(), "license_key": self.license_key})

    # Count a click on one of the app's social links (feeds the panel engagement stats).
    def track_social_click(self, link_id):
        return self._post("/api/app/social-click.php", {"link_id": link_id})

    # Mint a free trial key for this device. Off unless the owner enabled trials (else TRIAL_DISABLED / TRIAL_USED / TRIAL_LIMIT).
    def create_trial(self):
        return self._post_plain("/api/auth/trial.php", {"hwid": self.get_hwid()})

    # Queue an HWID-reset request for admin review (the reply is deliberately identical whether or not the key exists).
    def request_hwid_reset(self, reason):
        return self._post_plain("/api/auth/request-hwid-reset.php", {"license_key": self.license_key, "reason": reason})

    # Create an end-user account. Only works while the owner has user accounts switched on for this app.
    def register_account(self, username, password, email):
        return self._post_plain("/api/auth/account-register.php", {"username": username, "password": password, "email": email})

    # Sign an account in and open a session bound to this machine. Start the heartbeat afterwards, exactly as after a key login — the kill switch works the same way.
    def login_account(self, username, password):
        result = self._post_plain("/api/auth/account-login.php", {"username": username, "password": password, "hwid": self.get_hwid()})
        if result.get("success"):
            self.session_id = result.get("session_id")
            self.license_key = result.get("license_key", self.license_key)
        return result

    # Change an end-user account password. The current password is required — this is not an admin reset.
    def change_account_password(self, username, current_password, new_password):
        return self._post_plain("/api/auth/change-password.php", {"username": username, "current_password": current_password, "new_password": new_password})

    # Public price list — subscription levels and legacy plans for this app. No secret and no session needed, and the reply is plain JSON rather than enveloped.
    def get_pricing(self):
        return self._get("/api/app/pricing.php?app_id=8f5c522f-3e72-4078-b3ed-f7c6dd364f8d")

    def logout(self):
        if not self.session_id:
            return None
        result = self._post("/api/auth/logout.php", {
            "session_id": self.session_id,
            "license_key": self.license_key,
        })
        self.session_id = None
        return result


# Usage:
#   client = PWFLicense()
#   result = client.login("YOUR-LICENSE-KEY")
#   if result.get("success"):
#       features = result.get("features", {})   # entitlements returned by login
#
#       # Keep the session alive AND obey the admin kill switch. Run the loop on a
#       # background thread so your UI stays responsive; do NOT just ping once.
#       import threading
#       def on_revoked(code, message):
#           # code in {BANNED, PAUSED, EXPIRED, HWID_RESET, MAINTENANCE,
#           #          SESSION_REVOKED, SESSION_EXPIRED, SESSION_MISMATCH, NETWORK_LOST}
#           print("Session ended:", code, "-", message)
#           os._exit(0)  # log the user out of YOUR app here
#       threading.Thread(target=client.run_heartbeat, args=(on_revoked,), daemon=True).start()
#       ...
#       client.logout()
