"""Small UDP sink for an isolated, authorized WLAN test VLAN."""
import argparse, json, socket, time
from collections import defaultdict

p = argparse.ArgumentParser()
p.add_argument("--bind", default="0.0.0.0")
p.add_argument("--port", type=int, default=19055)
args = p.parse_args()
if not 1024 <= args.port <= 65535:
    raise SystemExit("Port must be 1024..65535")
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((args.bind, args.port))
counts = defaultdict(int)
print(f"UDP test receiver listening on {args.bind}:{args.port}")
while True:
    data, addr = sock.recvfrom(512)
    if len(data) > 256:
        continue
    try:
        frame = json.loads(data.decode())
        exp, worker, seq = str(frame["experiment_id"]), int(frame["worker_id"]), int(frame["sequence"])
        if not 1 <= worker <= 50 or not 1 <= seq <= 10:
            continue
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        continue
    key = (exp, addr[0])
    counts[key] += 1
    print(json.dumps({"time": time.time(), "experiment_id": exp, "worker_id": worker,
                      "sequence": seq, "source_ip": addr[0], "source_port": addr[1],
                      "received_for_experiment_from_source": counts[key]}), flush=True)
