# K2S Downloader: Complete Project Documentation

## Table of Contents

1. Introduction & Overview
2. The Problem Domain: Keep2Share (K2S)
3. Bypass Strategies & Architecture
4. Project Structure & File Manifest
5. Deep Dive: Core Modules (src/)
6. The Orchestrator: main.py
7. Testing & Inference (tests/)
8. Data Management & Persistence
9. Requirements & Dependencies

---

## 1. Introduction & Overview

K2S Downloader is a high-performance, parallel file downloader designed to bypass the free-tier restrictions of the Keep2Share (K2S) cloud storage service. It transforms a heavily throttled, single-connection download process into a multi-threaded, proxy-distributed swarm that achieves speeds comparable to premium accounts.

### What It Does

- Scrapes and validates thousands of free proxy servers.
- Automates token minting by solving K2S captchas and generating download URLs.
- Parallelizes downloads by splitting files into chunks and downloading them simultaneously through different proxies.
- Manages state atomically, allowing seamless resume after crashes, disconnects, or user cancellation.
- Optimizes resources using conservative wave-based thread scaling, first-byte-confirmed IP-Token bindings, and intelligent chunk assignment.

### Design Philosophy

1. **Stability over speed.** No duplicate proxies, no phantom connections. Every number on the dashboard is real.
2. **Confirm before committing.** A proxy-token pair is only "married" after the first byte of data arrives. Before that, tokens are freely returned.
3. **Measure, don't guess.** Speed checks only start after the first byte of data arrives, preventing false kills on slow-to-connect proxies.
4. **Unique first, race later.** Workers always claim un-attempted chunks before joining races on partially downloaded ones.
5. **Expand only when stable.** New worker waves launch only when ALL previous workers are actively downloading.

---

## 2. The Problem Domain: Keep2Share (K2S)

### What is K2S?

Keep2Share (k2s.cc) is a cloud storage and file hosting platform. Users upload files and share links. Free users can download these files, but K2S employs aggressive monetization strategies to push users toward premium subscriptions.

### How K2S Limits Free Users

| Restriction | Mechanism | Impact |
|---|---|---|
| Speed Throttle | K2S CDN limits single-connection downloads to ~30 KB/s | A 1GB file takes ~9 hours |
| Captcha Gate | Requires solving a visual captcha to generate a download key | Blocks automated downloads |
| Token Expiry | Free download keys expire after 24 hours | Must re-solve captchas daily |
| IP Binding | The generated download URL (token) is bound to the IP that requested it (up to 2 IPs max) | Cannot share tokens across many IPs |
| Concurrency Limit | A free account/IP has limited simultaneous connections | Multiple threads from one IP get blocked |
| Cooldown Timers | After generating a key, a wait timer (1-60 seconds) is enforced | Slows down token generation |

### The K2S API Flow (Free Download)

```
1. POST /api/v2/requestCaptcha
   → Returns: {"status": "success", "captcha_url": "https://...", "challenge": "..."}

2. [USER SOLVES CAPTCHA] → Returns text like "rkz4Xk"

3. POST /api/v2/getUrl
   → Payload: {"file_id": "...", "captcha_challenge": "...", "captcha_response": "..."}
   → Returns: {"status": "success", "free_download_key": "...", "time_wait": 10}

4. POST /api/v2/getUrl
   → Payload: {"file_id": "...", "free_download_key": "..."}
   → Returns: {"status": "success", "url": "https://cmb-speed.k2s.cc/..."}
   → This URL is the "token". It is bound to the requesting IP.
```

---

## 3. Bypass Strategies & Architecture

### Strategy 1: Distributed Proxy Network

**Problem:** 30 KB/s per connection.
**Solution:** Use 30+ proxies. Each proxy gets its own 30 KB/s connection.
**Result:** 30 proxies × 30 KB/s = ~900 KB/s.

### Strategy 2: Automated Token Minting

**Problem:** Captchas block automation.
**Solution:** The minter fetches the captcha image, opens it on the user's machine, and prompts for the answer. One captcha solve yields a free_download_key. That key is then used with multiple proxies to mint 100-500 download URLs (tokens) in a burst.
**Result:** 2-3 minutes of user interaction generates enough tokens for a full download.

