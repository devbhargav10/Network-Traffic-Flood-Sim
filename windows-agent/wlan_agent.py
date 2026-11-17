"""Bounded Windows WLAN traffic agent. Uses the host's normal network stack."""
from __future__ import annotations
import asyncio, ipaddress, json, os, platform, socket, time, uuid
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

API = os.getenv("SIM_CONTROLLER_URL", "http://127.0.0.1:8010").rstrip("/")
KEY = os.getenv("SIM_API_KEY", "")
AGENT_ID = os.getenv("SIM_AGENT_ID", platform.node() + "-" + str(uuid.getnode()))
CONFIG = os.getenv("SIM_AGENT_CONFIG", "agent-config.json")
MAX_WORKERS, MAX_SECONDS, MAX_PPS, MAX_EVENTS = 50, 10, 50, 500

def load_receiver():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    ip = ipaddress.ip_address(cfg["receiver_ip"])
    if ip.version != 4 or not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        raise ValueError("receiver_ip must be an explicitly authorized private IPv4 address")
    blocked = {ipaddress.ip_address(x) for x in ("10.6.1.55", "10.6.1.94", "10.5.1.1")}
    if ip in blocked:
        raise ValueError("Refusing known WLC, SNA collector, or gateway address")
    if cfg.get("authorization") != "AUTHORIZED_TEST_RECEIVER_NOT_WLC":
        raise ValueError("Set authorization to AUTHORIZED_TEST_RECEIVER_NOT_WLC after verifying the receiver")
    port = int(cfg.get("receiver_port", 19055))
    if port != 19055:
        raise ValueError("Receiver port is fixed at UDP 19055; do not use the NetFlow export port")
    return str(ip), port

def api(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, method=method,
                  headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    with urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode())

async def run_job(job, destination):
    workers, duration = int(job["workers"]), int(job["duration_seconds"])
    rate, budget = workers, workers * duration
    if not 1 <= workers <= MAX_WORKERS or not 1 <= duration <= MAX_SECONDS or rate > MAX_PPS or budget > MAX_EVENTS:
        raise ValueError("Controller job exceeded hard-coded safety limits")
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    sent = 0
    tasks = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    start, deadline = loop.time(), loop.time() + duration
    controller_state = "RUNNING"
    try:
        async def worker(worker_id):
            nonlocal sent
            for seq in range(1, duration + 1):
                due = start + (seq - 1) + (worker_id - 1) / workers
                delay = due - loop.time()
                if delay > 0:
                    try: await asyncio.wait_for(stop.wait(), timeout=delay)
                    except asyncio.TimeoutError: pass
                if stop.is_set() or loop.time() >= deadline: return
                frame = json.dumps({"experiment_id": job["id"], "worker_id": worker_id,
                                    "sequence": seq, "agent_id": AGENT_ID},
                                   separators=(",", ":")).encode()
                await loop.sock_sendto(sock, frame, destination)
                sent += 1
        tasks = [asyncio.create_task(worker(i)) for i in range(1, workers + 1)]
        while any(not t.done() for t in tasks):
            state = api("GET", "/api/v1/agent/jobs/" + job["id"])
            if state["status"] in ("STOP_REQUESTED", "INTERRUPTED", "CANCELLED"):
                controller_state = state["status"]
                stop.set()
                break
            if loop.time() >= deadline:
                break
            await asyncio.sleep(0.25)
        if stop.is_set():
            for t in tasks: t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        final = "STOPPED" if stop.is_set() else "COMPLETED"
        if controller_state != "INTERRUPTED":
            api("POST", "/api/v1/agent/jobs/" + job["id"] + "/report",
                {"sent": sent, "received": 0, "status": final,
                 "stop_reason": "operator_stop" if stop.is_set() else "duration_elapsed"})
        print(json.dumps({"job": job["id"], "status": final, "sent": sent,
                          "receiver": destination[0] + ":" + str(destination[1])}))
    except Exception:
        stop.set()
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            api("POST", "/api/v1/agent/jobs/" + job["id"] + "/report",
                {"sent": sent, "received": 0, "status": "FAILED", "stop_reason": "agent_or_controller_error"})
        except Exception:
            pass
        raise
    finally:
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        sock.close()

async def main():
    if len(KEY) < 32:
        raise SystemExit("Set SIM_API_KEY to the same 32+ character key used by the controller.")
    destination = load_receiver()
    print("Windows WLAN agent", AGENT_ID, "->", destination, "(50 logical workers max)")
    while True:
        try:
            result = api("GET", "/api/v1/agent/next?agent_id=" + AGENT_ID)
            job = result.get("job")
            if job:
                await run_job(job, destination)
            else:
                await asyncio.sleep(1)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            print("Agent error:", type(exc).__name__, str(exc))
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
