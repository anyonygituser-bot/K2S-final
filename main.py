import sys
import os
import json
import time
import subprocess
import importlib

# ── PATH SETUP ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REQUIREMENTS_FILE = os.path.join(DATA_DIR, ".requirements.json")
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

REQUIREMENTS = {
    "requests":        {"import": "requests", "pip": "requests>=2.31.0"},
    "rich":            {"import": "rich",     "pip": "rich>=13.0.0"},
    "Pillow":          {"import": "PIL",      "pip": "Pillow>=10.0.0"},
    "beautifulsoup4":  {"import": "bs4",      "pip": "beautifulsoup4"},
}


# ════════════════ REQUIREMENT CHECKING ════════════════

def get_version(import_name):
    """Get installed version of a package."""
    try:
        module = importlib.import_module(import_name)
        return getattr(module, "__version__", "unknown")
    except ImportError:
        return None


def install_package(pip_name):
    """Install a package via pip."""
    print(f"    Installing {pip_name}...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pip_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception as e:
        print(f"    Failed: {e}")
        return False


def check_requirements():
    """Check and install requirements. Returns True if all met."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(REQUIREMENTS_FILE):
        try:
            with open(REQUIREMENTS_FILE, "r") as f:
                locked = json.load(f)
            all_ok = True
            for pkg_key, info in REQUIREMENTS.items():
                version = get_version(info["import"])
                if version is None:
                    all_ok = False
                    break
            if all_ok:
                print("  Requirements: OK (cached)")
                return True
        except:
            pass

    print("  Checking requirements...")
    all_met = True
    versions = {}
    for pkg_key, info in REQUIREMENTS.items():
        import_name = info["import"]
        pip_name = info["pip"]
        version = get_version(import_name)
        if version:
            print(f"    {pkg_key}: {version} ✅")
            versions[pkg_key] = version
        else:
            print(f"    {pkg_key}: MISSING ❌")
            if install_package(pip_name):
                version = get_version(import_name)
                if version:
                    print(f"    {pkg_key}: {version} ✅ (installed)")
                    versions[pkg_key] = version
                else:
                    print(f"    {pkg_key}: FAILED ❌")
                    all_met = False
            else:
                all_met = False

    if all_met:
        with open(REQUIREMENTS_FILE, "w") as f:
            json.dump(versions, f, indent=2)
        print("  Requirements: All met. Lock file saved.")
    else:
        print("  Requirements: Some failed. Install manually:")
        for pkg_key, info in REQUIREMENTS.items():
            print(f"    pip install {info['pip']}")

    return all_met


# ════════════════ FILE INFO ════════════════

def get_file_info(file_id):
    """Fetch file name and size from K2S."""
    import requests
    try:
        r = requests.post("https://k2s.cc/api/v2/getFilesInfo", json={"ids": [file_id]}, timeout=10)
        if r.status_code == 200:
            info = r.json()['files'][0]
            return info['name'], int(info['size'])
    except Exception as e:
        print(f"  Error fetching file info: {e}")
    return None, None


# ════════════════ TOKEN CHECK ════════════════

def check_cached_tokens(file_id):
    """Check how many cached tokens exist for this file."""
    token_file = os.path.join(DATA_DIR, "tokens.json")
    if not os.path.exists(token_file):
        return 0
    try:
        with open(token_file, "r") as f:
            data = json.load(f)
        if file_id in data:
            now = time.time()
            return sum(1 for t in data[file_id]['tokens'] if now < t.get('expiry', 0))
    except:
        pass
    return 0


def load_cached_tokens(file_id):
    """Load cached token URLs for this file."""
    token_file = os.path.join(DATA_DIR, "tokens.json")
    if not os.path.exists(token_file):
        return []
    try:
        with open(token_file, "r") as f:
            data = json.load(f)
        if file_id in data:
            now = time.time()
            return [t['url'] for t in data[file_id]['tokens'] if now < t.get('expiry', 0)]
    except:
        pass
    return []


# ════════════════ HELPERS ════════════════

def format_time(seconds):
    if seconds < 0 or seconds == float('inf'):
        return "--:--:--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_dashboard(dl_engine, proxy_engine, start_time):
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

        if chunk_id >= 0 and chunk_total > 0:
            kb_bytes = chunk_bytes / 1024
            kb_total_w = chunk_total / 1024
            chunk_str = f"{kb_bytes:.0f}KB / {kb_total_w:.0f}KB"
            chunk_label = f"Chunk {chunk_id:>3}"
        else:
            chunk_str = "---"
            chunk_label = "Chunk ---"

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
            state_str = "Finished"
        else:
            state_str = state

        resume_str = f" (resumed {resume / 1024:.0f}KB)" if resume > 0 and state == "downloading" else ""

        line = f"W{wid:02d} : {chunk_label} | {chunk_str:>20} | {speed_w:>8.2f}KB/s | {state_str}{resume_str}"
        lines.append(line.ljust(120))

    return "\n".join(lines)


# ════════════════ MAIN ════════════════

def main():
    print()
    print("═" * 60)
    print("  K2S Downloader")
    print("═" * 60)
    print()

    # ── STEP 1: REQUIREMENTS ──
    print("[1/5] Checking requirements...")
    if not check_requirements():
        print("\n  Cannot continue. Fix requirements and try again.")
        input("\n  Press Enter to exit.")
        return
    print()

    # Import after requirements confirmed
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    from proxy_engine import ProxyEngine
    from minter import Minter
    from state_manager import StateManager
    from download_engine import DownloadEngine

    # ── STEP 2: FILE INFO ──
    print("[2/5] File info...")
    file_id = input("  File ID: ")
    if not file_id:
        print("  No file ID. Exiting.")
        return

    file_name, file_size = get_file_info(file_id)
    if not file_name:
        print("  Could not fetch file info. Check file ID.")
        input("\n  Press Enter to exit.")
        return

    size_mb = file_size / (1024 * 1024)
    print(f"  File: {file_name} ({size_mb:.1f} MB)")
    print()

    # ── STEP 3: PROXY CHECK ──
    print("[3/5] Checking proxies...")
    engine = ProxyEngine()
    engine.start()
    time.sleep(2)

    proxy_stats = engine.get_stats()
    validated = proxy_stats['validated']
    cold = proxy_stats['cold']

    if validated + cold == 0:
        print("  No proxies found. Run tests/fresh_proxies.py first.")
        engine.stop()
        input("\n  Press Enter to exit.")
        return

    print(f"  Proxies: {validated} validated, {cold} cold. ✅")
    print()

    # ── STEP 4: TOKEN CHECK ──
    print("[4/5] Checking tokens...")
    token_count = check_cached_tokens(file_id)
    if token_count < 250:
        print(f"  Tokens: {token_count} found. Need more. Starting minter...")
        print()
        minter = Minter(engine)
        try:
            minter.mint(file_id, target_tokens=250)
        except KeyboardInterrupt:
            print("\n  Minting cancelled.")
            engine.stop()
            input("\n  Press Enter to exit.")
            return

        token_count = check_cached_tokens(file_id)
        if token_count == 0:
            print("  No tokens minted. Cannot download.")
            engine.stop()
            input("\n  Press Enter to exit.")
            return
    else:
        print(f"  Tokens: {token_count} cached. ✅")

    tokens = load_cached_tokens(file_id)
    print()

    # ── STEP 5: DOWNLOAD ──
    print("[5/5] Starting download...")
    chunk_size = 5 * 1024 * 1024  # 5MB
    thread_count = 75

    state = StateManager()
    if state.load_state(file_name):
        completed, total = state.get_progress_chunks()
        print(f"  Resuming from {completed}/{total} chunks")
    else:
        state.init_download(file_id, file_name, file_size, chunk_size)
        print(f"  Fresh start. {state.total_chunks} chunks.")

    state.add_tokens(tokens)

    dl = DownloadEngine(state, engine, thread_count)
    dl.setup()

    start_time = time.time()

    try:
        import threading
        dl_thread = threading.Thread(target=dl.start, daemon=True)
        dl_thread.start()

        while dl_thread.is_alive():
            output = format_dashboard(dl, engine, start_time)
            os.system('cls' if os.name == 'nt' else 'clear')
            print(output)
            sys.stdout.flush()
            time.sleep(1)

        dl_thread.join()

        # Final display
        os.system('cls' if os.name == 'nt' else 'clear')
        print(format_dashboard(dl, engine, start_time))
        sys.stdout.flush()

        if state.is_download_complete():
            elapsed = time.time() - start_time
            print(f"\n  ✅ Download complete! File: {file_name}  |  Time: {format_time(elapsed)}")
        else:
            print(f"\n  Download stopped. Progress saved. Run again to resume.")

    except KeyboardInterrupt:
        print("\n\n  Stopping...")
        dl.stop()
        dl_thread.join(timeout=10)

    engine.stop()
    print()
    input("Press Enter to exit.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled. Run again to resume.")
    except Exception as e:
        print(f"\n  Error: {e}")
        input("\n  Press Enter to exit.")