### Strategy 3: Chunked Parallel Downloading

**Problem:** Single connection is slow and fragile.
**Solution:** Split the file into 5MB chunks. Assign each chunk to a different worker. All workers write to a pre-allocated `.part` file at their specific byte offset using `r+b` mode.
**Result:** Parallel downloading with zero file corruption.

### Strategy 4: First-Byte Confirmed IP-Token Binding

**Problem:** Tokens used from wrong IPs trigger HTTP 409 Conflict.
**Solution:** When a worker gets a proxy and token, they start "dating." Only after the first byte of data arrives is the pair "married" and the binding saved to disk (`bindings.json`). If the proxy dies before first byte, the token is returned to the pool — no waste. If married, the binding persists even across program restarts.
**Result:** Near-zero 409 errors. Tokens are only consumed by confirmed-working connections.

### Strategy 5: Intelligent Chunk Assignment

**Problem:** Multiple workers waste effort downloading the same chunk while others are untouched.
**Solution:** Every chunk tracks a `taken_count`. Workers always pick the chunk with the lowest `taken_count`. Among ties, they pick the chunk with the highest progress (partial downloads get finished first).
**Result:** 100% unique assignment when possible. Graceful, fair racing when necessary.

### Strategy 6: Conservative Wave-Based Startup

**Problem:** 50 workers launching simultaneously drains the proxy pool and wastes tokens.
**Solution:** Start 5 workers. Every 5 seconds, check: are **ALL** launched workers actively downloading? Only then launch 5 more.
**Result:** Workers only launch when previous ones have confirmed working connections. No wasted tokens on dead proxies.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          main.py                                │
│  (Orchestrator: Requirements → File Info → Mint → Download)     │
└──────────┬───────────────┬──────────────────┬───────────────────┘
           │               │                  │
           ▼               ▼                  ▼
┌─────────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  proxy_engine   │ │   minter     │ │   state_manager      │
│─────────────────│ │──────────────│ │----------------------│
│ Scraper         │ │ Captcha API  │ │ Chunk tracking       │
│ Validator       │ │ Key API      │ │ Token pool           │
│ 3-Pool System   │ │ URL API      │ │ Progress persistence │
│ Semaphore       │ │ Cooldowns    │ │ Atomic saves         │
└────────┬────────┘ └──────┬───────┘ └──────────┬───────────┘
         │                 │                     │
         │                 ▼                     │
         │          ┌──────────────┐             │
         │          │ tokens.json  │             │
         │          └──────────────┘             │
         │                                       │
         ▼                                       ▼
┌──────────────────────────────────────────────────────────────┐
│                     download_engine                          │
│──────────────────────────────────────────────────────────────│
│  Workers (Conservative waves)                              │
│  First-Byte Marriage (bindings.json)                       │
│  Token Return (unmarried tokens go back to pool)           │
│  Micro-Resumption (512KB)                                   │
│  .part File Writing (r+b mode)                              │
│  First-Byte Grace Period (no premature kills)               │
│  Response Cleanup (no memory leaks)                         │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Project Structure & File Manifest

```
K2S-final/
├── main.py                    # Entry point. Orchestrates all steps.
├── README.md                  # User-facing documentation.
├── Documentation.md           # This file. Deep technical reference.
├── requirements.txt           # pip dependencies (reference only)
│
├── src/                       # Core library modules
│   ├── proxy_engine.py        # Proxy scraping, validation, pool management
│   ├── minter.py              # Token minting via K2S API
│   ├── state_manager.py       # Chunk state, token pool, persistence
│   └── download_engine.py     # Worker threads, bindings, downloading logic
│
├── tests/                     # Test scripts for each module
│   ├── fresh_proxies.py       # Scrape and validate proxy list
│   ├── test_minter.py         # Test token minting flow
│   └── test_download.py       # Test full download with dashboard
│
└── data/                      # Runtime data (auto-created)
    ├── .requirements.json     # Lock file for installed packages
    ├── connected.txt          # Validated working proxies
    ├── unconnected.txt        # Proxies known but not yet tested
    ├── cooldowns.json         # Minter IP cooldown timestamps
    ├── tokens.json            # Unmarried token pool (cached tokens)
    ├── bindings.json          # Married IP→Token bindings (persisted)
    ├── {filename}.state.json  # Download state for resume
    └── {filename}.part        # Pre-allocated download target
```

