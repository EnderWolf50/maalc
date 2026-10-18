"""maafw.log -> events.json, the touch events the `evidence-annotate` skill draws.

  python tools/live/maafw_events.py maafw.log [more.log ...] -o events.json [--device-width 1920]

Two sources, both in the log's own wall-clock time:
  - AgentClient controller calls (game space 1280x720): click -> tap, swipe -> swipe (x2, y2, ms),
    touch_down/touch_up -> down/up (an up carries the last point the contact reached);
  - MuMuPlayerExtras touch_down/touch_up, which also see presses the pipeline made on its own
    (device pixels, scaled to 1280x720): a press no agent call explains becomes a tap, ms = how long it was held.
"""
import argparse
import json
import re
import sys
from pathlib import Path

TS = re.compile(r"^\[\d{4}-\d\d-\d\d (\d\d):(\d\d):(\d\d\.\d+)\]")
AGENT = re.compile(r"AgentClient::handle_controller_post_(click|swipe|touch_down|touch_move|touch_up)\] \[req=(\{[^}]*\})")
MUMU = re.compile(r"MuMuPlayerExtras::touch_(down|up)\] \[contact=(\d+)\](?: \[x=(\d+)\] \[y=(\d+)\])?")
SPACE = [1280, 720]


def seconds(m: re.Match) -> float:
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def clock(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def parse(lines, device_width: int = 1920) -> dict:
    scale = SPACE[0] / device_width
    events, last, mumu, open_m = [], {}, [], {}
    for line in lines:
        m = TS.match(line)
        if not m:
            continue
        t = seconds(m)
        if a := AGENT.search(line):
            kind, req = a[1], json.loads(a[2])
            c = req.get("contact", 0)
            if kind in ("click", "touch_down"):
                last[c] = (req["x"], req["y"])
                events.append({"t": t, "kind": "tap" if kind == "click" else "down", "x": req["x"], "y": req["y"]})
            elif kind == "swipe":
                events.append({"t": t, "kind": "swipe", "x": req["x1"], "y": req["y1"], "x2": req["x2"], "y2": req["y2"],
                               "ms": req.get("duration", 200)})
            elif kind == "touch_move":
                last[c] = (req["x"], req["y"])
            elif kind == "touch_up" and c in last:
                events.append({"t": t, "kind": "up", "x": last[c][0], "y": last[c][1]})
        elif u := MUMU.search(line):
            c = int(u[2])
            if u[1] == "down":
                open_m[c] = {"t": t, "kind": "tap", "x": round(int(u[3]) * scale), "y": round(int(u[4]) * scale), "ms": 0}
                mumu.append(open_m[c])
            elif c in open_m:
                e = open_m.pop(c)
                e["ms"] = round((t - e["t"]) * 1000)
    for e in mumu:  # a device press an agent call at the same moment and place already explains is dropped
        if not any(abs(a["t"] - e["t"]) < 0.25 and abs(a["x"] - e["x"]) < 12 and abs(a["y"] - e["y"]) < 12 for a in events):
            events.append(e)
    events.sort(key=lambda e: e["t"])
    for e in events:
        e["t"] = clock(e["t"])
    return {"space": SPACE, "events": events}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("-o", "--out", required=True, type=Path)
    ap.add_argument("--device-width", type=int, default=1920, help="MuMu touch width in device pixels")
    a = ap.parse_args(argv)
    lines = [ln for p in a.logs for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()]
    doc = parse(lines, a.device_width)
    a.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"{len(doc['events'])} events -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
