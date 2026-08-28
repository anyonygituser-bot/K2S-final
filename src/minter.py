import requests
import time
import threading
import json
import os
import subprocess
import platform
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
TOKEN_CACHE_FILE = os.path.join(_DATA_DIR, "tokens.json")
COOLDOWN_FILE = os.path.join(_DATA_DIR, "minter_cooldowns.json")

K2S_DOMAIN = "k2s.cc"
K2S_API = f"https://{K2S_DOMAIN}/api/v2"

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}


class Minter:

    def __init__(self, engine):
        self.engine = engine
        self.status = "Idle"
        self.tokens = []
        self.progress = 0
        self.total_to_mint = 0
        self.file_id = None
        self.cooldowns = self._load_cooldowns()
        self._lock = threading.Lock()

    # ════════════════ PUBLIC API ════════════════

    def mint(self, file_id, target_tokens=250):
        self.file_id = file_id
        self.total_to_mint = target_tokens
        self.status = "Checking cache..."

        cached = self._load_cache(file_id)
        if cached:
            self.tokens = cached
            self.progress = len(cached)
            if len(cached) >= self.total_to_mint:
                self.status = "Complete"
                print(f"[Minter] Loaded {len(cached)} tokens from cache!")
                return len(self.tokens)

            print(f"[Minter] Found {len(cached)} cached tokens. Minting {self.total_to_mint - len(cached)} more...")

        try:
            while len(self.tokens) < self.total_to_mint:

                # ── PHASE 1: CAPTCHA (retry 3x for hiccups) ──
                captcha_data = None
                for captcha_attempt in range(3):
                    self.status = f"Getting captcha (Home IP)... (Attempt {captcha_attempt + 1}/3)"
                    print(f"\n[Minter] Requesting captcha from Home IP... (Attempt {captcha_attempt + 1}/3)")
                    captcha_data = self._get_captcha()
                    if captcha_data:
                        break
                    time.sleep(2)

                if not captcha_data:
                    self.status = "Failed: Could not get captcha from Home IP."
                    break

                self.status = "Showing captcha..."
                self._open_image(captcha_data['url'])

                captcha_answer = input("\n> Enter captcha: ")

                free_download_key = None
                used_proxy_id = None
                used_proxy_dict = None
                is_invalid_captcha = False
                captcha_retried = False

                # ── PHASE 2: FIND WORKING PROXY (max 30 attempts) ──
                proxy_attempts = 0
                max_attempts = 30

                while proxy_attempts < max_attempts and not free_download_key:
                    proxy_attempts += 1
                    proxy_data = self.engine.get_proxy(timeout=3, protocol="http")
                    if not proxy_data:
                        self.status = "Failed: No proxies available!"
                        break

                    proxy_url = proxy_data['url']
                    proxy_id = proxy_data['id']
                    proxy_short = proxy_url.split("://")[1].split(":")[0]
                    proxy_dict = {"http": proxy_url, "https": proxy_url}

                    # Check K2S 2hr cooldown
                    if self._is_on_cooldown(proxy_url):
                        self.engine.release_proxy(proxy_id)
                        continue

                    self.status = f"Testing proxy {proxy_short} (Attempt {proxy_attempts})..."
                    print(f"[Minter] Testing proxy {proxy_short} (Attempt {proxy_attempts})...")

                    wait_time, key, is_invalid_captcha, reason = self._submit_captcha(
                        proxy_dict, captcha_data['challenge'], captcha_answer, file_id
                    )

                    # ── INVALID CAPTCHA: Retry once with same challenge ──
                    if is_invalid_captcha:
                        self.engine.release_proxy(proxy_id)
                        if not captcha_retried:
                            captcha_retried = True
                            print(f"[Minter] Invalid captcha. One retry with same challenge.")
                            self._open_image(captcha_data['url'])
                            captcha_answer = input("\n> Enter captcha again: ")
                            continue
                        else:
                            print(f"[Minter] Still invalid. Getting new captcha.")
                            break

                    # ── K2S BANNED / RATE LIMITED: Add cooldown ──
                    if reason in ("BANNED", "RATE_LIMITED"):
                        print(f"[Minter] Proxy {proxy_short} is {reason} by K2S. Adding to cooldown.")
                        self._add_cooldown(proxy_url, 7200)
                        self.engine.release_proxy(proxy_id)
                        continue

                    # ── SUCCESS: Key received ──
                    if key:
                        # Long wait time - IP is rate limited
                        if wait_time and wait_time > 30:
                            print(f"[Minter] Wait time {wait_time}s too long. Skipping proxy {proxy_short}.")
                            self._add_cooldown(proxy_url, 7200)
                            self.engine.release_proxy(proxy_id)
                            continue

                        free_download_key = key
                        used_proxy_id = proxy_id
                        used_proxy_dict = proxy_dict

                        # Register 2hr K2S cooldown for this IP
                        self._add_cooldown(proxy_url, 7200)
                        print(f"[Minter] Proxy {proxy_short} accepted! Key received.")

                        # ── PHASE 3: WAIT ──
                        if wait_time and wait_time > 0:
                            for i in range(wait_time, 0, -1):
                                self.status = f"Passed! Waiting {i}s..."
                                print(f"\r[Minter] Waiting {i}s...", end="", flush=True)
                                time.sleep(1)
                            print()

                        # ── PHASE 4: BURST MINT (until proxy dies) ──
                        self.status = "Minting..."
                        print(f"[Minter] Starting token generation burst...")
                        proxy_survived = self._generate_tokens(proxy_dict, file_id, free_download_key)

                        # ── PHASE 5: CLEANUP ──
                        if proxy_survived:
                            self.engine.release_proxy(used_proxy_id)
                        else:
                            self.engine.report_drop(used_proxy_id)
                            print("\n[Minter] Proxy died or key expired during minting. Will get new captcha/proxy.")
                            break

                    else:
                        # Direct URL case: save as 1 token, try next proxy
                        if reason == "Direct Link":
                            print(f"[Minter] Got direct link instead of key. Saved. Trying next proxy for a key...")
                            self.engine.release_proxy(proxy_id)
                            continue

                        # All other errors: proxy issue, try next
                        print(f"[Minter] Proxy {proxy_short} failed ({reason}). Trying next...")
                        self.engine.report_drop(proxy_id)

                if not free_download_key and not is_invalid_captcha:
                    self.status = f"Exhausted proxies. Have {len(self.tokens)} tokens."
                    print(f"\n[Minter] Exhausted proxy attempts. Proceeding with {len(self.tokens)} tokens.")
                    break

            self.status = "Complete"
            print(f"\n[Minter] Successfully minted {len(self.tokens)} tokens!")
            return len(self.tokens)

        finally:
            if len(self.tokens) > 0:
                self._save_cache()

    def checkout_token(self):
        """Pop one alive token. Removes from cache immediately."""
        with self._lock:
            now = time.time()
            while self.tokens:
                token = self.tokens.pop(0)
                if now < token.get('expiry', 0):
                    self._save_cache()
                    return token['url']
            self._save_cache()
            return None

    def mark_token_dead(self, token_url):
        """Remove a dead token from internal list and cache."""
        with self._lock:
            self.tokens = [t for t in self.tokens if t['url'] != token_url]
            self._save_cache()

    def tokens_available(self):
        """Count of alive, unchecked tokens."""
        with self._lock:
            now = time.time()
            return sum(1 for t in self.tokens if now < t.get('expiry', 0))

    def get_status_text(self):
        if self.status == "Minting":
            return f"Status: Minting... | Tokens: {self.progress}/{self.total_to_mint}"
        elif self.status.startswith("Waiting"):
            return self.status
        elif self.status == "Complete":
            return f"Status: Complete | Tokens Ready: {self.tokens_available()} | Cache: Active"
        else:
            return f"Status: {self.status}"

    # ════════════════ COOLDOWN MANAGEMENT ════════════════

    def _load_cooldowns(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        if not os.path.exists(COOLDOWN_FILE):
            return {}
        try:
            with open(COOLDOWN_FILE, "r") as f:
                data = json.load(f)
            now = time.time()
            return {ip: exp for ip, exp in data.items() if exp > now}
        except Exception:
            return {}

    def _save_cooldowns(self):
        try:
            with open(COOLDOWN_FILE, "w") as f:
                json.dump(self.cooldowns, f, indent=2)
        except Exception:
            pass

    def _add_cooldown(self, proxy_url, seconds):
        ip = proxy_url.split("://")[1].split(":")[0]
        self.cooldowns[ip] = time.time() + seconds
        self._save_cooldowns()

    def _is_on_cooldown(self, proxy_url):
        ip = proxy_url.split("://")[1].split(":")[0]
        return ip in self.cooldowns

    # ════════════════ CACHE MANAGEMENT ════════════════

    def _load_cache(self, file_id):
        os.makedirs(_DATA_DIR, exist_ok=True)
        if not os.path.exists(TOKEN_CACHE_FILE):
            return None
        try:
            with open(TOKEN_CACHE_FILE, "r") as f:
                data = json.load(f)
            if file_id in data:
                token_objects = data[file_id].get('tokens', [])
                now = time.time()
                alive = [t for t in token_objects if now < t.get('expiry', 0)]
                if len(alive) < len(token_objects):
                    print(f"[Minter] Cleaned {len(token_objects) - len(alive)} expired tokens from cache.")
                    data[file_id]['tokens'] = alive
                    self._atomic_write(TOKEN_CACHE_FILE, data)
                if alive:
                    return alive
        except Exception:
            pass
        return None

    def _save_cache(self):
        if not self.file_id:
            return
        data = {}
        if os.path.exists(TOKEN_CACHE_FILE):
            try:
                with open(TOKEN_CACHE_FILE, "r") as f:
                    data = json.load(f)
            except Exception:
                pass
        now = time.time()
        alive = [t for t in self.tokens if now < t.get('expiry', 0)]
        self.tokens = alive
        data[self.file_id] = {'tokens': alive}
        self._atomic_write(TOKEN_CACHE_FILE, data)

    def _atomic_write(self, filepath, data):
        tmp_path = filepath + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, filepath)
        except Exception as e:
            print(f"[Minter] Cache save error: {e}")

    # ════════════════ K2S API CALLS ════════════════

    def _get_captcha(self):
        try:
            r = requests.post(f"{K2S_API}/requestCaptcha", proxies=None, timeout=10, verify=True,
                              headers=API_HEADERS)
            if r.status_code == 200:
                d = r.json()
                return {'challenge': d.get('challenge'), 'url': d.get('captcha_url')}
        except Exception as e:
            print(f"[Minter] Captcha fetch error (Home IP): {e}")
        return None

    def _submit_captcha(self, proxy_dict, challenge, answer, file_id):
        payload = {
            "file_id": file_id,
            "captcha_challenge": challenge,
            "captcha_response": answer
        }
        try:
            r = requests.post(f"{K2S_API}/getUrl", json=payload, proxies=proxy_dict, timeout=10,
                              verify=False, headers=API_HEADERS)

            # Parse JSON if possible
            try:
                d = r.json()
            except:
                return None, None, False, f"Rejected (HTTP {r.status_code})"

            # ── SUCCESS ──
            if d.get('status') == 'success':
                wait_time = d.get('time_wait', 0)
                free_key = d.get('free_download_key')
                # Direct URL returned
                direct_url = d.get('url')
                if direct_url and not free_key:
                    with self._lock:
                        self.tokens.append({
                            'url': direct_url,
                            'mint_time': time.time(),
                            'expiry': time.time() + (24 * 3600)
                        })
                        self.progress = len(self.tokens)
                    return None, None, False, "Direct Link"

                if free_key:
                    return wait_time, free_key, False, "Success"

            # ── ERROR ──
            if d.get('status') == 'error':
                message = d.get('message', '').lower()
                # Invalid captcha (wrong answer OR expired)
                if 'invalid captcha' in message:
                    return None, None, True, "Invalid captcha"
                # Captcha/challenge related (expired, used, etc)
                if 'captcha' in message or 'challenge' in message:
                    return None, None, True, f"Captcha Issue: {d.get('message')}"
                # Rate limit / cooldown
                if 'wait' in message or 'limit' in message or 'cooldown' in message:
                    return None, None, False, "RATE_LIMITED"
                # IP blocked / banned / geo
                if 'block' in message or 'ban' in message or 'geo' in message:
                    return None, None, False, "BANNED"
                return None, None, False, f"API Error: {d.get('message')}"

            return None, None, False, f"Unknown response (HTTP {r.status_code})"

        except requests.exceptions.SSLError:
            return None, None, False, "SSL Error"
        except requests.exceptions.Timeout:
            return None, None, False, "Timeout"
        except requests.exceptions.ConnectionError:
            return None, None, False, "Network Error"
        except Exception:
            return None, None, False, "Unknown Error"

    def _generate_tokens(self, proxy_dict, file_id, free_download_key):
        proxy_dead = threading.Event()

        def mint_worker():
            while not proxy_dead.is_set():
                success = False
                for attempt in range(3):
                    if proxy_dead.is_set():
                        return
                    try:
                        payload = {"file_id": file_id, "free_download_key": free_download_key}
                        r = requests.post(f"{K2S_API}/getUrl", json=payload, proxies=proxy_dict,
                                          timeout=10, verify=False, headers=API_HEADERS)
                        if r.status_code == 200:
                            d = r.json()
                            url = d.get('url')
                            if url:
                                with self._lock:
                                    self.tokens.append({
                                        'url': url,
                                        'mint_time': time.time(),
                                        'expiry': time.time() + (24 * 3600)
                                    })
                                    self.progress = len(self.tokens)
                                    print(
                                        f"\r[Minter] Minting {self._draw_bar(self.progress, self.total_to_mint)}",
                                        end="", flush=True)
                                    if self.progress % 5 == 0:
                                        self._save_cache()
                                success = True
                                break
                            elif d.get('status') == 'error' and 'key' in d.get('message', '').lower():
                                proxy_dead.set()
                                return
                    except Exception:
                        pass
                if not success:
                    proxy_dead.set()
                    return

        threads = []
        for _ in range(10):
            t = threading.Thread(target=mint_worker, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        return not proxy_dead.is_set()

    # ════════════════ UTILITIES ════════════════

    def _draw_bar(self, current, total, length=30):
        pct = min(current / total, 1.0) if total > 0 else 0
        filled = int(length * pct)
        bar = '=' * filled + '-' * (length - filled)
        return f"[{bar}] {current}/{total}"

    def _open_image(self, url):
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            filepath = os.path.join(_DATA_DIR, "captcha.jpeg")
            r = requests.get(url, timeout=10, verify=True)
            with open(filepath, "wb") as f:
                f.write(r.content)
            if platform.system() == 'Windows':
                os.startfile(filepath)
            elif platform.system() == 'Darwin':
                subprocess.call(['open', filepath])
            else:
                subprocess.call(['xdg-open', filepath])
        except Exception as e:
            print(f"[Minter] Could not auto-open image: {e}. URL: {url}")
