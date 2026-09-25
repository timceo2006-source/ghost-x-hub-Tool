// PWFKeys SDK v2.0  ·  build 03x78dr  ·  csharp  ·  app 8f5c522f-3e72-4078-b3ed-f7c6dd364f8d  ·  generated 2026-09-25 UTC
// Auto-generated — regenerate from the SDK Generator instead of editing by hand.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Management;

namespace PWFLicense
{
    // AES-256-CBC envelope encryption — mirrors the server's PayloadCrypto.
    public class CryptoEnvelope
    {
        private readonly byte[] _encKey;
        private readonly byte[] _macKey;
        private const int MaxDriftSeconds = 300; // keep in sync with the server

        public CryptoEnvelope(string appSecret)
        {
            using (var sha = SHA256.Create())
            {
                _encKey = sha.ComputeHash(Encoding.UTF8.GetBytes("enc:" + appSecret));
                _macKey = sha.ComputeHash(Encoding.UTF8.GetBytes("mac:" + appSecret));
            }
        }

        public string Encrypt(Dictionary<string, object> data)
        {
            string json = JsonSerializer.Serialize(data);

            byte[] iv = new byte[16];
            using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(iv);

            byte[] cipher;
            using (var aes = Aes.Create())
            {
                aes.Key = _encKey; aes.IV = iv;
                aes.Mode = CipherMode.CBC; aes.Padding = PaddingMode.PKCS7;
                using (var enc = aes.CreateEncryptor())
                {
                    byte[] plain = Encoding.UTF8.GetBytes(json);
                    cipher = enc.TransformFinalBlock(plain, 0, plain.Length);
                }
            }

            byte[] combined = new byte[iv.Length + cipher.Length];
            Buffer.BlockCopy(iv, 0, combined, 0, iv.Length);
            Buffer.BlockCopy(cipher, 0, combined, iv.Length, cipher.Length);

            string p = Convert.ToBase64String(combined);
            long t = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

            string s;
            using (var hmac = new HMACSHA256(_macKey))
            {
                byte[] hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(p + t));
                s = BitConverter.ToString(hash).Replace("-", "").ToLower();
            }

            return JsonSerializer.Serialize(new Dictionary<string, object>
            {
                ["p"] = p, ["t"] = t, ["s"] = s
            });
        }

        public Dictionary<string, object> Decrypt(string envelopeJson)
        {
            var env = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(envelopeJson);
            if (env == null || !env.ContainsKey("p") || !env.ContainsKey("t") || !env.ContainsKey("s"))
                throw new Exception("Invalid envelope format");

            string p = env["p"].GetString();
            long t = env["t"].GetInt64();
            string s = env["s"].GetString();

            string expected;
            using (var hmac = new HMACSHA256(_macKey))
            {
                byte[] hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(p + t));
                expected = BitConverter.ToString(hash).Replace("-", "").ToLower();
            }
            if (!string.Equals(expected, s, StringComparison.OrdinalIgnoreCase))
                throw new Exception("HMAC verification failed");

            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            if (Math.Abs(now - t) > MaxDriftSeconds)
                throw new Exception("Request expired (replay protection) - check the system clock");

            byte[] combined = Convert.FromBase64String(p);
            byte[] iv = new byte[16];
            byte[] cipher = new byte[combined.Length - 16];
            Buffer.BlockCopy(combined, 0, iv, 0, 16);
            Buffer.BlockCopy(combined, 16, cipher, 0, cipher.Length);

