import requests
import time
import threading
import heapq
import os
import ipaddress
import json
from collections import deque
from bs4 import BeautifulSoup

#══════════════════════════════════════════════════ CONSTANTS ═════════════════════════════════════════════════

SEMAPHORE_LIMIT = 225
WORKER_COUNT = 225
K2S_URL = "https://k2s.cc"
K2S_TIMEOUT = 8
VALIDATED_TTL = 60
WARM_BREATHER = 6
PRISON_ESCALATION = [60, 90, 120, 300]
DEMOTE_THRESHOLD = 300
READY_THRESHOLD = 50
SCRAPE_INTERVAL = 300
SAVE_INTERVAL = 60

TEXT_SOURCES = {
    "http": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.txt",
        "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/refs/heads/main/http.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/http.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/refs/heads/master/generated/http_proxies.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/HTTPS_RAW.txt",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt",
        "https://raw.githubusercontent.com/BlackSnowDot/proxylist/master/output/http.txt",
        "https://raw.githubusercontent.com/BlackSnowDot/proxylist/master/output/https.txt",
        "https://raw.githubusercontent.com/Zaeem20/FREE-Proxies/master/PROXY_HTTP.txt",
        "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTP.txt",
        "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTPS.txt",
    ],
    "socks4": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks4/data.txt",
        "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/refs/heads/main/socks4.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/socks4.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/refs/heads/master/generated/socks4_proxies.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/SOCKS4_RAW.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
        "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks4/socks4.txt",
        "https://raw.githubusercontent.com/BlackSnowDot/proxylist/master/output/socks4.txt",
        "https://raw.githubusercontent.com/Zaeem20/FREE-Proxies/master/PROXY_SOCKS4.txt",
        "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/SOCKS4.txt",
    ],
    "socks5": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt",
        "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/refs/heads/main/socks5.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/socks5.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/refs/heads/master/generated/socks5_proxies.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/SOCKS5_RAW.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxylist.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
        "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt",
        "https://raw.githubusercontent.com/BlackSnowDot/proxylist/master/output/socks5.txt",
        "https://raw.githubusercontent.com/Zaeem20/FREE-Proxies/master/PROXY_SOCKS5.txt",
        "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/SOCKS5.txt",
    ]
}

JSON_SOURCES = {
    "http": [
        "https://proxylist.geonode.com/api/proxy-list?protocols=http&limit=500&page=1&sort_by=lastChecked&sort_type=desc",
        "https://proxylist.geonode.com/api/proxy-list?protocols=http&limit=500&page=2&sort_by=lastChecked&sort_type=desc",
        "https://proxylist.geonode.com/api/proxy-list?protocols=http&limit=500&page=3&sort_by=lastChecked&sort_type=desc",
        "https://api.proxyscrape.com/v3/free-proxy-list/get?request=display&protocol=http&timeout=5000",
    ],
    "socks4": [
        "https://proxylist.geonode.com/api/proxy-list?protocols=socks4&limit=500&page=1&sort_by=lastChecked&sort_type=desc",
        "https://proxylist.geonode.com/api/proxy-list?protocols=socks4&limit=500&page=2&sort_by=lastChecked&sort_type=desc",
        "https://api.proxyscrape.com/v3/free-proxy-list/get?request=display&protocol=socks4&timeout=5000",
    ],
    "socks5": [
        "https://proxylist.geonode.com/api/proxy-list?protocols=socks5&limit=500&page=1&sort_by=lastChecked&sort_type=desc",
        "https://proxylist.geonode.com/api/proxy-list?protocols=socks5&limit=500&page=2&sort_by=lastChecked&sort_type=desc",
        "https://api.proxyscrape.com/v3/free-proxy-list/get?request=display&protocol=socks5&timeout=5000",
    ]
}

HTML_SOURCES = {
    "http": [
        "https://proxydb.net/?protocol=http",
        "https://www.freeproxy.world/?type=http",
        "https://www.freeproxy.world/?type=http&page=2",
        "https://www.freeproxy.world/?type=http&page=3",
    ],
    "socks4": [
        "https://proxydb.net/?protocol=socks4",
        "https://www.freeproxy.world/?type=socks4",
        "https://www.freeproxy.world/?type=socks4&page=2",
    ],
    "socks5": [
        "https://proxydb.net/?protocol=socks5",
        "https://www.freeproxy.world/?type=socks5",
        "https://www.freeproxy.world/?type=socks5&page=2",
    ]
}

#══════════════════════════════════════════════════ HELPERS ═════════════════════════════════════════════════

def is_valid_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return not (ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast)
    except ValueError:
        return False

