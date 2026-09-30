"""Send rows from a CSV to the facade, to generate serving logs. Usage: send_traffic.py data.csv [n]"""
import sys

import httpx
import pandas as pd

from src.make_data import FEATURES

path, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 500
url = "http://localhost:8080/recommend"
rows = pd.read_csv(path).sample(n, random_state=0)[FEATURES].to_dict("records")
with httpx.Client(timeout=5) as c:
    bad = sum(c.post(url, json=r).status_code != 200 for r in rows)
print(f"sent {n} requests, {bad} failed")
sys.exit(1 if bad else 0)