---

## 5. Deep Dive: Core Modules (src/)

### 5.1 proxy_engine.py

**Purpose:** Provides a continuous supply of working HTTP/HTTPS/SOCKS proxies to the download engine.

**Key Concepts:**

- **Three-Pool System:**
  - `connected_set`: Proxies that passed validation at least once.
  - `unconnected_set`: Proxies scraped but not yet tested.
  - `prison_dict`: Proxies that failed validation (cooling off before re-test).
- **Semaphore:** Limits concurrent proxy validations to prevent network saturation (default: 225).
- **Proxy Affinity:** Workers hold proxies across chunks. Only discarded on failure.
- **Deduplication:** Both `connected_set` and `unconnected_set` use `(ip, int(port))` tuples. Loading from disk converts string ports to `int` to match scraper-generated pids. This prevents duplicate entries for the same proxy.
- **Deque:** `cold_list` uses `collections.deque` for O(1) `popleft()` instead of `list.pop(0)`.

**Key Methods:**

| Method | Purpose |
|---|---|
| `start()` | Loads pools from disk, starts background validator threads |
| `stop()` | Saves pools to disk, shuts down gracefully |
| `get_proxy(timeout)` | Returns `{id, url}` of a validated proxy. Blocks until available. |
| `release_proxy(proxy_id)` | Returns proxy to warm heap (6s breather, then re-validated) |
| `report_drop(proxy_id)` | Moves proxy to prison (it failed during download) |
| `get_stats()` | Returns `{validated, cold, prison}` counts for dashboard |

**How Proxies Are Validated:**

1. Proxy tries connecting to `https://k2s.cc` within 8 seconds.
2. Checks if response status is 200, 301, or 302.
3. Valid → `connected_set` + `validated_heap`. Invalid → prison with escalation timer.
4. Prison proxies re-tested after cooldown (60s, 90s, 120s, 300s escalation).
5. After max escalation (300s), proxy is demoted from connected → unconnected and re-queued to cold.

---

### 5.2 minter.py

**Purpose:** Automates the generation of K2S download tokens by interacting with the K2S API and prompting the user for captcha solves.

**API Endpoints Used:**

| Endpoint | Purpose |
|---|---|
| POST `/api/v2/requestCaptcha` | Gets captcha image URL and challenge token |
| POST `/api/v2/getUrl` | Submits captcha answer OR uses download key to get CDN URL |

**Key Methods:**

| Method | Purpose |
|---|---|
| `mint(file_id, target_tokens)` | Main flow: get captcha → solve → burst mint tokens |
| `_get_captcha()` | Calls K2S API from home IP, saves image, opens it for user |
| `_submit_captcha(proxy, challenge, answer, file_id)` | Submits answer via proxy, returns key + wait time |
| `_generate_tokens(proxy, file_id, key)` | Spawns 10 threads to burst-mint URLs from one proxy |
| `_save_cache()` | Saves tokens to `data/tokens.json` with expiry timestamps |

**Captcha Strategy:**

1. Fetch captcha from home IP (not proxy) for reliability.
2. Open image automatically using OS default viewer (`os.startfile` / `open` / `xdg-open`).
3. Prompt user in console for answer.
4. If invalid, allow 1 retry with same challenge.
5. If still invalid, fetch a new captcha (max 3 total).

**Token Burst Minting:**

1. One successful captcha → one `free_download_key`.
2. That key is used with a validated proxy to spawn 10 parallel request threads.
3. Each thread calls `getUrl` → gets a CDN URL (token).
4. Tokens are cached with 24-hour expiry in `data/tokens.json`.

**Cooldown Management:**

