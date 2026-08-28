import sys
import os
import time
import re
import requests
import urllib3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from proxy_engine import ProxyEngine
from minter import Minter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_file_name(file_id):
    try:
        r = requests.post("https://k2s.cc/api/v2/getFilesInfo", json={"ids": [file_id]}, timeout=10)
        if r.status_code == 200:
            file_info = r.json()['files'][0]
            name = file_info['name']
            size = int(file_info['size'])
            size_mb = size / (1024 * 1024)
            return f"{name} ({size_mb:.1f} MB)"
    except:
        pass
    return None

if __name__ == "__main__":
    file_id = "3d87e69169aa5"
    print("File Id : ", file_id)
    if not file_id:
        print("No file_id provided. Exiting.")
        sys.exit(1)

    file_name = get_file_name(file_id)
    if file_name:
        print(f"File: {file_name}")
    else:
        print(f"File: (could not fetch name)")

    target = input("Target tokens (default 100): ").strip()
    target_tokens = int(target) if target else 100

    engine = ProxyEngine()
    engine.start()

    minter = Minter(engine)

    try:
        minter.mint(file_id, target_tokens)
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Stopping...")

    engine.stop()