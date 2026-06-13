from pathlib import Path
import base64

ROOT = Path(__file__).resolve().parents[1]
B64 = ROOT / "assets" / "app_icon.ico.b64"
ICO = ROOT / "assets" / "app_icon.ico"

ICO.parent.mkdir(parents=True, exist_ok=True)
ICO.write_bytes(base64.b64decode(B64.read_text(encoding="utf-8")))
print(f"Wrote {ICO}")
