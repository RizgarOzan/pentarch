# Pentarch one-line installer for Windows 10/11.
#   irm https://raw.githubusercontent.com/RizgarOzan/pentarch/main/install.ps1 | iex
# Problems are reported with throw, not exit, so a window running this through iex stays open.
# Clones into ~\pentarch (or $env:PENTARCH_DIR), makes a virtualenv, then starts the guided setup.
$prevErrorAction = $ErrorActionPreference  # via iex this runs in the user's own session, so it is put back at the end
$ErrorActionPreference = 'Stop'
trap { $ErrorActionPreference = $prevErrorAction; throw $_ }  # a throw would otherwise leave the user's own session on 'Stop'

$dir = if ($env:PENTARCH_DIR) { $env:PENTARCH_DIR } else { Join-Path $HOME 'pentarch' }
$repo = 'https://github.com/RizgarOzan/pentarch.git'

function Offer($cmd, $id, [switch]$force, $why = '') {
    # a missing tool is installed with winget after a yes, then PATH is reread so this window sees it
    if ((-not $force -and (Get-Command $cmd -ErrorAction SilentlyContinue)) -or -not (Get-Command winget -ErrorAction SilentlyContinue)) { return }
    if ($why) { Write-Host $why }
    $a = Read-Host "$cmd is missing / $cmd kurulu degil. Install it now? / Simdi kurulsun mu? [Y/n] [E/h]"
    if ($a -match '^\s*[nNhH]') { return }
    Write-Host "Windows may ask 'Allow this app to make changes?': click Yes. / Windows 'Degisiklik yapmasina izin verilsin mi?' diye sorabilir: Evet'e bas."
    winget install --id $id -e --accept-source-agreements --accept-package-agreements --disable-interactivity
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
$newWindow = 'Then open a NEW PowerShell window and run the line again. / Sonra YENI bir PowerShell penceresi acip ayni satiri tekrar calistir.'

Offer git 'Git.Git'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Missing: git. Install it from https://git-scm.com/downloads. / git kurulu degil, oradan kur. $newWindow"
}
Offer node 'OpenJS.NodeJS.LTS' -why 'Node.js installs the agent program (Gemini CLI, Claude Code...). / Node.js ajan programini (Gemini CLI, Claude Code...) kurmak icin gerekli.'
Offer ffmpeg 'Gyan.FFmpeg' -why 'Optional: ffmpeg lets the assistant answer with voice. / Istege bagli: ffmpeg asistanin sesli cevap vermesi icin.'

function FindPython {
    # "python" can be the Microsoft Store stub, so a version check decides, not Get-Command
    $ErrorActionPreference = 'Continue'  # the Store stub writes to stderr; with 'Stop' Windows PowerShell 5.1 would abort here
    foreach ($c in 'python', 'py') {
        if (Get-Command $c -ErrorAction SilentlyContinue) {
            & $c -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>$null
            if ($LASTEXITCODE -eq 0) { return $c }
        }
    }
}
$py = FindPython
if (-not $py) { Offer 'Python 3.10+' 'Python.Python.3.12' -force; $py = FindPython }
if (-not $py) {
    throw "Missing: Python 3.10 or newer. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'). / Python 3.10+ kurulu degil; kurarken 'Add python.exe to PATH' kutusunu isaretle. $newWindow"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Note: Node.js isn't installed. Setup can still run; you'll need it to install the agent CLI (https://nodejs.org/)."
    Write-Host "Not: Node.js kurulu degil. Kurulum yine calisir ama ajan programini kurmak icin gerekecek (https://nodejs.org/)."
}

if (Test-Path (Join-Path $dir '.git')) {
    Write-Host "Found an install at $dir, updating it. / $dir icinde kurulum var, guncelleniyor."
    git -C $dir pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull failed (local changes in $dir?). See the message above. / git pull basarisiz ($dir icinde yerel degisiklik mi var?), ustteki mesaja bak." }
} else {
    git clone --quiet $repo $dir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed (see the message above). / git clone basarisiz (ustteki mesaja bak)." }
}

Set-Location $dir
if (-not (Test-Path '.venv')) { & $py -m venv .venv }
& .\.venv\Scripts\python.exe setup.py
$ErrorActionPreference = $prevErrorAction
