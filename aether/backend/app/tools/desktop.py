import os, subprocess, webbrowser, urllib.parse, platform
from pathlib import Path

# Deliberately allowlisted. Never pass an LLM-provided shell command to the OS.
APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "chrome": "chrome",
    "edge": "msedge",
    "spotify": "https://open.spotify.com/",
    "youtube music": "https://music.youtube.com/",
    "chatgpt": "https://chatgpt.com/",
    "vscode": "code",
}

def open_app(name: str):
    key = name.strip().lower()
    if key not in APP_ALIASES:
        raise ValueError(f"'{name}' is not in AETHER's safe app allowlist yet.")
    target = APP_ALIASES[key]
    if platform.system() == "Windows":
        if target.startswith(("https://", "http://")):
            webbrowser.open(target)
        elif key in ("chrome", "edge", "vscode"):
            # Start-menu protocol/registered app resolution, no shell interpolation.
            os.startfile(target)
        else:
            subprocess.Popen([target], shell=False)
    else:
        raise RuntimeError("Desktop app launching is currently supported on Windows only.")
    return {"opened": key}

def play_music(query: str = ""):
    q = query.strip()
    if q:
        url = "https://open.spotify.com/search/" + urllib.parse.quote(q)
    else:
        url = "https://open.spotify.com/"
    webbrowser.open(url)
    return {"opened_url": url, "message": "Opened Spotify. Choose playback if the app asks you to sign in."}

def open_url(url: str):
    allowed = ("https://", "http://")
    if not url.startswith(allowed):
        raise ValueError("Only HTTP/HTTPS URLs can be opened.")
    webbrowser.open(url)
    return {"opened_url": url}

def _send_media_key(char_code: int):
    # WScript.Shell.SendKeys with the virtual media-key character codes; no admin rights needed.
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
         f"(New-Object -ComObject WScript.Shell).SendKeys([char]{char_code})"],
        shell=False, check=False, timeout=10,
    )

def _lock_workstation():
    subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], shell=False)

def _sleep_pc():
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], shell=False)

def _take_screenshot():
    from datetime import datetime
    from app.config import OUTPUT_DIR
    try:
        from PIL import ImageGrab
    except ImportError:
        raise RuntimeError("Install the 'Pillow' package to enable screenshots.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    ImageGrab.grab().save(path)
    return {"message": "Captured a screenshot.", "path": str(path)}

def _set_wifi(enable: bool):
    # Disabling/enabling a network adapter needs admin rights. We launch an elevated
    # PowerShell for just this one allowlisted cmdlet; Windows shows a UAC consent prompt
    # the user must approve themselves. No other command can run through this path.
    verb = "Enable-NetAdapter" if enable else "Disable-NetAdapter"
    inner = f'{verb} -Name "Wi-Fi*" -Confirm:$false'
    outer = (
        "Start-Process powershell -Verb RunAs -WindowStyle Hidden -ArgumentList "
        f"'-NoProfile -Command \"{inner}\"'"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", outer], shell=False)
    return {"message": f"Requested Wi-Fi {'on' if enable else 'off'}. Approve the Windows permission prompt if one appears."}

SYSTEM_COMMANDS = {
    "wifi_on": lambda: _set_wifi(True),
    "wifi_off": lambda: _set_wifi(False),
    "lock": lambda: (_lock_workstation(), {"message": "Locked the screen."})[1],
    "mute": lambda: (_send_media_key(173), {"message": "Muted system volume."})[1],
    "volume_up": lambda: (_send_media_key(175), {"message": "Volume increased."})[1],
    "volume_down": lambda: (_send_media_key(174), {"message": "Volume decreased."})[1],
    "sleep": lambda: (_sleep_pc(), {"message": "Putting the PC to sleep."})[1],
    "screenshot": lambda: _take_screenshot(),
}

def run_system_command(command: str):
    key = command.strip().lower()
    if key not in SYSTEM_COMMANDS:
        raise ValueError(f"'{command}' is not in AETHER's safe system-control allowlist yet.")
    return SYSTEM_COMMANDS[key]()