- K2S enforces cooldowns per IP after key generation.
- Tracked in `data/minter_cooldowns.json` as `{ip: timestamp}`.
- Minter skips proxies on cooldown.

---

### 5.3 state_manager.py

**Purpose:** Single source of truth for chunk progress, token pool, and download state. Thread-safe. Persisted to disk atomically.

**Chunk Lifecycle:**

```
PENDING → ACTIVE (assigned to worker) → COMPLETED
                ↓ (worker fails)
           ACTIVE (stays, progress saved)
                ↓ (new worker picks up)
           ACTIVE → COMPLETED
```

**Key Data Structures:**

| Structure | Type | Purpose |
|---|---|---|
| `completed_chunks` | set | Chunks fully downloaded and verified |
| `active_chunks` | dict {id: bytes} | Chunks currently being downloaded with progress |
| `assigned_chunks` | set | Chunks currently checked out by a worker |
| `chunk_taken_count` | dict {id: int} | How many times each chunk has been assigned |
| `available_tokens` | list | Tokens ready for checkout (unmarried pool) |
| `checked_out_tokens` | list | Tokens currently in use by workers |

**Key Methods:**

| Method | Purpose |
|---|---|
| `init_download(...)` | Creates fresh state for a new file |
| `load_state(filename)` | Loads state from disk for resume |
| `save_state()` | Atomic write via `.tmp` + `os.replace()` |
| `get_next_chunk()` | Returns chunk with lowest `taken_count`, then highest progress |
| `update_chunk_progress(id, bytes)` | Micro-resumption: saves progress every 512KB |
| `complete_chunk(id)` | Moves chunk to completed set |
| `release_chunk(id)` | Un-assigns chunk so another worker can pick it up |
| `checkout_token()` | Pops token from available pool |
| `return_token(url)` | Returns token to available pool (used when proxy dies before marriage) |
| `mark_token_dead(url)` | Removes token from all pools (409 error) |
| `get_progress_bytes()` | Returns total bytes on disk (completed size + active progress) |

**Chunk Assignment Algorithm (`get_next_chunk`):**

1. Build list of all chunks not in `completed_chunks`.
2. Find the minimum `taken_count` among candidates.
3. Filter to only chunks with that minimum count.
4. Among those, pick the one with the highest progress (prefer partial downloads).
5. Increment `taken_count`, add to `assigned_chunks`, return chunk ID.

**Micro-Resumption:**

- Every 512KB, the worker calls `update_chunk_progress()`.
- On crash/restart, `get_resume_byte()` returns the last saved progress.
- The worker sends `Range: bytes={resume}-{end}` to download only the missing portion.
- Result: Zero wasted bandwidth.

**Persistence:**

- Saved every 5 seconds by the download engine's monitor thread.
- Uses atomic write: write to `.tmp`, then `os.replace()` (crash-safe on all OS).
- On load, `checked_out_tokens` are returned to `available_tokens` (workers are gone after crash).
- `assigned_chunks` is cleared on load (chunks become available again).

---

### 5.4 download_engine.py

**Purpose:** Manages worker threads that download chunks, handles IP-Token bindings, monitors speed, and finalizes the file.

**Constants:**

| Constant | Value | Purpose |
|---|---|---|
| `MIN_SPEED_KBPS` | 10 | Minimum acceptable download speed |
| `SPEED_CHECK_INTERVAL` | 5 | Seconds between speed checks |
| `STALE_DATA_TIMEOUT` | 10 | Kill if no data received for 10s |
| `PROGRESS_UPDATE_BYTES` | 524288 | Save progress every 512KB |
| `RECOVERY_COOLDOWN` | 5 | Seconds to wait after proxy failure |
| `WAVE_SIZE` | 5 | Workers launched per wave |
| `WAVE_HEALTH_THRESHOLD` | 1.0 | **100%** of workers must be downloading to expand |
| `STATE_SAVE_INTERVAL` | 5 | Seconds between state saves |
| `TOKEN_EXPIRY` | 86400 | 24 hours — bindings expire after this |

**Worker Lifecycle:**

