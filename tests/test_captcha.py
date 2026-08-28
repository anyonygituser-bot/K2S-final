import requests
import os
import subprocess
import platform
import urllib3
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

K2S_API = "https://k2s.cc/api/v2"
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def find_working_proxy():
    print("[0] Fetching proxy list...")
    try:
        r = requests.get(
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all",
            timeout=10
        )
        proxies = [f"http://{line.strip()}" for line in r.text.splitlines() if line.strip()]
    except Exception as e:
        print(f"    Failed to fetch proxy list: {e}")
        return None

    print(f"    Found {len(proxies)} proxies. Testing for K2S reachability...")

    def test_proxy(proxy_url):
        try:
            r = requests.head(
                "https://k2s.cc",
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=5,
                verify=False,
                headers=API_HEADERS
            )
            if r.status_code in (200, 301, 302):
                return proxy_url
        except:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(test_proxy, p): p for p in proxies[:150]}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                print(f"    Found working proxy: {result}")
                return result

    print("    No working proxies found.")
    return None


def open_image(url):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        filepath = os.path.join(DATA_DIR, "captcha.jpeg")
        r = requests.get(url, timeout=10, verify=True)
        with open(filepath, "wb") as f:
            f.write(r.content)
        if platform.system() == 'Windows':
            os.startfile(filepath)
    except Exception as e:
        print(f"    Could not open image: {e}")


if __name__ == "__main__":
    file_id = input("File ID: ").strip()

    # Step 0: Find a working proxy automatically
    proxy_url = find_working_proxy()
    if not proxy_url:
        print("Cannot continue without a working proxy.")
        exit(1)

    proxy_dict = {"http": proxy_url, "https": proxy_url}

    # Step 1: Request captcha
    print("\n[1] Requesting captcha from Home IP...")
    r = requests.post(f"{K2S_API}/requestCaptcha", proxies=None, timeout=10, verify=True, headers=API_HEADERS)
    print(f"    Status: {r.status_code}")
    print(f"    Response: {r.json()}")

    data = r.json()
    challenge = data.get('challenge')
    captcha_url = data.get('captcha_url')

    # Step 2: Show image, get answer
    open_image(captcha_url)
    answer = input("\n[2] Enter captcha (type WRONG answer on purpose): ").strip()

    # Step 3: Submit through proxy
    payload = {
        "file_id": file_id,
        "captcha_challenge": challenge,
        "captcha_response": answer
    }

    print(f"\n[3] Submitting through proxy {proxy_url}...")
    print(f"    Payload: {payload}")

    try:
        r = requests.post(f"{K2S_API}/getUrl", json=payload, proxies=proxy_dict, timeout=15,
                          verify=False, headers=API_HEADERS)
        print(f"    Status: {r.status_code}")
        print(f"    Headers: {dict(r.headers)}")
        try:
            print(f"    JSON: {r.json()}")
        except:
            print(f"    Body: {r.text}")
    except Exception as e:
        print(f"    Error: {type(e).__name__}: {e}")