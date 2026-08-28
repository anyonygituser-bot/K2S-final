import sys
import os
import time
import urllib3

# Point to the src folder (one directory up)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from proxy_engine import ProxyEngine

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if __name__ == "__main__":
    engine = ProxyEngine()
    engine.start()

    start_time = time.time()
    was_ready = False

    try:
        while True:
            stats = engine.get_stats()
            elapsed = time.time() - start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)

            if stats['is_ready'] and not was_ready:
                print(f"\n  >>> READY THRESHOLD REACHED ({stats['validated']} validated) <<<")
                was_ready = True

            print(
                f"\r  [{mins:02d}:{secs:02d}]  "
                f"Validated: {stats['validated']:>3}  |  "
                f"Ready: {'✓' if stats['is_ready'] else '✗'}  |  "
                f"Warm: {stats['warm']:>3}  |  "
                f"Prison: {stats['prison']:>3}  |  "
                f"Cold: {stats['cold']:>4}  |  "
                f"Active: {stats['active']:>3}  |  "
                f"Connected: {stats['connected']:>4}  |  "
                f"Unconnected: {stats['unconnected']:>5}   ",
                end="", flush=True
            )
            time.sleep(1)

    except KeyboardInterrupt:
        engine.stop()