            string json;
            using (var aes = Aes.Create())
            {
                aes.Key = _encKey; aes.IV = iv;
                aes.Mode = CipherMode.CBC; aes.Padding = PaddingMode.PKCS7;
                using (var dec = aes.CreateDecryptor())
                {
                    byte[] plain = dec.TransformFinalBlock(cipher, 0, cipher.Length);
                    json = Encoding.UTF8.GetString(plain);
                }
            }
            return JsonSerializer.Deserialize<Dictionary<string, object>>(json);
        }
    }

    public class LicenseClient
    {
        private readonly HttpClient _http = new HttpClient();
        private readonly string _baseUrl = "https://pwfauth.com";
        private readonly string _appSecret = "ea3e876c7d3a28937cd5ccd798b85a0d08951a7d89289480f789f9a39fb0eef1";
        private readonly CryptoEnvelope _crypto;
        private string _sessionId;
        private int _hbIntervalMs = 30000; // updated from the server's heartbeat_interval

        public string LicenseKey { get; private set; }

        // Server heartbeat responses that mean the session is GONE for good — stop the
        // loop and sign the user out. (Kept in sync with api/auth/heartbeat.php.)
        private static readonly HashSet<string> KillCodes = new HashSet<string>
        { "BANNED", "PAUSED", "EXPIRED", "HWID_RESET", "SESSION_REVOKED", "SESSION_EXPIRED",
          "SESSION_MISMATCH", "MAINTENANCE" };

        // How many CONSECUTIVE failed heartbeats end the session locally. Without this,
        // blocking the license domain in a firewall would keep the app running forever
        // while the server has long since dropped the session.
        private const int MaxHeartbeatFailures = 3;

        public LicenseClient()
        {
            _crypto = new CryptoEnvelope(_appSecret);
            _http.DefaultRequestHeaders.Add("X-App-Secret", _appSecret);
            _http.Timeout = TimeSpan.FromSeconds(15);
        }

        public string GetHWID()
        {
            try
            {
                var searcher = new ManagementObjectSearcher("SELECT SerialNumber FROM Win32_BaseBoard");
                foreach (var obj in searcher.Get())
                    return obj["SerialNumber"]?.ToString() ?? Environment.MachineName;
            }
            catch { }
            return Environment.MachineName;
        }

        // Shared reply handler for every transport. Surfaces HTTP/transport failures
        // with a readable message instead of a cryptic JSON exception, then
        // transparently decrypts the body when the server enveloped it.
        private Dictionary<string, object> ParseReply(string raw, HttpResponseMessage res)
        {
            int code = (int)res.StatusCode;
            if (string.IsNullOrWhiteSpace(raw))
                throw new Exception($"License server returned HTTP {code} with an empty body.");

            Dictionary<string, JsonElement> probe;
            try { probe = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(raw); }
            catch
            {
                // Not JSON at all — usually a proxy/CDN error page or a wrong base URL.
                throw new Exception($"License server returned HTTP {code} with a non-JSON body. Check the API base URL.");
            }

            bool isEnvelope = probe != null
                && probe.ContainsKey("p") && probe.ContainsKey("t") && probe.ContainsKey("s");

            if (isEnvelope)
                return _crypto.Decrypt(raw);

            // Plain JSON: the API's own {success,error_code,message} shape is returned
            // as-is (callers inspect it); anything else with a failing status is fatal.
            var plain = JsonSerializer.Deserialize<Dictionary<string, object>>(raw);
            if (code >= 400 && (plain == null || !plain.ContainsKey("success")))
                throw new Exception($"License server returned HTTP {code}.");
            return plain;
        }

        // Encrypts the request, sends it, and transparently handles the reply.
        // The server returns a plain (unencrypted) JSON object when it rejects
        // the request early — ParseReply detects that instead of failing to decrypt.
        private async Task<Dictionary<string, object>> PostAsync(string endpoint, Dictionary<string, object> body)
        {
            string encrypted = _crypto.Encrypt(body);
            var content = new StringContent(encrypted, Encoding.UTF8, "application/json");
            var res = await _http.PostAsync(_baseUrl + endpoint, content);
            return ParseReply(await res.Content.ReadAsStringAsync(), res);
        }

        // login.php also activates the key on first use — no separate activate endpoint.
        public async Task<Dictionary<string, object>> LoginAsync(string licenseKey)
        {
            var result = await PostAsync("/api/auth/login.php", new Dictionary<string, object>
            {
                ["license_key"] = licenseKey,
                ["hwid"] = GetHWID()
            });

            bool ok = result.ContainsKey("success")
                && ((JsonElement)result["success"]).GetBoolean();
            if (ok)
            {
                _sessionId = ((JsonElement)result["session_id"]).GetString();
                LicenseKey = licenseKey;
                if (result.ContainsKey("heartbeat_interval"))
                    _hbIntervalMs = ((JsonElement)result["heartbeat_interval"]).GetInt32() * 1000;
            }
            return result;
        }

        // Lightweight status check WITHOUT opening a session (no device seat used).
        // Returns the key's current status + its feature map — useful for a launcher
        // that wants to show entitlements before the user logs in.
        public async Task<Dictionary<string, object>> CheckKeyAsync(string licenseKey)
        {
            return await PostAsync("/api/auth/check-key.php", new Dictionary<string, object>
            {
                ["license_key"] = licenseKey
            });
        }

        public async Task<Dictionary<string, object>> HeartbeatAsync()
        {
            if (string.IsNullOrEmpty(_sessionId)) return null;
            return await PostAsync("/api/auth/heartbeat.php", new Dictionary<string, object>
            {
                ["session_id"] = _sessionId,
                ["license_key"] = LicenseKey
            });
        }

        // Drives the heartbeat on the server-provided interval and REACTS to the
        // server's kill switch: the instant an admin bans / pauses / expires / resets
        // or revokes the key, the next heartbeat comes back success=false and we sign
        // the user out via onRevoked(errorCode, message).
        //
        // A single network blip is retried, but MaxHeartbeatFailures consecutive
        // failures also end the session with NETWORK_LOST. That matters: the server
        // drops the session after SESSION_TIMEOUT anyway, so an attacker who firewalls
        // this domain must NOT be left with a working app.
        public async Task RunHeartbeatAsync(Action<string, string> onRevoked,
                                            System.Threading.CancellationToken ct = default(System.Threading.CancellationToken)) // typed default: compiles on C# 7.0 / older .NET Framework projects too
        {
            int failures = 0;
            while (!ct.IsCancellationRequested && !string.IsNullOrEmpty(_sessionId))
            {
                try { await Task.Delay(_hbIntervalMs, ct); } catch (TaskCanceledException) { return; }

                Dictionary<string, object> r = null;
                try { r = await HeartbeatAsync(); }
                catch { r = null; }

                if (r == null && _sessionId == null) return;   // logged out meanwhile
                if (r == null)
                {
                    if (++failures >= MaxHeartbeatFailures)
                    {
                        _sessionId = null;
                        onRevoked?.Invoke("NETWORK_LOST",
                            "Cannot reach the license server. Please check your connection and sign in again.");
                        return;
                    }
                    continue;                                   // transient — retry next tick
                }
                failures = 0;

                bool ok = r.ContainsKey("success") && ((JsonElement)r["success"]).GetBoolean();
                if (ok) continue;

                string code = r.ContainsKey("error_code") ? ((JsonElement)r["error_code"]).GetString() : "";
                string msg  = r.ContainsKey("message")    ? ((JsonElement)r["message"]).GetString()    : "";
                if (KillCodes.Contains(code))
                {
                    _sessionId = null;               // session is dead server-side
                    onRevoked?.Invoke(code, msg);    // e.g. show message + close the app
                    return;
                }
                // Unknown non-success: treat as transient and keep trying.
            }
        }

        // GET whose RESPONSE is enveloped (X-App-Secret is already a default header).
        // Pass the license key for endpoints that read Authorization: Bearer.
        private async Task<Dictionary<string, object>> GetAsync(string endpoint, string bearerKey = null)
        {
            var req = new HttpRequestMessage(HttpMethod.Get, _baseUrl + endpoint);
            if (!string.IsNullOrEmpty(bearerKey))
                req.Headers.TryAddWithoutValidation("Authorization", "Bearer " + bearerKey);
            var res = await _http.SendAsync(req);
            return ParseReply(await res.Content.ReadAsStringAsync(), res);
        }

        // POST plain JSON — endpoints that do NOT speak the envelope.
        private async Task<Dictionary<string, object>> PostPlainAsync(string endpoint, Dictionary<string, object> body)
        {
            var content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
            var res = await _http.PostAsync(_baseUrl + endpoint, content);
            return ParseReply(await res.Content.ReadAsStringAsync(), res);
        }

        // App metadata + social links + server "what's new" (name, version, download URL, maintenance flags).
        public async Task<Dictionary<string, object>> GetAppInfoAsync()
        {
            return await GetAsync("/api/app/info.php");
        }

        // Remote texts for THIS license (per-key overrides win over app defaults). Key rides in Authorization: Bearer.
        public async Task<Dictionary<string, object>> GetTextsAsync()
        {
            return await GetAsync("/api/app/text.php", LicenseKey);
        }

        // Fetch the active promo / announcement slides configured for this app.
        public async Task<Dictionary<string, object>> GetSlidesAsync()
        {
            return await PostAsync("/api/app/slides.php", new Dictionary<string, object>
            {
                ["action"] = "get_slides"
            });
        }

        // Ask for a newer build on the stable channel. Returns update_available + version/sha256/download_url.
        public async Task<Dictionary<string, object>> CheckUpdateAsync(string currentVersion)
        {
            return await PostAsync("/api/update/check.php", new Dictionary<string, object>
            {
                ["v"] = currentVersion,
                ["channel"] = "stable",
                ["hwid"] = GetHWID(),
                ["license_key"] = LicenseKey
            });
        }

        // Count a click on one of the app's social links (feeds the panel engagement stats).
        public async Task<Dictionary<string, object>> TrackSocialClickAsync(int linkId)
        {
            return await PostAsync("/api/app/social-click.php", new Dictionary<string, object>
            {
                ["link_id"] = linkId
            });
        }

        // Mint a free trial key for this device. Off unless the owner enabled trials (else TRIAL_DISABLED / TRIAL_USED / TRIAL_LIMIT).
        public async Task<Dictionary<string, object>> CreateTrialAsync()
        {
            return await PostPlainAsync("/api/auth/trial.php", new Dictionary<string, object>
            {
                ["hwid"] = GetHWID()
            });
        }

        // Queue an HWID-reset request for admin review (the reply is deliberately identical whether or not the key exists).
        public async Task<Dictionary<string, object>> RequestHwidResetAsync(string reason)
        {
            return await PostPlainAsync("/api/auth/request-hwid-reset.php", new Dictionary<string, object>
            {
                ["license_key"] = LicenseKey,
                ["reason"] = reason
            });
        }

        // Create an end-user account. Only works while the owner has user accounts switched on for this app.
        public async Task<Dictionary<string, object>> RegisterAccountAsync(string username, string password, string email)
        {
            return await PostPlainAsync("/api/auth/account-register.php", new Dictionary<string, object>
            {
                ["username"] = username,
                ["password"] = password,
                ["email"] = email
            });
        }

        // Sign an account in and open a session bound to this machine. Start the heartbeat afterwards, exactly as after a key login — the kill switch works the same way.
        public async Task<Dictionary<string, object>> LoginAccountAsync(string username, string password)
        {
            var result = await PostPlainAsync("/api/auth/account-login.php", new Dictionary<string, object>
            {
                ["username"] = username,
                ["password"] = password,
                ["hwid"] = GetHWID()
            });
            if (result.ContainsKey("success") && ((JsonElement)result["success"]).GetBoolean())
            {
                _sessionId = ((JsonElement)result["session_id"]).GetString();
                if (result.ContainsKey("license_key")) LicenseKey = ((JsonElement)result["license_key"]).GetString();
            }
            return result;
        }

        // Change an end-user account password. The current password is required — this is not an admin reset.
        public async Task<Dictionary<string, object>> ChangeAccountPasswordAsync(string username, string currentPassword, string newPassword)
        {
            return await PostPlainAsync("/api/auth/change-password.php", new Dictionary<string, object>
            {
                ["username"] = username,
                ["current_password"] = currentPassword,
                ["new_password"] = newPassword
            });
        }

        // Public price list — subscription levels and legacy plans for this app. No secret and no session needed, and the reply is plain JSON rather than enveloped.
        public async Task<Dictionary<string, object>> GetPricingAsync()
        {
            return await GetAsync("/api/app/pricing.php?app_id=8f5c522f-3e72-4078-b3ed-f7c6dd364f8d");
        }

        public async Task LogoutAsync()
        {
            if (string.IsNullOrEmpty(_sessionId)) return;
            await PostAsync("/api/auth/logout.php", new Dictionary<string, object>
            {
                ["session_id"] = _sessionId,
                ["license_key"] = LicenseKey
            });
            _sessionId = null;
        }
    }
}

// Usage:
//   var client = new LicenseClient();
//   var result = await client.LoginAsync("YOUR-LICENSE-KEY");
//   if (((JsonElement)result["success"]).GetBoolean())
//   {
//       // (optional) read entitlements returned by login:
//       //   var features = (JsonElement)result["features"];
//
//       // Keep the session alive AND obey the admin kill switch. This call loops
//       // until the server revokes the key — do NOT just fire a single heartbeat.
//       await client.RunHeartbeatAsync((code, message) =>
//       {
//           // code is one of: BANNED, PAUSED, EXPIRED, HWID_RESET, M
