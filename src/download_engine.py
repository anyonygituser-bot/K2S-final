import os
import time
import threading
import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
BINDINGS_FILE = os.path.join(_DATA_DIR, "bindings.json")

MIN_SPEED_KBPS = 10
SPEED_CHECK_INTERVAL = 5
STALE_DATA_TIMEOUT = 10
PROGRESS_UPDATE_BYTES = 512 * 1024  # 512KB
RECOVERY_COOLDOWN = 5
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
WAVE_INTERVAL = 15
WAVE_SIZE = 5
WAVE_HEALTH_THRESHOLD = 1.0  # 100% of workers must be downloading before expanding
STATE_SAVE_INTERVAL = 5
TOKEN_EXPIRY = 24 * 3600  # 24 hours


class DownloadEngine:

    def __init__(self, state_manager, engine, thread_count=50):
        self.state_manager = state_manager
        self.engine = engine
        self.thread_count = thread_count

        self.part_file = os.path.join(_DATA_DIR, state_manager.file_name + ".part")

        # Token-IP binding
        self.ip_to_token = {}      # {ip: token_url}
        self.binding_times = {}    # {ip: timestamp}
        self.binding_lock = threading.Lock()

        # Worker tracking
        self.worker_stats = {}
        self.workers_launched = 0
        self.worker_threads = []

        # Control
        self.is_running = False
        self.lock = threading.Lock()

    # ════════════════ BINDINGS PERSISTENCE ════════════════

    def _load_bindings(self):
        """Load bindings from disk. Returns set of bound token URLs."""
        bound_urls = set()
        if not os.path.exists(BINDINGS_FILE):
            return bound_urls

        try:
            with open(BINDINGS_FILE, "r") as f:
                data = json.load(f)

            now = time.time()
            expired_count = 0
            for ip, info in data.items():
                url = info.get("url")
                bound_time = info.get("bound_time", 0)

                if not url:
                    continue

                if now - bound_time >= TOKEN_EXPIRY:
                    expired_count += 1
                    continue

                self.ip_to_token[ip] = url
                self.binding_times[ip] = bound_time
                bound_urls.add(url)

            if expired_count > 0:
                print(f"[Downloader] Dropped {expired_count} expired bindings.")
                self._save_bindings_file()

            if bound_urls:
                print(f"[Downloader] Loaded {len(bound_urls)} active bindings from disk.")

        except Exception as e:
            print(f"[Downloader] Could not load bindings: {e}")

        return bound_urls

    def _save_binding(self, ip, token_url):
        """Save a single binding to disk."""
        with self.binding_lock:
            self.binding_times[ip] = time.time()
            self._save_bindings_file()

    def _remove_binding(self, ip):
        """Remove a single binding from memory and disk."""
        with self.binding_lock:
            self.ip_to_token.pop(ip, None)
            self.binding_times.pop(ip, None)
            self._save_bindings_file()

    def _save_bindings_file(self):
        """Write all current bindings to disk. Caller must hold binding_lock."""
        data = {}
        for ip, url in self.ip_to_token.items():
            data[ip] = {
                "url": url,
                "bound_time": self.binding_times.get(ip, 0)
            }
        try:
            tmp = BINDINGS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            for attempt in range(3):
                try:
                    os.replace(tmp, BINDINGS_FILE)
                    return
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.1)
                    else:
                        raise
        except Exception as e:
            print(f"[Downloader] Bindings save error: {e}")

    def _is_binding_expired(self, ip):
        bound_time = self.binding_times.get(ip, 0)
        return time.time() - bound_time >= TOKEN_EXPIRY

    # ════════════════ PUBLIC API ════════════════

    def setup(self):
        """Pre-allocate file and load bindings. Returns set of bound token URLs."""
        os.makedirs(_DATA_DIR, exist_ok=True)

        bound_urls = self._load_bindings()

        # Remove bound tokens from state_manager pool
        for url in bound_urls:
            self.state_manager.mark_token_dead(url)

        # Pre-allocate part file
        file_size = self.state_manager.file_size
        if not os.path.exists(self.part_file) or os.path.getsize(self.part_file) != file_size:
            print(f"[Downloader] Pre-allocating {file_size / (1024 * 1024):.2f}MB...")
            with open(self.part_file, "wb") as f:
                f.seek(file_size - 1)
                f.write(b'\0')
            print("[Downloader] Pre-allocation complete.")

        completed, total = self.state_manager.get_progress_chunks()
        if completed > 0:
            print(f"[Downloader] Resuming from {completed}/{total} chunks complete.")
        else:
            print(f"[Downloader] Starting fresh. {total} chunks to download.")

        return bound_urls

    def start(self):
        self.is_running = True

        monitor = threading.Thread(target=self._monitor, daemon=True)
        monitor.start()
        self.worker_threads.append(monitor)

        initial = min(WAVE_SIZE, self.thread_count)
        for _ in range(initial):
            self._launch_worker()

        print(f"[Downloader] Started wave 1: {initial} workers. Target: {self.thread_count}.")

        for t in self.worker_threads:
            t.join()

        self.is_running = False
        if self.state_manager.is_download_complete():
            self._finalize()

    def stop(self):
        self.is_running = False
        self.state_manager.save_state()

    def get_stats(self):
        completed, total = self.state_manager.get_progress_chunks()
        bytes_dl = self.state_manager.get_progress_bytes()
        kb_dl = bytes_dl / 1024
        kb_total = self.state_manager.file_size / 1024
        pct = (bytes_dl / self.state_manager.file_size * 100) if self.state_manager.file_size > 0 else 0

        global_speed = 0
        with self.lock:
            for ws in self.worker_stats.values():
                global_speed += ws.get("speed_kbps", 0)

        return {
            "completed": completed,
            "total": total,
            "bytes_downloaded": bytes_dl,
            "kb_downloaded": kb_dl,
            "kb_total": kb_total,
            "pct": pct,
            "speed_kbps": round(global_speed, 2),
            "tokens_available": self.state_manager.tokens_available(),
        }

    def get_full_stats(self):
        stats = self.get_stats()
        active = 0
        waiting = 0
        disconnected = 0
        with self.lock:
            for ws in self.worker_stats.values():
                s = ws.get("state")
                if s == "downloading":
                    active += 1
                elif s in ("waiting_proxy", "waiting_token", "recovery", "connecting", "waiting", "finished"):
                    waiting += 1
                elif s == "disconnected":
                    disconnected += 1
        stats["active_workers"] = active
        stats["waiting_workers"] = waiting
        stats["disconnected_workers"] = disconnected
        stats["workers"] = dict(self.worker_stats)
        stats["bindings"] = len(self.ip_to_token)
        return stats

    # ════════════════ WORKER LAUNCH ════════════════

    def _launch_worker(self):
        wid = self.workers_launched
        self.workers_launched += 1
        with self.lock:
            self.worker_stats[wid] = {
                "state": "init",
                "state_since": time.time(),
                "proxy_ip": "None",
                "current_chunk": -1,
                "chunk_bytes": 0,
                "chunk_total": 0,
                "resume_bytes": 0,
                "speed_kbps": 0,
                "chunks_completed": 0,
                "total_bytes": 0,
                "first_byte_time": None,
            }
        t = threading.Thread(target=self._worker, args=(wid,), daemon=True)
        t.start()
        self.worker_threads.append(t)

    # ════════════════ WORKER ════════════════

    def _worker(self, worker_id):
        proxy_url = None
        proxy_id = None
        proxy_ip = None
        token = None
        chunk_id = None
        married = False

        while self.is_running:
            if self.state_manager.is_download_complete():
                break

            # ── GET PROXY ──
            if not proxy_url:
                self._update_worker_state(worker_id, "waiting_proxy")
                proxy_data = self.engine.get_proxy(timeout=5)
                if not proxy_data:
                    self._update_worker_state(worker_id, "recovery")
                    time.sleep(RECOVERY_COOLDOWN)
                    continue

                proxy_url = proxy_data['url']
                proxy_id = proxy_data['id']
                proxy_ip = proxy_url.split("://")[1].split(":")[0]
                self._update_worker_state(worker_id, "connecting", proxy_ip=proxy_ip)

                # ── GET TOKEN (check binding first) ──
                with self.binding_lock:
                    token = self.ip_to_token.get(proxy_ip)

                if token:
                    if self._is_binding_expired(proxy_ip):
                        print(f"[Downloader] Binding expired for {proxy_ip}. Getting fresh token.")
                        self._remove_binding(proxy_ip)
                        token = None
                    else:
                        married = True

                if not token:
                    token = self.state_manager.checkout_token()
                    if not token:
                        self.engine.release_proxy(proxy_id)
                        proxy_url = None
                        proxy_id = None
                        proxy_ip = None
                        self._update_worker_state(worker_id, "waiting_token")
                        time.sleep(2)
                        continue
                    married = False

            # ── GET CHUNK ──
            if chunk_id is None:
                chunk_id = self.state_manager.get_next_chunk()

            if chunk_id is None:
                if self.state_manager.is_download_complete():
                    break
                self._update_worker_state(worker_id, "waiting")
                time.sleep(3)
                continue

            resume_byte = self.state_manager.get_resume_byte(chunk_id)
            start, end = self.state_manager.get_chunk_offset(chunk_id)
            chunk_total = end - start

            with self.lock:
                ws = self.worker_stats[worker_id]
                ws["current_chunk"] = chunk_id
                ws["chunk_bytes"] = resume_byte
                ws["chunk_total"] = chunk_total
                ws["resume_bytes"] = resume_byte
                ws["first_byte_time"] = None

            # ── DOWNLOAD ──
            success, bytes_written, result, got_first_byte = self._download_chunk(
                worker_id, chunk_id, resume_byte, start, end, proxy_url, token
            )

            # ── MARRIAGE CHECK (first byte = married) ──
            if not married and got_first_byte:
                with self.binding_lock:
                    self.ip_to_token[proxy_ip] = token
                self._save_binding(proxy_ip, token)
                married = True

            if success:
                self.state_manager.complete_chunk(chunk_id)
                self._update_worker_state(worker_id, "finished")
                with self.lock:
                    ws = self.worker_stats[worker_id]
                    ws["chunks_completed"] += 1
                chunk_id = None
                time.sleep(0.5)

            elif result == "409":
                self.state_manager.release_chunk(chunk_id)
                self.state_manager.mark_token_dead(token)
                self._remove_binding(proxy_ip)
                token = None
                chunk_id = None

            elif result == "already_done":
                self.state_manager.release_chunk(chunk_id)
                self._update_worker_state(worker_id, "finished")
                chunk_id = None
                time.sleep(0.3)

            else:
                self._update_worker_state(worker_id, "disconnected")
                self.engine.report_drop(proxy_id)

                if not married:
                    # Not married — return token to pool
                    self.state_manager.return_token(token)

                proxy_url = None
                proxy_id = None
                proxy_ip = None
                token = None
                married = False
                time.sleep(RECOVERY_COOLDOWN)

        # ── CLEANUP ──
        if chunk_id is not None:
            self.state_manager.release_chunk(chunk_id)
        if proxy_url and proxy_id:
            self.engine.release_proxy(proxy_id)

    # ════════════════ DOWNLOAD ════════════════

    def _download_chunk(self, worker_id, chunk_id, resume_byte, start, end, proxy_url, token):
        actual_start = start + resume_byte
        chunk_total = end - start
        proxy_dict = {"http": proxy_url, "https": proxy_url}
        headers = {"Range": f"bytes={actual_start}-{end - 1}"}
        bytes_written = resume_byte
        last_check_time = None
        last_check_bytes = resume_byte
        last_data_time = time.time()
        first_byte_time = None
        got_first_byte = False
        progress_since_save = 0

        self._update_worker_state(worker_id, "connecting")

        r = None
        try:
            r = requests.get(token, headers=headers, proxies=proxy_dict,
                             stream=True, verify=False,
                             timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))

            if r.status_code == 409:
                return False, bytes_written, "409", False

            if r.status_code not in (200, 206):
                return False, bytes_written, None, False

            with open(self.part_file, "r+b") as f:
                f.seek(actual_start)

                for data in r.iter_content(65536):
                    if not self.is_running:
                        return False, bytes_written, None, got_first_byte

                    if chunk_id in self.state_manager.completed_chunks:
                        return False, bytes_written, "already_done", got_first_byte

                    if data:
                        f.write(data)
                        bytes_written += len(data)
                        last_data_time = time.time()

                        if first_byte_time is None:
                            first_byte_time = time.time()
                            got_first_byte = True
                            with self.lock:
                                self.worker_stats[worker_id]["first_byte_time"] = first_byte_time
                                self.worker_stats[worker_id]["state"] = "downloading"
                                self.worker_stats[worker_id]["state_since"] = time.time()

                        with self.lock:
                            ws = self.worker_stats[worker_id]
                            ws["chunk_bytes"] = bytes_written
                            ws["total_bytes"] += len(data)

                        progress_since_save += len(data)
                        if progress_since_save >= PROGRESS_UPDATE_BYTES:
                            self.state_manager.update_chunk_progress(chunk_id, bytes_written)
                            progress_since_save = 0

                        now = time.time()

                        if first_byte_time and now - first_byte_time >= 1:
                            elapsed = now - first_byte_time
                            session_bytes = bytes_written - resume_byte
                            speed = (session_bytes / elapsed) / 1024
                            with self.lock:
                                self.worker_stats[worker_id]["speed_kbps"] = round(speed, 2)

                        if first_byte_time:
                            if last_check_time is None:
                                if now - first_byte_time >= SPEED_CHECK_INTERVAL:
                                    last_check_time = now
                                    last_check_bytes = bytes_written
                            else:
                                if now - last_check_time >= SPEED_CHECK_INTERVAL:
                                    speed_bytes = bytes_written - last_check_bytes
                                    speed_kbps = (speed_bytes / (now - last_check_time)) / 1024
                                    if speed_kbps < MIN_SPEED_KBPS:
                                        return False, bytes_written, None, got_first_byte
                                    last_check_time = now
                                    last_check_bytes = bytes_written

                    if time.time() - last_data_time > STALE_DATA_TIMEOUT:
                        return False, bytes_written, None, got_first_byte

            if bytes_written >= chunk_total:
                return True, bytes_written, None, True
            else:
                return False, bytes_written, None, got_first_byte

        except Exception:
            return False, bytes_written, None, got_first_byte

        finally:
            if r is not None:
                r.close()

    # ════════════════ MONITOR ════════════════

    def _monitor(self):
        while self.is_running:
            time.sleep(STATE_SAVE_INTERVAL)
            if not self.is_running:
                break

            self.state_manager.save_state()

            if self.state_manager.is_download_complete():
                self.is_running = False
                break

            # Wave expansion — only when ALL previous workers are downloading
            if self.workers_launched < self.thread_count:
                with self.lock:
                    downloading = sum(1 for ws in self.worker_stats.values()
                                      if ws["state"] == "downloading")
                    launched = self.workers_launched

                if launched > 0 and downloading == launched:
                    next_wave = min(WAVE_SIZE, self.thread_count - self.workers_launched)
                    if next_wave > 0:
                        for _ in range(next_wave):
                            self._launch_worker()
                        print(f"[Downloader] Wave expanded: {self.workers_launched}/{self.thread_count} workers.")

    # ════════════════ FINALIZE ════════════════

    def _finalize(self):
        final_path = os.path.join(_DATA_DIR, self.state_manager.file_name)
        if os.path.exists(self.part_file):
            os.rename(self.part_file, final_path)
        self.state_manager.delete_state()
        with self.binding_lock:
            self.ip_to_token.clear()
            self.binding_times.clear()
        if os.path.exists(BINDINGS_FILE):
            try:
                os.remove(BINDINGS_FILE)
            except Exception:
                pass
        print(f"[Downloader] Finalized: {self.state_manager.file_name}")

    # ════════════════ WORKER STATS ════════════════

    def _update_worker_state(self, worker_id, state, proxy_ip=None):
        with self.lock:
            ws = self.worker_stats[worker_id]
            ws["state"] = state
            ws["state_since"] = time.time()
            if proxy_ip:
                ws["proxy_ip"] = proxy_ip
            if state not in ("downloading", "connecting"):
                ws["speed_kbps"] = 0
                ws["first_byte_time"] = None
                ws["current_chunk"] = -1
                ws["chunk_bytes"] = 0
                ws["chunk_total"] = 0
                ws["resume_bytes"] = 0
