import requests
import time
import threading
import queue
import os
import ipaddress
from bs4 import BeautifulSoup

#══════════════════════════════════════════════════ SOURCES ═════════════════════════════════════════════════

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

K2S_URL = "https://k2s.cc"
K2S_TIMEOUT = 10
TEST_WORKERS = 225

#══════════════════════════════════════════════════ HELPERS ═════════════════════════════════════════════════

def is_valid_public_ip(ip_str: str) -> bool:
    """Check if an IP is valid, public, and not loopback/reserved/multicast."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return not (ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast)
    except ValueError:
        return False

#══════════════════════════════════════════════════ SCRAPER ═════════════════════════════════════════════════

class ProxyScraper:
    def __init__(self):
        # Key: (ip, port) -> Value: protocol
        self.proxies = {}
        self.lock = threading.Lock()

        # Tracking metrics
        self.source_stats = {}
        self.duplicates_dropped = 0
        self.private_ips_dropped = 0

    def _add(self, ip: str, port: str, protocol: str, source_url: str):
        """Validate, deduplicate, and store a proxy."""
        if not is_valid_public_ip(ip):
            with self.lock:
                self.private_ips_dropped += 1
            return

        key = (ip, port)
        with self.lock:
            if key in self.proxies:
                self.duplicates_dropped += 1
                return

            self.proxies[key] = protocol
            self.source_stats[source_url]["yield"] += 1

    def _init_source(self, source_url: str):
        """Ensure source is registered in stats."""
        with self.lock:
            if source_url not in self.source_stats:
                self.source_stats[source_url] = {"yield": 0, "error": False}

    def scrape_text(self, url: str, protocol: str):
        self._init_source(url)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                with self.lock: self.source_stats[url]["error"] = True
                return

            for line in r.text.splitlines():
                line = line.strip()
                if not line or ":" not in line or len(line) > 30:
                    continue

                # Strip protocol if somehow included in text list
                if "://" in line:
                    line = line.split("://")[1]

                parts = line.split(":")
                if len(parts) == 2:
                    self._add(parts[0], parts[1], protocol, url)
        except Exception:
            with self.lock:
                self.source_stats[url]["error"] = True

    def scrape_json(self, url: str, protocol: str):
        self._init_source(url)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                with self.lock: self.source_stats[url]["error"] = True
                return

            data = r.json()
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
                if ip and port:
                    self._add(ip, port, protocol, url)
        except Exception:
            with self.lock:
                self.source_stats[url]["error"] = True

    def scrape_html(self, url: str, protocol: str):
        self._init_source(url)
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                with self.lock: self.source_stats[url]["error"] = True
                return

            soup = BeautifulSoup(r.text, 'html.parser')
            for row in soup.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) >= 2:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    if ip and port:
                        self._add(ip, port, protocol, url)
        except Exception:
            with self.lock:
                self.source_stats[url]["error"] = True

    def scrape_all(self):
        threads = []

        for protocol, urls in TEXT_SOURCES.items():
            for url in urls:
                t = threading.Thread(target=self.scrape_text, args=(url, protocol), daemon=True)
                t.start()
                threads.append(t)

        for protocol, urls in JSON_SOURCES.items():
            for url in urls:
                t = threading.Thread(target=self.scrape_json, args=(url, protocol), daemon=True)
                t.start()
                threads.append(t)

        for protocol, urls in HTML_SOURCES.items():
            for url in urls:
                t = threading.Thread(target=self.scrape_html, args=(url, protocol), daemon=True)
                t.start()
                threads.append(t)

        for t in threads:
            t.join()

        return len(self.proxies)

    def get_proxy_strings(self) -> list:
        """Convert internal dict to list of protocol://ip:port strings."""
        return [f"{proto}://{ip}:{port}" for (ip, port), proto in self.proxies.items()]

    def get_top_sources(self, n=5) -> list:
        """Return top N sources by yield."""
        sorted_sources = sorted(
            self.source_stats.items(),
            key=lambda x: x[1]["yield"],
            reverse=True
        )
        return sorted_sources[:n]

#══════════════════════════════════════════════════ TESTER ═════════════════════════════════════════════════

