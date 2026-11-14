"""Health check of the install, and a safe update.

  python -I doktor.py            # doctor: config, folders, CLIs, keys (by variable name only), ports
  python -I doktor.py update     # git pull --ff-only, only when the repo has no local changes
Never prints a key value: a key is only reported as set or missing.
"""
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, CONFIG_FILE, EXTRA_DIRS, NOTES, SECRETS, T  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def env_adlari(d=C, yol=""):
    """(where, VARIABLE) for every *_env setting and every MCP env name in the config."""
    out = []
    if isinstance(d, dict):
        for k, v in d.items():
            if k.endswith("_env") and isinstance(v, str) and v:
                out.append((f"{yol}{k}", v))
            elif k == "env" and isinstance(v, list):
                out += [(f"{yol}env", x) for x in v]
            else:
                out += env_adlari(v, f"{yol}{k}.")
    elif isinstance(d, list):
        for i, x in enumerate(d):
            out += env_adlari(x, f"{yol}{i}.")
    return out


def port_bos(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def kontroller():
    """[(ok, line)]; ok is True, False, or None for a plain note."""
    r = [(CONFIG_FILE.exists(), f"config: {CONFIG_FILE}" + ("" if CONFIG_FILE.exists() else T(" yok (setup.py yazar)", " missing (setup.py writes it)"))),
         (NOTES.exists(), T("not klasörü: ", "notes folder: ") + str(NOTES))]
    r += [(d.exists(), T("ek klasör: ", "extra folder: ") + str(d)) for d in EXTRA_DIRS]
    cli = C["agent"]["cli"]
    r.append((bool(shutil.which(cli)), f"agent CLI {cli}: " + (shutil.which(cli) or T("PATH'te yok", "not on PATH"))))
    r.append((bool(shutil.which("ffmpeg")) or None, "ffmpeg: " + (shutil.which("ffmpeg") or T("yok (sesli cevap çalışmaz)", "missing (voice replies won't work)"))))
    if (C.get("sandbox") or {}).get("backend") == "docker":
        r.append((bool(shutil.which("docker")), "docker: " + (shutil.which("docker") or T("yok: sandbox komutları reddedilir", "missing: sandbox commands are refused"))))
    for ad, s in (C.get("mcp_servers") or {}).items():
        r.append((bool(shutil.which(s.get("command", ""))), f"MCP {ad}: {s.get('command')}"))
    tg = bool(os.environ.get("PENTARCH_TELEGRAM_TOKEN")) or (SECRETS / "telegram.txt").exists()
    r.append((tg, "Telegram token: " + (T("var", "set") if tg else T("yok", "missing"))))
    for yer, ad in env_adlari():
        r.append((bool(os.environ.get(ad)) or None, f"{ad} ({yer}): " + (T("tanımlı", "set") if os.environ.get(ad) else T("tanımsız", "not set"))))
    for ad in ("panel_port", "lock_port"):
        r.append((None, f"{ad} {C[ad]}: " + (T("boş", "free") if port_bos(C[ad]) else T("kullanımda (Pentarch çalışıyor olabilir)", "in use (Pentarch may be running)"))))
    return r


VPN = ("tap", "wintun", "wireguard", "vpn", "tun")
# Windows only: app crashes in the last 24 h, fixed drives, adapters that are up. One PowerShell call, JSON back
SISTEM_PS = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"  # otherwise the OEM code page garbles non-ASCII event text
    "$ev=@(Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000,1002;StartTime=(Get-Date).AddHours(-24)} "
    "-ErrorAction SilentlyContinue | select -First 10 | %{ $_.TimeCreated.ToString('MM-dd HH:mm')+' '+(($_.Message -split \"`n\")[0]) });"
    "$d=@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | %{ @{ad=$_.DeviceID;bos=[double]$_.FreeSpace;boyut=[double]$_.Size} });"
    "$a=@(Get-NetAdapter -ErrorAction SilentlyContinue | ?{$_.Status -eq 'Up'} | %{ $_.Name+' | '+$_.InterfaceDescription });"
    "@{ev=$ev;disk=$d;ag=$a} | ConvertTo-Json -Depth 3 -Compress")


