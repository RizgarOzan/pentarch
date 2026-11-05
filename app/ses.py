"""Turns text into speech and sends it to Telegram as a voice message.

Usage:
    python -I ses.py "text"                          (sends a voice message)
    python -I ses.py "text" --kaydet C:/path/out.ogg (does not send, writes the file)

Engine: edge-tts (needs internet). Voice is config "tts_voice", or a default for the configured language. Without
internet it falls back to Piper (local): the first <home>/piper/<lang>_*.onnx model, e.g. en_US-lessac-medium.onnx.
ffmpeg cleans the audio up and converts it to ogg/opus for Telegram.
"""
import site
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.append(site.getusersitepackages())  # piper is often pip --user installed; -I hides that folder
from config import C, HOME, LANG, NAME, T  # noqa: E402
import tg  # noqa: E402

VOICES = {"tr": ("tr-TR-AhmetNeural", "-4%", "-5Hz"), "en": ("en-US-GuyNeural", "+0%", "+0Hz")}
VOICE, RATE, PITCH = (C.get("tts_voice"), "+0%", "+0Hz") if C.get("tts_voice") else VOICES.get(LANG, VOICES["en"])
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # under pythonw, ffmpeg would open a console window
FX = "highpass=f=90,equalizer=f=3500:t=q:w=1.2:g=3,loudnorm=I=-16:TP=-1.5"  # clean voice; flanger/echo sounded muffled


def piper_model():
    found = sorted((HOME / "piper").glob(f"{LANG}_*.onnx"))
    if not found:
        raise FileNotFoundError(T(f"{HOME / 'piper'} içinde {LANG}_*.onnx yok", f"no {LANG}_*.onnx in {HOME / 'piper'}"))
    return found[0]


def piper_wav(text, wav):
    import wave
    from piper import PiperVoice
    voice = PiperVoice.load(str(piper_model()))
    with wave.open(str(wav), "wb") as f:
        voice.synthesize_wav(text, f)


def edge_mp3(text, mp3):
    subprocess.run([sys.executable, "-m", "edge_tts", "--voice", VOICE, f"--rate={RATE}", f"--pitch={PITCH}",
                    "--text", text, "--write-media", str(mp3)], check=True, capture_output=True, creationflags=NOWIN)


def to_ogg(src, ogg):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", FX,
                    "-c:a", "libopus", "-b:a", "32k", str(ogg)], check=True, creationflags=NOWIN)


def make(text, ogg):
    tmp = Path(tempfile.mkdtemp())
    try:
        src = tmp / "voice.mp3"
        edge_mp3(text, src)
    except Exception as e:
        print(T(f"edge-tts olmadı ({e}), piper deneniyor", f"edge-tts failed ({e}), trying piper"), file=sys.stderr)
        src = tmp / "voice.wav"
        piper_wav(text, src)
    to_ogg(src, ogg)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__ + f"\nvoice: {VOICE}")
    out = None
    if "--kaydet" in args:
        i = args.index("--kaydet")
        out = Path(args[i + 1])
        args = args[:i] + args[i + 2:]
    text = " ".join(args)
    ogg = out or Path(tempfile.mkdtemp()) / "voice.ogg"
    make(text, ogg)
    if out:
        print(T(f"yazıldı: {out}", f"written: {out}"))
        return
    tg.send_voice(tg.load_state(), ogg, text)
    tg.log(NAME, T("[sesli mesaj] ", "[voice message] ") + text)


if __name__ == "__main__":
    main()
