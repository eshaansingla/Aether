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

def play_music(query: str = "", service: str = "youtube"):
    q = query.strip()
    if service == "spotify":
        return _play_spotify(q)
    return _play_youtube(q)

def _play_spotify(q: str):
    if not q:
        webbrowser.open("https://open.spotify.com/")
        return {"opened_url": "https://open.spotify.com/", "message": "Opened Spotify."}
    # Spotify's web player needs a signed-in session to autoplay, which isn't available
    # headlessly here — but the spotify: URI deep-links straight into the installed
    # desktop app's search results (one click from actual playback) when it's running,
    # which is the closest thing to "just play it" without the Spotify API/OAuth.
    if platform.system() == "Windows":
        try:
            os.startfile(f"spotify:search:{urllib.parse.quote(q)}")
            return {"message": f'Opened Spotify and searched for "{q}" — press play on the top result.'}
        except OSError:
            pass
    url = "https://open.spotify.com/search/" + urllib.parse.quote(q)
    webbrowser.open(url)
    return {"opened_url": url, "message": f'Opened Spotify search for "{q}" — press play on the top result.'}

def _play_youtube(q: str):
    if not q:
        webbrowser.open("https://www.youtube.com/")
        return {"opened_url": "https://www.youtube.com/", "message": "Opened YouTube."}
    # No API key available locally, so the top result's video id is scraped from the
    # search results page; that lets playback start immediately instead of landing on
    # a results list the user still has to click through.
    import re
    try:
        import httpx
        resp = httpx.get(
            "https://www.youtube.com/results",
            # sp=EgIQAQ%3D%3D restricts results to videos only, so the first hit is never
            # a channel/playlist card; the CONSENT cookie skips the EU cookie-consent
            # interstitial that otherwise replaces the results page with no video data.
            params={"search_query": q, "sp": "EgIQAQ%3D%3D", "hl": "en", "gl": "US"},
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
            cookies={"CONSENT": "YES+1", "SOCS": "CAI"},
            timeout=6,
            follow_redirects=True,
        )
        match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
        if match:
            url = f"https://www.youtube.com/watch?v={match.group(1)}&autoplay=1"
            webbrowser.open(url)
            return {"opened_url": url, "message": f'Playing "{q}" now.'}
    except Exception:
        pass
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(q)
    webbrowser.open(url)
    return {"opened_url": url, "message": f'Opened the search results for "{q}" — pick a track to play.'}

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

def _volume_interface():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume

def _set_volume(level):
    level = max(0, min(100, int(level if level is not None else 50)))
    try:
        vol = _volume_interface()
        vol.SetMasterVolumeLevelScalar(level / 100, None)
        return {"message": f"Volume set to {level}%."}
    except Exception as exc:
        raise RuntimeError(f"Could not change the system volume: {exc}")

def _adjust_volume(amount, direction):
    amount = int(amount) if amount is not None else 10
    try:
        vol = _volume_interface()
        current = vol.GetMasterVolumeLevelScalar()
        new = max(0.0, min(1.0, current + direction * (amount / 100)))
        vol.SetMasterVolumeLevelScalar(new, None)
        pct = round(new * 100)
        return {"message": f"Volume {'increased' if direction > 0 else 'decreased'} to {pct}%."}
    except Exception as exc:
        raise RuntimeError(f"Could not change the system volume: {exc}")

def _run_ps_query(cmd: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd],
        shell=False, check=False, timeout=10, capture_output=True, text=True,
    )
    return result.stdout.strip()

def _get_brightness():
    out = _run_ps_query("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness")
    if not out.isdigit():
        raise RuntimeError(
            "Couldn't read screen brightness — this only works on a built-in laptop display, "
            "not an external monitor."
        )
    return int(out)

def _set_brightness(level):
    level = max(0, min(100, int(level if level is not None else 50)))
    out = _run_ps_query(
        f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level}); 'ok'"
    )
    if out.strip() != "ok":
        raise RuntimeError(
            "Couldn't change screen brightness — this only works on a built-in laptop display, "
            "not an external monitor."
        )
    return {"message": f"Brightness set to {level}%."}

def _adjust_brightness(amount, direction):
    amount = int(amount) if amount is not None else 10
    current = _get_brightness()
    new = max(0, min(100, current + direction * amount))
    return _set_brightness(new)

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
    "wifi_on": lambda amount=None: _set_wifi(True),
    "wifi_off": lambda amount=None: _set_wifi(False),
    "lock": lambda amount=None: (_lock_workstation(), {"message": "Locked the screen."})[1],
    "mute": lambda amount=None: (_send_media_key(173), {"message": "Muted system volume."})[1],
    "volume_up": lambda amount=None: _adjust_volume(amount, 1),
    "volume_down": lambda amount=None: _adjust_volume(amount, -1),
    "volume_set": lambda amount=None: _set_volume(amount),
    "brightness_up": lambda amount=None: _adjust_brightness(amount, 1),
    "brightness_down": lambda amount=None: _adjust_brightness(amount, -1),
    "brightness_set": lambda amount=None: _set_brightness(amount),
    "sleep": lambda amount=None: (_sleep_pc(), {"message": "Putting the PC to sleep."})[1],
    "screenshot": lambda amount=None: _take_screenshot(),
}

def run_system_command(command: str, amount=None):
    key = command.strip().lower()
    if key not in SYSTEM_COMMANDS:
        raise ValueError(f"'{command}' is not in AETHER's safe system-control allowlist yet.")
    return SYSTEM_COMMANDS[key](amount)