class ProxyTester:
    def __init__(self, proxy_list):
        self.queue = queue.Queue()
        for p in proxy_list:
            self.queue.put(p)

        self.total = len(proxy_list)
        self.tested = 0
        self.passed = 0
        self.failed = 0
        self.working = []
        self.lock = threading.Lock()
        self.start_time = time.time()

    def _test(self, url):
        proxies = {"http": url, "https": url}
        try:
            r = requests.head(K2S_URL, proxies=proxies, timeout=K2S_TIMEOUT, verify=False)
            # 403 EXCLUDED - K2S banned/geo-blocked IPs are not "working"
            if r.status_code in (200, 301, 302):
                return True
        except Exception:
            pass
        return False

    def _worker(self):
        while True:
            try:
                url = self.queue.get(timeout=1)
            except queue.Empty:
                return

            if self._test(url):
                with self.lock:
                    self.tested += 1
                    self.passed += 1
                    self.working.append(url)
            else:
                with self.lock:
                    self.tested += 1
                    self.failed += 1

            self.queue.task_done()

    def run(self):
        threads = []
        for _ in range(TEST_WORKERS):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            threads.append(t)

        while any(t.is_alive() for t in threads):
            with self.lock:
                tested = self.tested
                passed = self.passed

            elapsed = time.time() - self.start_time
            rate = tested / elapsed if elapsed > 0 else 0
            pct = tested / self.total * 100 if self.total > 0 else 0
            eta = (self.total - tested) / rate if rate > 0 else 0

            print(f"\r  Testing: {tested}/{self.total} ({pct:.1f}%)  |  "
                  f"Rate: {rate:.0f}/s  |  "
                  f"Working: {passed}  |  "
                  f"ETA: {eta:.0f}s   ", end="", flush=True)
            time.sleep(0.5)

        for t in threads:
            t.join()

    def print_report(self):
        elapsed = time.time() - self.start_time
        by_protocol = {"http": 0, "socks4": 0, "socks5": 0}
        for p in self.working:
            proto = p.split("://")[0]
            if proto in by_protocol:
                by_protocol[proto] += 1

        print()
        print()
        print("  ═══════════════════════════════════════")
        print("  RESULTS")
        print("  ═══════════════════════════════════════")
        print(f"  Tested:    {self.tested}")
        print(f"  Working:   {self.passed}  ({self.passed / self.tested * 100:.1f}%)" if self.tested > 0 else "")
        print(f"  Failed:    {self.failed}")
        print(f"  Time:      {elapsed:.0f}s")
        print()
        print(f"    HTTP:   {by_protocol['http']}")
        print(f"    SOCKS4: {by_protocol['socks4']}")
        print(f"    SOCKS5: {by_protocol['socks5']}")
        print("  ═══════════════════════════════════════")
        print()

#═════════════════════════════════════════════════ MAIN ═════════════════════════════════════════════════

if __name__ == "__main__":
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    os.makedirs("data", exist_ok=True)

    # ──────────── STEP 1: SCRAPE ────────────
    print("  [1] Scraping all sources...")
    scraper = ProxyScraper()
    scrape_start = time.time()
    total_scraped = scraper.scrape_all()
    scrape_time = time.time() - scrape_start

    by_proto = {"http": 0, "socks4": 0, "socks5": 0}
    for (ip, port), proto in scraper.proxies.items():
        if proto in by_proto:
            by_proto[proto] += 1

    print(f"      Scraped {total_scraped} unique public proxies in {scrape_time:.1f}s")
    print(f"        HTTP: {by_proto['http']}  SOCKS4: {by_proto['socks4']}  SOCKS5: {by_proto['socks5']}")
    print(f"      Filtered: {scraper.private_ips_dropped} private/reserved IPs")
    print(f"      Deduped:  {scraper.duplicates_dropped} duplicate ip:port combinations")

    # Top Sources Report
    top_sources = scraper.get_top_sources(5)
    if top_sources:
        print("\n      Top 5 Sources:")
        for url, stats in top_sources:
            short_url = url.split("?")[0].split("/")[-1] or url.split("/")[2]
            print(f"        - {short_url}: {stats['yield']} proxies")

    # Save raw scraped proxies
    raw_path = "data/raw_proxies.txt"
    with open(raw_path, "w") as f:
        for p in scraper.get_proxy_strings():
            f.write(f"{p}\n")
    print(f"\n      Saved raw pool to {raw_path}")
    print()

    # ──────────── STEP 2: TEST ────────────
    print("  [2] Testing against K2S (8s timeout, strict 200/301/302)...")
    proxy_list = scraper.get_proxy_strings()
    tester = ProxyTester(proxy_list)
    tester.run()
    tester.print_report()

    # ──────────── STEP 3: SAVE WORKING ────────────
    with open("data/fresh_proxies.txt", "w") as f:
        for p in sorted(tester.working):
            f.write(f"{p}\n")

    print(f"  Saved {len(tester.working)} working proxies to data/fresh_proxies.txt")