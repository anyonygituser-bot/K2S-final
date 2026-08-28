# K2S Downloader

A parallel, proxy-swarming downloader that bypasses Keep2Share (K2S) free-tier speed limits. Turns a 9-hour single-connection crawl into a ~20-minute parallel download.

---

### The Rule

This is open source. No limits. Use it, share it, dismantle it, add to it, subtract from it. Use it for parts to build something completely different. The only ask: **if you make it better, share it with others too.**

---

## For the Casual User: How to Use

### What You Need

- A computer with **Python 3.8+** installed.
- A terminal / command prompt.
- An internet connection.
- A K2S file link (e.g., `https://k2s.cc/file/4d0c302353422`).

### Step 1: Start the Downloader

```
python main.py
```

That's it. The downloader scrapes proxies, validates them, and starts downloading — all in one command. On a fresh start, it waits ~30 seconds for the scraper before proceeding.

### Step 2: Enter the File ID

It will ask for a File ID. Take your K2S link and paste just the ID part:

```
File ID: 4d0c302353422
```

It will fetch the file name and size automatically.

### Step 3: Solve the Captcha

If you don't have enough cached tokens, the minter will start. An image will pop up on your screen. Type the text you see in the terminal and press Enter. You might need to do this 2-3 times. This generates the download keys.

### Step 4: Watch It Download

The dashboard will appear:

```
Overall: 48.66% █████████░░░░░░░░░░░ 974848KB / 2003544KB [167/392]  |  Speed: 698.5KB/s  |  Elapsed: 00:21:37  |  ETA: 00:24:32
Tokens: 1253  |  Bindings: 23  |  Active: 24  |  Waiting: 1  |  Disconnected: 5
Proxies: Validated: 312  |  Cold: 8420  |  Prison: 87
```

Go get coffee. It will finish on its own. The final file appears in the `data/` folder.

### If It Gets Interrupted

Press `Ctrl+C`, close the terminal, lose power — doesn't matter. Just run `python main.py` again with the same File ID. It picks up exactly where it left off. Proxy state, download progress, and IP-Token bindings are all saved to disk.

---

## For the Programmer: How It Works & How to Dismantle It

The system is built in layers. Every layer is independent. You can rip any piece out, replace it, or use it standalone.

### The Layers

```
main.py          → The glue. Orchestrates everything. Start here to trace the flow.
  │
  ├── proxy_engine.py  → The blood supply. Finds and manages proxies.
  ├── minter.py        → The key maker. Talks to K2S API, handles captchas, mints tokens.
  ├── state_manager.py → The memory. Tracks chunks, progress, tokens. Saves to disk.
  └── download_engine.py → The muscle. Worker threads, bindings, file I/O, speed control.
```

### How to Take It Apart

**Want to use your own proxy source?**
Throw away `proxy_engine.py`. Replace it with anything that provides a `get_proxy()` method returning `{"id": "...", "url": "http://ip:port"}` and a `report_drop(id)` method. The rest won't notice.

**Want to automate the captcha?**
Open `minter.py`. Replace `_get_captcha()` and `_submit_captcha()` with an OCR solver or API call. Everything downstream expects a list of token URLs.

**Want to add a web UI?**
`main.py` and the dashboard loop are cleanly separated. Replace `format_dashboard()` and the `while dl_thread.is_alive()` loop with a Flask/FastAPI server that reads `dl.get_full_stats()`.

**Want to download from a different site?**
Keep `proxy_engine.py`, `state_manager.py`, and `download_engine.py`. Replace `minter.py` with whatever generates download URLs for your target site. The chunking, proxy rotation, and resume logic are site-agnostic.

**Want to use a database instead of JSON files?**
Replace `state_manager.py`. Implement the same methods (`get_next_chunk`, `complete_chunk`, `checkout_token`, etc.) but back it with SQLite, Redis, or whatever you want.

### Core Concepts to Understand

1. **First-Byte Marriage:** A proxy-token pair starts as "dating." Only after the first byte arrives are they "married" and saved to disk. If the proxy dies before first byte, the token goes back to the pool. Zero waste.

2. **Conservative Wave Expansion:** Workers launch in waves of 5. The next wave only fires when **ALL** previous workers are actively downloading. No tokens wasted on dead proxies.

3. **Bindings Persistence:** Married pairs are saved to `bindings.json`. On restart, the program reloads them. Expired bindings (>24h) are automatically replaced with fresh tokens.

4. **Intelligent Chunk Assignment:** Every chunk tracks how many times it was assigned. Workers always pick the least-attempted chunk. Ties broken by highest progress.

5. **Micro-Resumption:** Workers save progress every 512KB. On disconnect, the next worker resumes from the exact byte.

6. **Proxy Deduplication:** All proxy IDs use `(ip, int(port))` tuples. Loading from disk converts string ports to `int`. Same proxy never appears twice.

---

## For the Improver: Making It Better

Here is what wasn't built. Low-hanging fruit you could pick:

### Automation

- **OCR the captcha.** The minter already isolates the image. Plug in a vision model and remove the human entirely.
- **Auto-retry minting.** If tokens run out mid-download, pause workers, mint more, resume.

### Smarter Downloading

- **2-IP token binding.** K2S allows 2 IPs per token. We use 1. Using 2 would halve token consumption.
- **Priority chunks.** Download chunks sequentially so the file can be previewed while still downloading.

### Better Proxies

- **Paid proxy API integration.** Replace the scraper with a reliable proxy provider. Speed and stability would jump dramatically.
- **Proxy health scoring.** Track how many bytes each proxy delivered. Prefer proven proxies.

### Better UI

- **Rich terminal UI.** The `rich` package is already in requirements but unused. Build a proper TUI with progress bars and live charts.
- **Web dashboard.** Flask + WebSocket pushing stats to a browser.

### Architecture

- **Multi-file queue.** Feed it a list of file IDs. Download them one after another.
- **Distributed workers.** Run proxy engine on one machine, download workers on multiple machines, all writing to a shared NAS.

---

## Project Structure

```
K2S-final/
├── main.py                 # Run this to start everything
├── requirements.txt        # pip dependencies
├── README.md               # You are here
├── Documentation.md        # Deep technical reference
├── .gitignore
│
├── src/                    # Core modules
│   ├── proxy_engine.py     # Proxy scraping, validation, pool management
│   ├── minter.py           # Token minting via K2S API
│   ├── state_manager.py    # Chunk state, token pool, persistence
│   └── download_engine.py  # Worker threads, bindings, downloading
│
├── tests/                  # Standalone tools
│   ├── fresh_proxies.py    # Scrape and validate proxies
│   ├── test_minter.py      # Test token minting
│   └── test_download.py    # Test full download with dashboard
│
└── data/                   # Auto-created at runtime
    ├── .requirements.json  # Package lock file
    ├── connected.txt       # Previously validated proxies
    ├── unconnected.txt     # Known but untested proxies
    ├── cooldowns.json      # Minter IP cooldowns
    ├── tokens.json         # Unmarried token pool
    ├── bindings.json       # Married IP→Token bindings
    ├── *.state.json        # Download state (for resume)
    └── *.part              # Download in progress
```

---
_Built May 2026. Stable. Tested. Real numbers only._
