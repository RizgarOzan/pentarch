"""Measures internet use (Windows): adapter counters (total bytes) plus which processes moved data in a short sample.
Windows has no per-process network bytes; 'IO Other Bytes/sec' includes network traffic, so it is approximate.
Usage: python -I net.py [seconds=8]"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import T  # noqa: E402


def ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=0x08000000, timeout=120).stdout


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    sec = int(next((a for a in sys.argv[1:] if a.isdigit()), 8))
    cmd = ("(Get-NetAdapterStatistics | Where-Object {$_.ReceivedBytes -gt 0} | "
           "ForEach-Object {'{0} {1} {2}' -f $_.Name,$_.ReceivedBytes,$_.SentBytes})")
    a = {l.rsplit(" ", 2)[0]: tuple(map(int, l.rsplit(" ", 2)[1:])) for l in ps(cmd).splitlines() if l.strip()}
    raw = ("Get-CimInstance Win32_PerfRawData_PerfProc_Process | ForEach-Object "
           "{'{0} {1}' -f $_.Name,$_.IOOtherBytesPersec}")

    def procs():
        d = {}
        for l in ps(raw).splitlines():
            p = l.rsplit(" ", 1)
            if len(p) == 2 and p[1].isdigit() and p[0] not in ("_Total", "Idle"):
                d[p[0]] = d.get(p[0], 0) + int(p[1])
        return d

    # one PowerShell session, so the gap between the two samples really is `sec` (separate calls added ~4 s each)
    one = ("$r={Get-CimInstance Win32_PerfRawData_PerfProc_Process|%{'P|{0}|{1}' -f $_.Name,$_.IOOtherBytesPersec}};"
           "$n={Get-NetAdapterStatistics|?{$_.ReceivedBytes -gt 0}|%{'N|{0}|{1}|{2}' -f $_.Name,$_.ReceivedBytes,$_.SentBytes}};"
           f"&$n;&$r;'T|'+(Get-Date).Ticks;Start-Sleep -Seconds {sec};'T|'+(Get-Date).Ticks;&$n;&$r")
    lines = ps(one).splitlines()
    ti = [i for i, l in enumerate(lines) if l.startswith("T|")]
    dt = (int(lines[ti[1]][2:]) - int(lines[ti[0]][2:])) / 1e7 if len(ti) == 2 else sec
    p1, p2, a, b = {}, {}, {}, {}
    for i, l in enumerate(lines):
        f = l.split("|")
        if f[0] == "P" and f[2].isdigit() and f[1] not in ("_Total", "Idle"):
            d = p1 if i < ti[1] else p2
            d[f[1]] = d.get(f[1], 0) + int(f[2])
        elif f[0] == "N":
            (a if i < ti[1] else b)[f[1]] = (int(f[2]), int(f[3]))
    print(T(f"Ölçüm {dt:.0f} sn. Kart trafiği (MB):", f"Sampled {dt:.0f} s. Adapter traffic (MB):"))
    for k in b:
        if k in a:
            down, up, total = (b[k][0] - a[k][0]) / 1e6, (b[k][1] - a[k][1]) / 1e6, b[k][0] / 1e9
            print(T(f"  {k}: indirme {down:.1f}, yükleme {up:.1f}  (toplam sayaç: {total:.1f} GB indirme)",
                    f"  {k}: down {down:.1f}, up {up:.1f}  (counter total: {total:.1f} GB down)"))
    rows = [((p2[n] - p1[n]) / 1e6, n) for n in p2 if n in p1 and p2[n] > p1[n]]
    print(T("Süreç G/Ç (MB, G/Ç Other, ağ dahil; yaklaşık):", "Process I/O (MB, IO Other incl. network; approximate):"))
    for mb, n in sorted(rows, reverse=True)[:6]:
        print(f"  {n}: {mb:.1f}")


if __name__ == "__main__":
    main()