def sistem_yorumla(js):
    """[(ok, line)] from the SISTEM_PS answer: crashes and a VPN are notes, a nearly full drive is a problem."""
    r = []
    ev = js.get("ev") or []
    r.append((None, T(f"son 24 saatte {len(ev)} uygulama çökmesi/donması", f"{len(ev)} app crash/hang event(s) in the last 24 h")
              + (": " + "; ".join(e[:90] for e in ev[:3]) if ev else "")))
    for d in js.get("disk") or []:
        bos, boyut = d.get("bos") or 0, d.get("boyut") or 0
        dolu = boyut and (bos < 10 * 2**30 or bos / boyut < 0.1)
        r.append((not dolu, T(f"disk {d.get('ad')}: {bos / 2**30:.0f} GB boş / {boyut / 2**30:.0f} GB",
                              f"drive {d.get('ad')}: {bos / 2**30:.0f} GB free of {boyut / 2**30:.0f} GB")))
    vpn = [a for a in js.get("ag") or [] if any(w in a.partition(" | ")[2].lower() for w in VPN)]
    r.append((None, T("VPN bağdaştırıcısı açık: ", "VPN adapter up: ") + "; ".join(vpn) if vpn
              else T("VPN bağdaştırıcısı görünmüyor", "no VPN adapter up")))
    return r


def erisim(url):
    """True when the host answered at all (any HTTP status means the network works)."""
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=6)
    except urllib.error.HTTPError:
        pass
    except Exception:
        return False
    return True


def sistem_kontrolleri():
    """Real connectivity, plus the Windows checks. Kept out of kontroller(): it touches the network and takes seconds."""
    hedef = {"google": "https://www.google.com", "telegram": "https://api.telegram.org"}
    sonuc = {k: erisim(u) for k, u in hedef.items()}
    r = [(any(sonuc.values()), T("internet: ", "internet: ") + ", ".join(
        f"{k} {T('açık', 'reachable') if v else T('YOK', 'UNREACHABLE')}" for k, v in sonuc.items()))]
    if os.name != "nt":
        return r
    try:
        import json
        p = subprocess.run(["powershell", "-NoProfile", "-Command", SISTEM_PS], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r + sistem_yorumla(json.loads(p.stdout))
    except Exception as e:
        return r + [(None, T(f"Windows kontrolleri okunamadı: {e!r}"[:200], f"Windows checks unreadable: {e!r}"[:200]))]


def doctor():
    sorun = 0
    for ok, satir in kontroller() + sistem_kontrolleri():
        print(("OK " if ok else "-- " if ok is None else "!! ") + satir)
        sorun += ok is False
    print(T(f"{sorun} sorun", f"{sorun} problem(s)"))
    return sorun


def update(git=shutil.which("git") or "git"):
    if not (REPO / ".git").exists():
        return T(f"{REPO} bir git deposu değil; yeni sürümü elle indir.", f"{REPO} is not a git repo; download the new version by hand.")
    durum = subprocess.run([git, "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True)
    if durum.returncode or durum.stdout.strip():
        return T("Depoda kaydedilmemiş değişiklik var; güncellemedim (önce commit ya da stash).",
                 "The repo has local changes; not updated (commit or stash first).")
    p = subprocess.run([git, "-C", str(REPO), "pull", "--ff-only"], capture_output=True, text=True)
    if p.returncode:
        return T("git pull olmadı: ", "git pull failed: ") + (p.stderr or p.stdout).strip()[-300:]
    return (p.stdout.strip() or "ok") + T("\nÇalışan Pentarch kod değişince kendini yeniden başlatır; yeni ayar için setup.py.",
                                         "\nA running Pentarch restarts itself when the code changes; run setup.py for new settings.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["update"]:
        print(update())
    elif not sys.argv[1:]:
        sys.exit(1 if doctor() else 0)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
