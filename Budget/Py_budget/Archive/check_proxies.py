import threading
import queue
import requests

q = queue.Queue()
valid_proxies = []

with open("proxy_list.txt", "r") as f:
    proxies = f.read().split("\n")
    for p in proxies:
        q.put(p)


def check_proxy():
    global q
    while not q.empty():
        proxy = q.get()
        try:
            response = requests.get("https://www.google.com", proxies={"https": proxy}, timeout=5)
            if response.status_code == 200:
                print(proxy)
        except:
            continue

for _ in range(10):
    threading.Thread(target=check_proxy).start()