def is_valid_port(port_str: str) -> bool:
    try:
        port = int(port_str)
        return 1 <= port <= 65535
    except ValueError:
        return False

#══════════════════════════════════════════════════ PROXY ENGINE ═════════════════════════════════════════════════

class ProxyEngine:

    def __init__(self):
        self.is_running = False
        self.lock = threading.RLock()
        self.semaphore = threading.Semaphore(SEMAPHORE_LIMIT)

        # Persistent sets: (ip, port) tuples
        self.connected_set = set()
        self.unconnected_set = set()

        # Proxy metadata: (ip, port) -> {url, protocol, fail_count}
        self.proxy_map = {}

        # Internal queues
        self.warm_heap = []       # min-heap: (release_timestamp, (ip, port))
        self.prison_dict = {}     # (ip, port) -> release_timestamp
        self.cold_list = deque()  # deque for O(1) popleft

        # Validated pool: min-heap by response_time
        self.validated_heap = []  # (response_time, (ip, port))
        self.validated_meta = {}  # (ip, port) -> {timestamp, url}

        # Active downloads: TTL paused while here
        self.active_downloads = set()
        self.threads = []

    # ══════════════════════════ PUBLIC API ══════════════════════════

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        os.makedirs("data", exist_ok=True)
        print("[Engine] Starting up...")
        self._load_state()
        self._start_thread(self._state_saver)
        self._start_thread(self._ttl_sweeper)
        self._start_thread(self._scraper_loop)
        for _ in range(WORKER_COUNT):
            self._start_thread(self._worker)
        print(f"[Engine] Running. {WORKER_COUNT} workers. Semaphore {SEMAPHORE_LIMIT}.")

    def stop(self):
        if not self.is_running:
            return
        print("\n[Engine] Shutting down gracefully...")
        self.is_running = False
        self._save_state()
        print("[Engine] State saved. Goodbye.")

    @property
    def is_ready(self) -> bool:
        with self.lock:
            return len(self.validated_heap) >= READY_THRESHOLD

    def get_proxy(self, timeout=5, protocol=None):
        deadline = time.time() + timeout
        while self.is_running and time.time() < deadline:
            with self.lock:
                if self.validated_heap:
                    if not protocol:
                        rt, pid = heapq.heappop(self.validated_heap)
                        if pid in self.validated_meta:
                            url = self.validated_meta[pid]["url"]
                            proto = self.validated_meta[pid]["protocol"]
                            del self.validated_meta[pid]
                            self.active_downloads.add(pid)
                            return {"url": url, "id": pid, "response_time": rt, "protocol": proto}
                    else:
                        for i, (rt, pid) in enumerate(self.validated_heap):
                            if pid in self.validated_meta and self.validated_meta[pid]["protocol"] == protocol:
                                url = self.validated_meta[pid]["url"]
                                del self.validated_meta[pid]
                                self.active_downloads.add(pid)
                                self.validated_heap.pop(i)
                                heapq.heapify(self.validated_heap)
                                return {"url": url, "id": pid, "response_time": rt, "protocol": protocol}
            time.sleep(0.5)
        return None

    def report_drop(self, proxy_id):
        with self.lock:
            self.active_downloads.discard(proxy_id)
            if proxy_id in self.proxy_map:
                self._send_to_prison(proxy_id)

    def release_proxy(self, proxy_id):
        with self.lock:
            self.active_downloads.discard(proxy_id)
            if proxy_id in self.proxy_map:
                release_time = time.time() + WARM_BREATHER
                heapq.heappush(self.warm_heap, (release_time, proxy_id))

    def get_stats(self) -> dict:
        with self.lock:
            return {
                "validated": len(self.validated_heap),
                "warm": len(self.warm_heap),
                "prison": len(self.prison_dict),
                "cold": len(self.cold_list),
                "active": len(self.active_downloads),
                "connected": len(self.connected_set),
                "unconnected": len(self.unconnected_set),
                "is_ready": len(self.validated_heap) >= READY_THRESHOLD,
            }

    # ══════════════════════════ WORKERS ══════════════════════════

    def _worker(self):
        while self.is_running:
            self.semaphore.acquire()
            if not self.is_running:
                self.semaphore.release()
                break
            pid = self._get_next_to_test()
            if not pid:
                self.semaphore.release()
                time.sleep(1)
                continue
            passed, response_time = self._test_proxy(pid)
            self._route_result(pid, passed, response_time)
            self.semaphore.release()

    def _get_next_to_test(self):
        with self.lock:
            now = time.time()

            # Priority 1: Warm
            if self.warm_heap:
                release_time, pid = self.warm_heap[0]
                if now >= release_time:
                    heapq.heappop(self.warm_heap)
                    return pid

            # Priority 2: Prison
            for pid, release_time in list(self.prison_dict.items()):
                if now >= release_time:
                    del self.prison_dict[pid]
                    return pid

            # Priority 3: Cold
            if self.cold_list:
                return self.cold_list.popleft()

            return None

    def _test_proxy(self, pid):
        with self.lock:
            meta = self.proxy_map.get(pid)
            if not meta:
                return False, 0
            url = meta.get("url")
            protocol = meta.get("protocol")
        if not url:
            return False, 0

        proxies = {"http": url, "https": url}
        start = time.time()
        try:
            r = requests.head(K2S_URL, proxies=proxies, timeout=K2S_TIMEOUT, verify=False)
            elapsed = time.time() - start
            if r.status_code in (200, 301, 302):
                return True, round(elapsed, 3)
        except Exception:
            pass
        return False, 0

    MAX_UNCONNECTED_FAILS = 3

    def _route_result(self, pid, passed, response_time):
        with self.lock:
            if pid not in self.proxy_map:
                return

            if passed:
                self.proxy_map[pid]["fail_count"] = 0
                self.connected_set.add(pid)
                self.unconnected_set.discard(pid)
                heapq.heappush(self.validated_heap, (response_time, pid))
                self.validated_meta[pid] = {
                    "timestamp": time.time(),
                    "url": self.proxy_map[pid]["url"],
                    "protocol": self.proxy_map[pid]["protocol"]
                }
            else:
                if pid in self.connected_set:
                    self.proxy_map[pid]["fail_count"] += 1
                    self._send_to_prison(pid)
                else:
                    self.proxy_map[pid]["fail_count"] += 1
                    if self.proxy_map[pid]["fail_count"] >= self.MAX_UNCONNECTED_FAILS:
                        self.unconnected_set.discard(pid)
                        self.proxy_map.pop(pid, None)
                    else:
                        self.cold_list.append(pid)

    def _send_to_prison(self, pid):
        fail_count = self.proxy_map[pid]["fail_count"]
        idx = min(fail_count - 1, len(PRISON_ESCALATION) - 1)
        ttl = PRISON_ESCALATION[idx]
        if ttl > DEMOTE_THRESHOLD:
            self.connected_set.discard(pid)
            self.unconnected_set.add(pid)
            self.prison_dict.pop(pid, None)
            self.proxy_map[pid]["fail_count"] = 0
            self.cold_list.append(pid)
        else:
            self.prison_dict[pid] = time.time() + ttl

    # ══════════════════════════ BACKGROUND SERVICES ══════════════════════════

    def _ttl_sweeper(self):
        while self.is_running:
            time.sleep(10)
            now = time.time()
            with self.lock:
                expired = [
                    pid for pid, meta in self.validated_meta.items()
                    if now - meta["timestamp"] > VALIDATED_TTL
                    and pid not in self.active_downloads
                ]
                warm_pids = {pid for _, pid in self.warm_heap}
                for pid in expired:
                    del self.validated_meta[pid]
                    if pid not in warm_pids:
                        release_time = time.time() + WARM_BREATHER
                        heapq.heappush(self.warm_heap, (release_time, pid))
                        warm_pids.add(pid)

                self.validated_heap = [
                    (rt, pid) for rt, pid in self.validated_heap
                    if pid in self.validated_meta
                ]
                heapq.heapify(self.validated_heap)

    def _scraper_loop(self):
        while self.is_running:
            self._scrape()
            for _ in range(SCRAPE_INTERVAL):
                if not self.is_running:
                    return
                time.sleep(1)

    def _scrape(self):
        new_count = 0
        all_sources = []
        for protocol, urls in TEXT_SOURCES.items():
            for url in urls:
                all_sources.append((url, protocol, "text"))
        for protocol, urls in JSON_SOURCES.items():
            for url in urls:
                all_sources.append((url, protocol, "json"))
        for protocol, urls in HTML_SOURCES.items():
            for url in urls:
                all_sources.append((url, protocol, "html"))

        for url, protocol, fmt in all_sources:
            if not self.is_running:
                return
            try:
                proxies_raw = []
                r = requests.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                if fmt == "text":
                    proxies_raw = self._parse_text(r.text, protocol)
                elif fmt == "json":
                    proxies_raw = self._parse_json(r.text, protocol)
                elif fmt == "html":
                    proxies_raw = self._parse_html(r.text, protocol)
                for ip, port, proto in proxies_raw:
                    pid = (ip, port)
                    with self.lock:
                        if pid not in self.connected_set and pid not in self.unconnected_set:
                            self.unconnected_set.add(pid)
                            self.proxy_map[pid] = {
                                "url": f"{proto}://{ip}:{port}",
                                "protocol": proto,
                                "fail_count": 0
                            }
                            self.cold_list.append(pid)
                            new_count += 1
            except Exception:
                pass

    def _parse_text(self, text, protocol):
        results = []
        for line in text.splitlines():
            line = line.strip()
            if not line or ":" not in line or len(line) > 30:
                continue
            if "://" in line:
                line = line.split("://")[1]
            parts = line.split(":")
            if len(parts) == 2 and is_valid_public_ip(parts[0]) and is_valid_port(parts[1]):
                results.append((parts[0], int(parts[1]), protocol))
        return results

    def _parse_json(self, text, protocol):
        results = []
        try:
            data = json.loads(text) if isinstance(text, str) else text
        except Exception:
            return results
        proxy_list = []
        if isinstance(data, dict) and "data" in data:
            proxy_list = data["data"]
        elif isinstance(data, dict) and "proxies" in data:
            proxy_list = data["proxies"]
        elif isinstance(data, list):
            proxy_list = data
        for proxy in proxy_list:
            if not isinstance(proxy, dict):
                continue
            ip = proxy.get("ip", "")
            port = str(proxy.get("port", ""))
            if ip and port and is_valid_public_ip(ip) and is_valid_port(port):
                results.append((ip, int(port), protocol))
        return results

    def _parse_html(self, text, protocol):
        results = []
        try:
            soup = BeautifulSoup(text, 'html.parser')
            for row in soup.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) >= 2:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    if ip and port and is_valid_public_ip(ip) and is_valid_port(port):
                        results.append((ip, int(port), protocol))
        except Exception:
            pass
        return results

    # ══════════════════════════ PERSISTENCE ══════════════════════════

    def _load_state(self):
        conn_path = "data/connected.txt"
        if os.path.exists(conn_path):
            count = 0
            with self.lock:
                with open(conn_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if "://" not in line:
                            continue
                        proto, rest = line.split("://", 1)
                        if ":" not in rest:
                            continue
                        ip, port = rest.split(":", 1)
                        pid = (ip, int(port))
                        self.connected_set.add(pid)
                        self.proxy_map[pid] = {"url": line, "protocol": proto, "fail_count": 0}
                        heapq.heappush(self.warm_heap, (0, pid))
                        count += 1
            print(f"[Engine] Loaded {count} connected proxies for immediate testing.")

        unconn_path = "data/unconnected.txt"
        if os.path.exists(unconn_path):
            count = 0
            with self.lock:
                with open(unconn_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if "://" not in line:
                            continue
                        proto, rest = line.split("://", 1)
                        if ":" not in rest:
                            continue
                        ip, port = rest.split(":", 1)
                        pid = (ip, int(port))
                        if pid not in self.connected_set and pid not in self.unconnected_set:
                            self.unconnected_set.add(pid)
                            self.proxy_map[pid] = {"url": line, "protocol": proto, "fail_count": 0}
                            self.cold_list.append(pid)
                            count += 1
            print(f"[Engine] Loaded {count} unconnected proxies to cold queue.")

    def _state_saver(self):
        while self.is_running:
            for _ in range(SAVE_INTERVAL):
                if not self.is_running:
                    return
                time.sleep(1)
            self._save_state()

    def _save_state(self):
        tmp_conn = "data/connected.txt.tmp"
        tmp_unconn = "data/unconnected.txt.tmp"
        final_conn = "data/connected.txt"
        final_unconn = "data/unconnected.txt"
        with self.lock:
            try:
                with open(tmp_conn, "w") as f:
                    for pid in self.connected_set:
                        if pid in self.proxy_map:
                            f.write(f"{self.proxy_map[pid]['url']}\n")
                os.replace(tmp_conn, final_conn)
                with open(tmp_unconn, "w") as f:
                    for pid in self.unconnected_set:
                        if pid in self.proxy_map:
                            f.write(f"{self.proxy_map[pid]['url']}\n")
                os.replace(tmp_unconn, final_unconn)
            except Exception as e:
                print(f"[Engine] State save error: {e}")

    # ══════════════════════════ HELPERS ══════════════════════════

    def _start_thread(self, target):
        t = threading.Thread(target=target, daemon=True)
        t.start()
        self.threads.append(t)

#══════════════════════════════════════════════════ CONSOLE ENTRY ═════════════════════════════════════════════════

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    engine = ProxyEngine()
    engine.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        engine.stop()
