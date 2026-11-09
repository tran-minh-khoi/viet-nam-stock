"""Compare two running instances field by field, for a safe switch-over.

    python scripts/compare_live.py http://127.0.0.1:8005 http://127.0.0.1:8007 PDR VNM FPT SHS BSR E1VFVN30

Prints every field that differs. Fields that depend on when each request ran (timestamp,
lastUpdated, stale) are skipped. Price fields may legitimately differ by one trade if the two
services refreshed a few seconds apart; run it again and they should converge.
Exit code 0 = identical, 1 = differences found.
"""
import json
import sys
import time
import urllib.error
import urllib.request

VOLATILE = {"timestamp", "lastUpdated", "stale", "uptimeSeconds", "upstreamCallsLastMinute",
            "upstreamLimitPerMinute", "priorityAgeSeconds", "cachedSymbols", "version", "docs"}


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in VOLATILE:
                continue
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'new' if k in b else 'old'}")
            else:
                out += diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} items vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out


def main():
    old, new, *symbols = sys.argv[1:]
    paths = []
    for s in symbols or ["PDR"]:
        paths += [f"/stock/{s}", f"/stock/{s}/recent?days=30", f"/stock/{s.lower()}?recent=5"]
    paths += ["/stocks?symbols=" + ",".join((symbols or ["PDR"])[:10]), "/stock/XXXX", "/stock/a%20b", "/health"]
    problems = 0
    for p in paths:
        (sa, a), (sb, b) = get(old, p), get(new, p)
        found = ([f"status {sa} != {sb}"] if sa != sb else []) + diff(a, b)
        print(("OK   " if not found else "DIFF ") + p)
        for line in found:
            print("       " + line)
        problems += bool(found)
        time.sleep(0.3)
    print(f"\n{len(paths) - problems}/{len(paths)} identical")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
