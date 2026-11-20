"""Where shell work runs: on this computer (default), in a throwaway Docker container, or on another machine over ssh.

  python -I kum.py <command> [args...]     # runs in the docker or ssh backend; refused when local

Config "sandbox": {"backend": "local" | "docker" | "ssh", "image": "...", "network": false, "host": "", "dir": ""}.
With docker the current folder is mounted at /work and nothing else; no network unless sandbox.network is true. The
container runs as a normal user with no capabilities, 256 processes and 2 GB; the home folder, a drive root or a folder
holding Pentarch's keys is never mounted.
With ssh the command runs on `host` (an ssh alias or user@host, key login only, no password prompt) inside `dir`
(default ~/pentarch-work); files are not copied over, the remote folder is its own. Fail safe: when the chosen
backend is unusable, the command is refused, never quietly run on the host.
"""
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, HOME, T  # noqa: E402

AYAR = {"backend": "local", "image": "python:3.12-slim", "network": False, **(C.get("sandbox") or {})}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def docker_var():
    d = shutil.which("docker")
    if not d:
        return False
    try:
        return subprocess.run([d, "info"], capture_output=True, timeout=20, creationflags=NO_WINDOW).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def sar(cmd, cwd):
    """The command line to run `cmd` (a list) in the backend. Raises RuntimeError when docker is chosen but unusable."""
    if AYAR["backend"] == "local":
        return list(cmd)
    if AYAR["backend"] == "ssh":
        host, ssh = str(AYAR.get("host") or ""), shutil.which("ssh")
        if not host or host.startswith("-") or not ssh:  # "-oProxyCommand=..." as a host would run a local command
            raise RuntimeError(T("sandbox ssh seçili ama sandbox.host boş/geçersiz ya da ssh yok; komut çalıştırılmadı",
                                 "sandbox is ssh but sandbox.host is empty/invalid or ssh is missing; command not run"))
        d = str(AYAR.get("dir") or "~/pentarch-work")
        d = "~/" + shlex.quote(d[2:]) if d.startswith("~/") else shlex.quote(d)  # ~ must stay unquoted to expand
        uzak = f"mkdir -p {d} && cd {d} && {shlex.join(cmd)}"
        return [ssh, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--", host, uzak]
    if AYAR["backend"] != "docker":
        raise RuntimeError(f"unknown sandbox backend: {AYAR['backend']}")
    if not docker_var():
        raise RuntimeError(T("sandbox docker seçili ama docker yok ya da çalışmıyor; komut çalıştırılmadı",
                             "sandbox is docker but docker is missing or not running; command not run"))
    yer = Path(cwd).resolve()
    if yer in (Path.home().resolve(), Path(HOME).resolve(), Path(yer.anchor)) or Path(HOME).resolve().is_relative_to(yer):
        raise RuntimeError(T(f"{yer} kum havuzuna bağlanmaz (ev klasörü, kök ya da Pentarch'ın anahtarları); bir proje klasörü seç",
                             f"{yer} is not mounted into the sandbox (home, a drive root or Pentarch's keys); pick a project folder"))
    kim = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "1000:1000"  # not root, files stay the user's
    return [shutil.which("docker") or "docker", "run", "--rm", "-i", *([] if AYAR["network"] else ["--network", "none"]),
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "2g",
            "--user", kim, "-e", "HOME=/tmp", "-v", f"{yer}:/work", "-w", "/work", AYAR["image"], *cmd]


def calistir(cmd, cwd=".", timeout=600):
    return subprocess.run(sar(cmd, cwd), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if AYAR["backend"] not in ("docker", "ssh"):  # the agent may run app/* scripts under acceptEdits; on the host this would be a shell
        sys.exit(T("kum.py yalnızca docker ya da ssh kum havuzunda komut çalıştırır (sandbox.backend)",
                   "kum.py only runs commands in the docker or ssh sandbox (sandbox.backend)"))
    try:
        p = calistir(sys.argv[1:])
    except RuntimeError as e:
        sys.exit(str(e))
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
