import json
import os
import threading
import time

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


class StateManager:
    def __init__(self):
        self.lock = threading.Lock()

        # File metadata
        self.file_id = None
        self.file_name = None
        self.file_size = 0
        self.chunk_size = 0
        self.total_chunks = 0

        # Chunk state
        self.completed_chunks = set()
        self.active_chunks = {}  # chunk_id -> bytes_downloaded
        self.assigned_chunks = set()  # chunks currently being worked on
        self.chunk_taken_count = {}  # chunk_id -> how many times assigned

        # Token pool
        self.available_tokens = []
        self.checked_out_tokens = []

        # Persistence
        self.state_file = None

    # ════════════════ SETUP & PERSISTENCE ════════════════

    def init_download(self, file_id, file_name, file_size, chunk_size):
        """Create fresh state for a new download."""
        os.makedirs(_DATA_DIR, exist_ok=True)

        self.file_id = file_id
        self.file_name = file_name
        self.file_size = file_size
        self.chunk_size = chunk_size
        self.total_chunks = (file_size + chunk_size - 1) // chunk_size
        self.state_file = os.path.join(_DATA_DIR, file_name + ".state.json")

        self.completed_chunks = set()
        self.active_chunks = {}
        self.assigned_chunks = set()
        self.chunk_taken_count = {}
        self.available_tokens = []
        self.checked_out_tokens = []

    def load_state(self, file_name):
        """Load existing state. Returns True if state found and loaded."""
        os.makedirs(_DATA_DIR, exist_ok=True)
        self.state_file = os.path.join(_DATA_DIR, file_name + ".state.json")

        if not os.path.exists(self.state_file):
            return False

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)

            self.file_id = data.get("file_id")
            self.file_name = data.get("file_name")
            self.file_size = data.get("file_size", 0)
            self.chunk_size = data.get("chunk_size", 0)
            self.total_chunks = data.get("total_chunks", 0)

            self.completed_chunks = set(data.get("completed_chunks", []))
            self.active_chunks = {int(k): v for k, v in data.get("active_chunks", {}).items()}
            self.chunk_taken_count = {int(k): v for k, v in data.get("chunk_taken_count", {}).items()}

            # Assigned chunks are lost on crash — they become available again
            self.assigned_chunks = set()

            pool = data.get("token_pool", {})
            self.available_tokens = pool.get("available", [])
            self.checked_out_tokens = pool.get("checked_out", [])

            # Checked out tokens are lost on crash. Return them to available.
            if self.checked_out_tokens:
                self.available_tokens.extend(self.checked_out_tokens)
                self.checked_out_tokens = []

            return True
        except Exception as e:
            print(f"[State] Error loading state: {e}")
            return False

    def save_state(self):
        """Atomic save to disk."""
        if not self.state_file:
            return

        with self.lock:
            data = {
                "file_id": self.file_id,
                "file_name": self.file_name,
                "file_size": self.file_size,
                "chunk_size": self.chunk_size,
                "total_chunks": self.total_chunks,
                "completed_chunks": list(self.completed_chunks),
                "active_chunks": {str(k): v for k, v in self.active_chunks.items()},
                "chunk_taken_count": {str(k): v for k, v in self.chunk_taken_count.items()},
                "token_pool": {
                    "available": self.available_tokens,
                    "checked_out": self.checked_out_tokens
                }
            }

        tmp_path = self.state_file + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.state_file)
        except Exception as e:
            print(f"[State] Save error: {e}")

    def delete_state(self):
        """Remove state file after successful download."""
        if self.state_file and os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
            except Exception:
                pass

    # ════════════════ CHUNK MANAGEMENT ════════════════

    def get_next_chunk(self):
        """Get next chunk. Lowest taken_count first, highest progress within same count."""
        with self.lock:
            # Build candidate list (not completed)
            candidates = {}
            for cid in range(self.total_chunks):
                if cid not in self.completed_chunks:
                    count = self.chunk_taken_count.get(cid, 0)
                    progress = self.active_chunks.get(cid, 0)
                    candidates[cid] = (count, progress)

            if not candidates:
                return None

            # Find minimum taken count
            min_count = min(v[0] for v in candidates.values())

            # Filter to only those with min_count
            min_candidates = [cid for cid, (cnt, _) in candidates.items() if cnt == min_count]

            # Among min_candidates, pick the one with highest progress
            best_cid = max(min_candidates, key=lambda cid: candidates[cid][1])

            # Increment taken count
            self.chunk_taken_count[best_cid] = self.chunk_taken_count.get(best_cid, 0) + 1

            # Mark as assigned
            self.assigned_chunks.add(best_cid)

            # Ensure it's in active_chunks
            if best_cid not in self.active_chunks:
                self.active_chunks[best_cid] = 0

            return best_cid

    def get_resume_byte(self, chunk_id):
        """How far did this chunk get before crash/disconnect?"""
        with self.lock:
            return self.active_chunks.get(chunk_id, 0)

    def update_chunk_progress(self, chunk_id, bytes_downloaded):
        """Update bytes downloaded for an active chunk (micro-resumption)."""
        with self.lock:
            if chunk_id in self.active_chunks:
                self.active_chunks[chunk_id] = bytes_downloaded

    def complete_chunk(self, chunk_id):
        """Mark chunk as complete."""
        with self.lock:
            self.completed_chunks.add(chunk_id)
            self.active_chunks.pop(chunk_id, None)
            self.assigned_chunks.discard(chunk_id)

    def release_chunk(self, chunk_id):
        """Worker gave up. Un-assign so another worker can pick it up."""
        with self.lock:
            self.assigned_chunks.discard(chunk_id)

    def is_download_complete(self):
        """Are all chunks done?"""
        with self.lock:
            return len(self.completed_chunks) == self.total_chunks

    def get_chunk_offset(self, chunk_id):
        """Get start and end byte offset for a chunk."""
        start = chunk_id * self.chunk_size
        end = min((chunk_id + 1) * self.chunk_size, self.file_size)
        return start, end

    def get_progress_bytes(self):
        """Total bytes downloaded (completed chunks + active progress)."""
        with self.lock:
            completed_bytes = 0
            for cid in self.completed_chunks:
                start, end = self.get_chunk_offset(cid)
                completed_bytes += (end - start)

            active_bytes = sum(self.active_chunks.values())
            return completed_bytes + active_bytes

    def get_progress_chunks(self):
        """Return (completed_count, total_count)."""
        with self.lock:
            return len(self.completed_chunks), self.total_chunks

    # ════════════════ TOKEN MANAGEMENT ════════════════

    def add_tokens(self, token_list):
        """Add minted tokens to the pool."""
        with self.lock:
            for token in token_list:
                if token not in self.available_tokens and token not in self.checked_out_tokens:
                    self.available_tokens.append(token)

    def checkout_token(self):
        """Pop an available token. Returns None if empty."""
        with self.lock:
            if self.available_tokens:
                token = self.available_tokens.pop(0)
                self.checked_out_tokens.append(token)
                return token
            return None

    def return_token(self, token_url):
        """Worker finished. Token goes back to available."""
        with self.lock:
            if token_url in self.checked_out_tokens:
                self.checked_out_tokens.remove(token_url)
            self.available_tokens.append(token_url)

    def mark_token_dead(self, token_url):
        """Remove a dead/expired token."""
        with self.lock:
            if token_url in self.available_tokens:
                self.available_tokens.remove(token_url)
            if token_url in self.checked_out_tokens:
                self.checked_out_tokens.remove(token_url)

    def tokens_available(self):
        """How many tokens are ready to use?"""
        with self.lock:
            return len(self.available_tokens)