import sys
import os
import time
import json
import requests
import urllib3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from proxy_engine import ProxyEngine
from minter import Minter
from state_manager import StateManager
from download_engine import DownloadEngine

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
TOKEN_CACHE_FILE = os.path.join(DATA_DIR, "tokens.json")
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB


def get_file_info(file_id):
    try:
        r = requests.post("https://k2s.cc/api/v2/getFilesInfo", json={"ids": [file_id]}, timeout=10)
        if r.status_code == 200:
            info = r.json()['files'][0]
            return info['name'], int(info['size'])
    except:
        pass
    return None, None


def load_cached_tokens(file_id):
    if not os.path.exists(TOKEN_CACHE_FILE):
        return []
    try:
        with open(TOKEN_CACHE_FILE, "r") as f:
            data = json.load(f)
        if file_id in data:
            now = time.time()
            return [t['url'] for t in data[file_id]['tokens'] if now < t.get('expiry', 0)]
    except:
        pass
    return []


def format_time(seconds):
    if seconds < 0 or seconds == float('inf'):
        return "--:--:--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_dashboard(dl_engine, proxy_engine, start_time):
    stats = dl_engine.get_full_stats()
    workers = stats["workers"]
    proxy_stats = proxy_engine.get_stats()

    # ── LINE 1: GLOBAL PROGRESS ──
    pct = stats["pct"]
    completed = stats["completed"]
    total = stats["total"]
    kb_dl = stats["kb_downloaded"]
    kb_total = stats["kb_total"]
    speed = stats["speed_kbps"]

    bar_len = 20
    filled = int(bar_len * pct / 100)
    bar = '█' * filled + '░' * (bar_len - filled)

    elapsed = time.time() - start_time
    elapsed_str = format_time(elapsed)

    if speed > 0:
        kb_remaining = kb_total - kb_dl
        eta_seconds = kb_remaining / speed
        eta_str = format_time(eta_seconds)
    else:
        eta_str = "--:--:--"

    line1 = f"Overall: {pct:>5.2f}% {bar} {kb_dl:.0f}KB / {kb_total:.0f}KB [{completed}/{total}]"
    line1 += f"  |  Speed: {speed:.1f}KB/s  |  Elapsed: {elapsed_str}  |  ETA: {eta_str}"

    # ── LINE 2: TOKENS & WORKERS ──
    line2 = f"Tokens: {stats['tokens_available']}  |  Bindings: {stats['bindings']}"
    line2 += f"  |  Active: {stats['active_workers']}  |  Waiting: {stats['waiting_workers']}  |  Disconnected: {stats['disconnected_workers']}"

    # ── LINE 3: PROXY POOL ──
    line3 = f"Proxies: Validated: {proxy_stats['validated']}  |  Cold: {proxy_stats['cold']}  |  Prison: {proxy_stats['prison']}"

    lines = [line1, line2, line3, ""]

    # ── WORKERS ──
    for wid in sorted(workers.keys()):
        ws = workers[wid]
        state = ws["state"]
        state_time = int(time.time() - ws["state_since"])
        chunk_id = ws["current_chunk"]
        chunk_bytes = ws["chunk_bytes"]
        chunk_total = ws["chunk_total"]
        speed_w = ws["speed_kbps"]
        resume = ws["resume_bytes"]

        # Format chunk info
        if chunk_id >= 0 and chunk_total > 0:
            kb_bytes = chunk_bytes / 1024
            kb_total_w = chunk_total / 1024
            chunk_str = f"{kb_bytes:.0f}KB / {kb_total_w:.0f}KB"
            chunk_label = f"Chunk {chunk_id:>3}"
        else:
            chunk_str = "---"
            chunk_label = "Chunk ---"

        # Format state
        if state == "downloading":
            state_str = f"Downloading ({state_time}s)"
        elif state == "connecting":
            state_str = f"Connecting ({state_time}s)"
        elif state == "waiting_proxy":
            state_str = f"Waiting ({state_time}s)"
        elif state == "waiting_token":
            state_str = f"No token ({state_time}s)"
        elif state == "waiting":
            state_str = f"Idle ({state_time}s)"
        elif state == "disconnected":
            state_str = f"Disconnected ({state_time}s)"
        elif state == "recovery":
            state_str = f"Recovery ({state_time}s)"
        elif state == "finished":
            state_str = f"Finished"
        elif state == "complete":
            state_str = "Complete"
        else:
            state_str = state

        # Resume indicator
        resume_str = f" (resumed {resume / 1024:.0f}KB)" if resume > 0 and state == "downloading" else ""

        line = f"W{wid:02d} : {chunk_label} | {chunk_str:>20} | {speed_w:>8.2f}KB/s | {state_str}{resume_str}"
        lines.append(line.ljust(120))

    return "\n".join(lines)


if __name__ == "__main__":
    file_id = input("File ID: ").strip()
    if not file_id:
        print("No file_id. Exiting.")
        sys.exit(1)

    file_name, file_size = get_file_info(file_id)
    if not file_name:
        print("Could not fetch file info. Exiting.")
        sys.exit(1)

    size_mb = file_size / (1024 * 1024)
    print(f"  File: {file_name} ({size_mb:.1f} MB)")

    # Load tokens
    tokens = load_cached_tokens(file_id)
    if not tokens:
        print(f"\n  No cached tokens for this file. Run test_minter.py first.")
        sys.exit(1)

    print(f"  Tokens: {len(tokens)} available")

    thread_count = input(f"Thread count (default 20): ").strip()
    thread_count = int(thread_count) if thread_count else 20

    # Setup state manager
    state = StateManager()
    if state.load_state(file_name):
        completed, total = state.get_progress_chunks()
        print(f"  State: Resuming from {completed}/{total} chunks")
    else:
        state.init_download(file_id, file_name, file_size, CHUNK_SIZE)
        print(f"  State: Fresh start. {state.total_chunks} chunks.")

    state.add_tokens(tokens)

    # Setup proxy engine
    proxy_engine = ProxyEngine()
    proxy_engine.start()

    # Setup download engine
    dl = DownloadEngine(state, proxy_engine, thread_count)
    dl.setup()

    start_time = time.time()

    try:
        # Start download in background
        import threading
        dl_thread = threading.Thread(target=dl.start, daemon=True)
        dl_thread.start()

        # Dashboard loop
        while dl_thread.is_alive():
            output = format_dashboard(dl, proxy_engine, start_time)
            os.system('cls' if os.name == 'nt' else 'clear')
            print(output)
            sys.stdout.flush()
            time.sleep(1)

        dl_thread.join()

        # Final state
        os.system('cls' if os.name == 'nt' else 'clear')
        print(format_dashboard(dl, proxy_engine, start_time))
        sys.stdout.flush()

        if state.is_download_complete():
            elapsed = time.time() - start_time
            print(f"\n  Download complete! File: {file_name}  |  Time: {format_time(elapsed)}")
        else:
            print(f"\n  Download stopped. Progress saved.")

    except KeyboardInterrupt:
        print("\n\n  Stopping...")
        dl.stop()

    proxy_engine.stop()