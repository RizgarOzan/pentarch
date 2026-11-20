#!/usr/bin/env sh
# Pentarch one-line installer for Linux and macOS.
#   curl -fsSL https://raw.githubusercontent.com/RizgarOzan/pentarch/main/install.sh | sh
# Clones into ~/pentarch (or $PENTARCH_DIR), makes a virtualenv, then starts the guided setup.
set -eu
# Everything sits in main(), called on the last line: if `curl | sh` is cut off mid-download, nothing runs.
main() {
DIR="${PENTARCH_DIR:-$HOME/pentarch}"
REPO="https://github.com/RizgarOzan/pentarch.git"

say() { printf '%s\n' "$*"; }
need() {
  command -v "$1" >/dev/null 2>&1 || { say "Missing: $1. $2"; exit 1; }
}

# On a fresh Mac, /usr/bin/git is only a stub that pops up the developer-tools installer
if [ "$(uname)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1; then
  say "Missing: Apple's command line tools (they bring git). Run: xcode-select --install"
  say "Click Install in the window that opens, wait for it to finish, then run this installer again."
  exit 1
fi
need git "Install it from https://git-scm.com/downloads"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  # macOS ships an old /usr/bin/python3 shim; Homebrew's is the usual fix
  if [ "$(uname)" = Darwin ]; then
    if command -v brew >/dev/null 2>&1; then say "Missing: Python 3.10 or newer. Run: brew install python@3.12"
    else say "Missing: Python 3.10 or newer. Download the macOS installer from https://www.python.org/downloads/ and open it."
         say "When it finishes, double-click 'Install Certificates.command' in the Python folder it opens (without it, web requests fail with an SSL error)."; fi
    say "Then open a new Terminal window and run this installer again."
  else say "Missing: Python 3.10 or newer. Install it from https://www.python.org/downloads/"; fi
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  if [ "$(uname)" = Darwin ]; then say "Note: Node.js isn't installed. Setup still runs, but the AI agent needs it: get the macOS installer from https://nodejs.org/ (or: brew install node), then run this installer again."
  else say "Note: Node.js isn't installed. Setup can still run; you'll need it to install the agent CLI (https://nodejs.org/)."; fi
fi

if [ -d "$DIR/.git" ]; then
  say "Found an install at $DIR, updating it."
  git -C "$DIR" pull --ff-only
else
  git clone --quiet "$REPO" "$DIR"
fi

cd "$DIR"
if [ ! -d .venv ]; then
  # Debian and Ubuntu ship Python without venv/ensurepip
  case "${PREFIX:-}" in *com.termux*) say "On Termux run: pkg install python git procps, then python setup.py"; exit 1;; esac
  "$PY" -c 'import ensurepip' 2>/dev/null || { say "Missing: Python's venv module. On Debian/Ubuntu: sudo apt install python3-venv"; exit 1; }
  "$PY" -m venv .venv
fi
say "Later commands in the README that start with 'python' mean $DIR/.venv/bin/python (or run 'source .venv/bin/activate' first)."
# under `curl | sh` stdin is the script itself, so setup's questions read from the terminal instead
if [ -t 0 ]; then exec .venv/bin/python setup.py; else exec .venv/bin/python setup.py </dev/tty; fi
}
main "$@"
