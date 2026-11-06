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


def doctor():
    sorun = 0
    for ok, satir in kontroller():
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