```
1. Get proxy from engine
2. Check ip_to_token binding for proxy IP
   → Found? Reuse that token (already married)
   → Not found? Checkout new token from pool (dating)
3. Get chunk from state_manager
4. Download chunk:
   → State: "connecting"
   → First byte arrives → MARRIAGE: save binding to bindings.json
   → Stream to .part file at correct offset
   → Update progress every 512KB
5. On success:
   → complete_chunk(), keep proxy + token + marriage
   → Loop for next chunk
6. On proxy failure:
   → If NOT married: return_token() to pool (no waste)
   → If married: binding stays on disk (permanent)
   → Keep chunk_id, get new proxy on next loop
7. On 409:
   → mark_token_dead(), remove binding from disk
   → Get new token + new chunk
8. On already_done:
   → release_chunk(), keep proxy + token
```

**First-Byte Marriage System:**

```
ip_to_token = {"1.2.3.4": "https://cmb-...", "5.6.7.8": "https://cmb-..."}
binding_times = {"1.2.3.4": 1716543600.0, "5.6.7.8": 1716543612.0}
```

- On proxy assignment: Check `bindings.json` first. If IP exists and not expired, reuse token.
- On first byte: Save binding to disk. Token is now "married" to this IP.
- On proxy death before first byte: Return token to pool. No binding saved. No waste.
- On proxy death after first byte: Binding stays. Token is quarantined (useless from other IPs without causing 409s).
- On 409: Remove binding. Token is dead.
- On program restart: Load bindings from disk. Expired ones (>24h) are dropped and replaced with fresh tokens.
- On finalize: Clear entire dict, delete `bindings.json`.

**Conservative Wave-Based Startup:**

1. Launch 5 workers initially.
2. Every 5 seconds, monitor checks: are **ALL** launched workers actively downloading?
3. If yes → launch 5 more. If no → wait.
4. Repeat until `thread_count` reached.
5. Why: Ensures every worker has a confirmed working connection before investing more tokens. No wasted tokens on dead proxies.

**First-Byte Grace Period:**

- Speed checks do NOT start based on wall clock time.
- They start after the first byte of data arrives and then every `SPEED_CHECK_INTERVAL` seconds.
- Why: A proxy that takes 9 seconds to connect but then downloads at 40KB/s is perfectly good.

**Pre-Allocated .part File:**

- On startup, create `{filename}.part` with exact file size.
- Uses `f.seek(size - 1); f.write(b'\0')`.
- Workers open with `r+b` mode and seek to their chunk's offset.
- Multiple workers write simultaneously without corruption (each writes to different offset).

**Memory Leak Prevention:**

- `requests.get(..., stream=True)` borrows a connection from urllib3's pool.
- If not closed, the connection leaks.
- Fix: `r = None` before try block, `finally: if r is not None: r.close()` ensures cleanup on every path.

**Finalization:**

1. Rename `{filename}.part` → `{filename}` (atomic on same filesystem).
2. Delete state file.
3. Delete `bindings.json`.
4. Clear `ip_to_token` dict.
5. Print completion message with elapsed time.

---

## 6. The Orchestrator: main.py

**Purpose:** Single entry point. Handles requirements, gathers user input, orchestrates all modules, displays dashboard.

**Execution Flow:**

```
[1/5] Requirements
  → Check .requirements.json lock file
  → If missing: check each package, install if needed, save lock
  → Packages: requests, rich, Pillow, beautifulsoup4

[2/5] File Info
  → Prompt for File ID
  → Fetch name + size from K2S API

[3/5] Proxy Check
  → Start ProxyEngine
  → Wait up to 60 seconds for scraper (fresh start has no cached data)
  → If still 0 proxies → check internet connection, exit

[4/5] Token Check
  → Check tokens.json for cached tokens
  → If < 250 tokens → launch Minter inline
  → User solves captchas, minter generates tokens

[5/5] Download
  → Init StateManager (resume or fresh)
  → Load bindings.json from disk (married tokens)
  → Filter married tokens out of unmarried pool
  → Setup DownloadEngine (pre-allocate .part file)
  → Start download in background thread
  → Main thread: dashboard loop (1 refresh/second)
  → On completion: show final stats + elapsed time
```

