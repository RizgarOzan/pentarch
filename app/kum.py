"""Where shell work runs: on this computer (default) or in a throwaway Docker container.

  python -I kum.py <command> [args...]     # runs in the configured backend, in the current folder

Config "sandbox": {"backend": "local" | "docker", "image": "...", "network": false}. With docker the current folder
is mounted at /work and nothing else; no network unless sandbox.network is true. Fail safe: when docker is chosen but
missing or not running, the command is refused, never quietly run on the host.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, T  # noqa: E402

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
    if AYAR["backend"] != "docker":
        raise RuntimeError(f"unknown sandbox backend: {AYAR['backend']}")
    if not docker_var():
        raise RuntimeError(T("sandbox docker seçili ama docker yok ya da çalışmıyor; komut çalıştırılmadı",
                             "sandbox is docker but docker is missing or not running; command not run"))
    return [shutil.which("docker") or "docker", "run", "--rm", "-i", *([] if AYAR["network"] else ["--network", "none"]),
            "-v", f"{Path(cwd).resolve()}:/work", "-w", "/work", AYAR["image"], *cmd]


def calistir(cmd, cwd=".", timeout=600):
    return subprocess.run(sar(cmd, cwd), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        p = calistir(sys.argv[1:])
    except RuntimeError as e:
        sys.exit(str(e))
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