**Dashboard Format:**

```
Overall: 48.66% █████████░░░░░░░░░░░ 974848KB / 2003544KB [167/392]  |  Speed: 698.5KB/s  |  Elapsed: 00:21:37  |  ETA: 00:24:32
Tokens: 1253  |  Bindings: 23  |  Active: 24  |  Waiting: 1  |  Disconnected: 5
Proxies: Validated: 312  |  Cold: 8420  |  Prison: 87

W00 : Chunk 258 |      1536KB / 5120KB |    31.45KB/s | Downloading (32s) (resumed 512KB)
W01 : Chunk --- |                  --- |     0.00KB/s | Disconnected (2s)
```

**Cancellation Handling:**

- Ctrl+C during minting → stops minter, stops engine, exits cleanly.
- Ctrl+C during download → calls `dl.stop()` (saves state), joins threads with timeout, exits cleanly.
- All wrapped in try/except at top level to catch unexpected errors.

**Fresh Start Handling:**

- On a fresh start (no `data/` folder), main.py waits up to 60 seconds for the scraper to find proxies instead of immediately exiting.
- No need to run `fresh_proxies.py` separately.

---

## 7. Testing & Inference (tests/)

### 7.1 fresh_proxies.py

**Purpose:** Standalone script to scrape proxy lists and validate them before running the main downloader.

**What It Does:**

1. Scrapes multiple free proxy list websites.
2. Deduplicates and cleans proxy URLs.
3. Validates each proxy against K2S.
4. Saves working proxies to `data/connected.txt`.

**Inference from Testing:**

- ~30,000 raw proxies scraped → ~700 validated on first pass.
- Proxy health degrades rapidly. A proxy validated 10 minutes ago may be dead now.
- Conclusion: The proxy engine must continuously re-validate in the background, not rely on a single upfront check.

### 7.2 test_minter.py

**Purpose:** Test the token minting pipeline in isolation.

**Inference from Testing:**

- Invalid captcha handling: K2S returns `{"status": "error", "message": "Invalid captcha"}`. We allow 1 retry with same challenge, then fetch new captcha. Max 3 captchas total.
- Key reuse: One `free_download_key` can generate 100-500 tokens through different proxies before the key expires or rate-limits.
- Proxy exhaustion: Minting 500 tokens burns through ~5-10 proxies. Need at least 20 validated proxies for a successful mint.
- Cooldown tracking: Without it, we waste time hitting rate-limited proxies.

### 7.3 test_download.py

**Purpose:** Test the full download engine with a live dashboard.

**Inference from Testing — Bugs Found and Fixed:**

| Bug | Symptom | Root Cause | Fix |
|---|---|---|---|
| 112% Progress | Progress exceeded 100% | `get_progress_bytes()` summed absolute byte positions instead of chunk sizes | Changed to `end - start` per chunk |
| All workers on same chunk | Every worker showed "Chunk 0" | No `assigned_chunks` tracking | Added `assigned_chunks` set |
| Last-minute racing chaos | 4 workers on chunk 203 | No priority system | Implemented `chunk_taken_count` |
| Proxy death wasting tokens | Token quarantined forever on dead IP | Permanent binding even before confirmation | First-byte marriage: unmarried tokens returned to pool |
| Port type mismatch | Same proxy appearing twice (111k cold) | Disk loaded `("1.2.3.4", "8080")` vs scraper `("1.2.3.4", 8080)` | All ports stored as `int` everywhere |
| Memory leak | Memory grew over time | `stream=True` responses never closed | Added `finally: if r is not None: r.close()` |
| Workers don't stop | Process hung after 100% | Workers never checked completion | Workers check `is_running` flag |

**Performance Observations:**

| Metric | Value | Notes |
|---|---|---|
| Per-worker speed | ~30 KB/s | K2S hard limit per connection |
| Total speed (stable) | ~500-900 KB/s | Depends on proxy quality and count |
| Tokens consumed per download | ~30-50 | First-byte marriage saves unused tokens |
| Tokens minted per captcha | ~100-250 | Depends on proxy quality |
| Time to download 1GB | ~20-30 minutes | Versus ~9 hours single-threaded |

---

## 8. Data Management & Persistence

**Directory:** `data/`  
Auto-created on first run. All runtime data lives here.

### Files

| File | Created By | Format | Purpose |
|---|---|---|---|
| `.requirements.json` | main.py | JSON | Lock file: `{package: version}`. Skips pip checks if valid. |
| `connected.txt` | proxy_engine.py | Text, 1 per line | Previously validated proxies |
| `unconnected.txt` | proxy_engine.py | Text, 1 per line | Known but untested proxies |
| `cooldowns.json` | minter.py | JSON | `{ip: timestamp}` for K2S rate-limit cooldowns |
| `tokens.json` | minter.py | JSON | `{file_id: {tokens: [{url, mint_time, expiry}]}}` — **unmarried** token pool |
| `bindings.json` | download_engine.py | JSON | `{ip: {url, bound_time}}` — **married** IP→Token bindings |
| `{name}.state.json` | state_manager.py | JSON | Chunk progress, active chunks, token pool for resume |
| `{name}.part` | download_engine.py | Binary | Pre-allocated file. Workers write at offsets. Renamed to final on completion. |

### Bindings File Schema (`data/bindings.json`)

```json
{
  "1.2.3.4": {
    "url": "https://cmb-speed.k2s.cc/...",
    "bound_time": 1716543600.0
  },
  "5.6.7.8": {
    "url": "https://cmb-speed.k2s.cc/...",
    "bound_time": 1716543612.0
  }
}
```

- `bound_time`: Unix timestamp when the first byte confirmed the marriage.
- On load: bindings older than 24 hours are dropped. Workers get fresh tokens for those IPs.

### State File Schema (`{name}.state.json`)

```json
{
  "file_id": "4d0c30562bcb9",
  "file_name": "movie.mp4",
  "file_size": 1065353216,
  "chunk_size": 5242880,
  "total_chunks": 204,
  "completed_chunks": [0, 1, 4, 5, 12],
  "active_chunks": {
    "2": 3800000,
    "3": 0
  },
  "chunk_taken_count": {
    "0": 1, "1": 1, "2": 3, "3": 2
  },
  "token_pool": {
    "available": ["https://cmb-...", "https://cmb-..."],
    "checked_out": ["https://cmb-..."]
  }
}
```

### Atomic Write Pattern

Used by `state_manager.py`, `minter.py`, and `download_engine.py`:

```python
tmp_path = target_path + ".tmp"
with open(tmp_path, "w") as f:
    json.dump(data, f, indent=2)
os.replace(tmp_path, target_path)
```

`os.replace()` is atomic on POSIX and nearly atomic on Windows (within same drive). A crash mid-write leaves either the old file intact or the new file complete. Never a corrupted half-file.

### Cleanup

| Event | What Gets Cleaned |
|---|---|
| Download completes | `.state.json` deleted, `.part` renamed to final filename, `bindings.json` deleted, `ip_to_token` dict cleared |
| Proxy engine stops | `connected.txt` + `unconnected.txt` saved (warm start next time) |
| Minter finishes | `tokens.json` updated, `cooldowns.json` saved |

---

## 9. Requirements & Dependencies

### Required Packages

| Package | Version | Import Name | Purpose |
|---|---|---|---|
| requests | ≥2.31.0 | requests | HTTP client for K2S API, chunk downloading |
| rich | ≥13.0.0 | rich | Future: enhanced terminal formatting |
| Pillow | ≥10.0.0 | PIL | Captcha image processing/display |
| beautifulsoup4 | latest | bs4 | HTML parsing for proxy scraping |

### Standard Library Usage

No external packages are used for:

- Threading (`threading`)
- JSON parsing (`json`)
- File operations (`os`, `shutil`)
- Time tracking (`time`)
- Process management (`subprocess`)

This minimizes dependency count and installation failures.
