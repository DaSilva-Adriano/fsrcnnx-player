# SPDX-License-Identifier: GPL-3.0-or-later
"""Download portable mpv and the two FSRCNNX shaders. Nothing else."""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
MPV_DIR = VENDOR / "mpv"
SEVEN = VENDOR / "7zr.exe"
SHADER_DIR = ROOT / "portable_config" / "shaders"
CACHE_DIR = ROOT / "portable_config" / "shader-cache"

MPV_API = "https://api.github.com/repos/zhongfly/mpv-winbuild/releases/latest"
SEVEN_URL = "https://www.7-zip.org/a/7zr.exe"
SHADER_8 = (
    "https://github.com/igv/FSRCNN-TensorFlow/releases/download/1.1/"
    "FSRCNNX_x2_8-0-4-1.glsl"
)
SHADER_16 = (
    "https://github.com/igv/FSRCNN-TensorFlow/releases/download/1.1/"
    "FSRCNNX_x2_16-0-4-1.glsl"
)
UA = "FSRCNNX-Player-installer (https://github.com/DaSilva-Adriano)"


def _ssl() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    return ctx


def _req(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": UA})


def log(msg: str) -> None:
    print(msg, flush=True)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log(f"download {url}")
    with urllib.request.urlopen(_req(url), context=_ssl()) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        with tmp.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                got += len(chunk)
                if total:
                    pct = 100.0 * got / total
                    log(f"  {got / 1e6:.1f} / {total / 1e6:.1f} MB ({pct:.0f}%)")
    tmp.replace(dest)
    log(f"saved {dest}")


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(_req(url), context=_ssl()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cpu_wants_v3() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        class Info(ctypes.Structure):
            _fields_ = [
                ("ProcessorArchitecture", ctypes.c_ushort),
                ("Reserved", ctypes.c_ushort),
                ("PageSize", ctypes.c_uint),
                ("MinimumApplicationAddress", ctypes.c_void_p),
                ("MaximumApplicationAddress", ctypes.c_void_p),
                ("ActiveProcessorMask", ctypes.c_void_p),
                ("NumberOfProcessors", ctypes.c_uint),
                ("ProcessorType", ctypes.c_uint),
                ("AllocationGranularity", ctypes.c_uint),
                ("ProcessorLevel", ctypes.c_ushort),
                ("ProcessorRevision", ctypes.c_ushort),
            ]

        info = Info()
        ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(info))
        # Intel Haswell+ / AMD Excavator+ report processor level >= 6 with AVX2.
        # This machine is Intel Iris Xe (11th gen+): use v3.
        return info.ProcessorArchitecture == 9 and info.ProcessorLevel >= 6
    except Exception:
        return True


def pick_mpv_asset(release: dict) -> tuple[str, str]:
    want_v3 = cpu_wants_v3()
    assets = release.get("assets") or []
    chosen = None
    fallback = None
    for a in assets:
        name = a.get("name") or ""
        url = a.get("browser_download_url") or ""
        if not name.startswith("mpv-x86_64") or not name.endswith(".7z"):
            continue
        if "debug" in name or "dev" in name or "lgpl" in name:
            continue
        if "v3" in name:
            if want_v3:
                chosen = (name, url)
        else:
            fallback = (name, url)
    pick = chosen or fallback
    if not pick:
        raise RuntimeError("No mpv-x86_64 .7z asset on the latest zhongfly release")
    return pick


def ensure_7zr() -> Path:
    if SEVEN.is_file():
        return SEVEN
    download(SEVEN_URL, SEVEN)
    if not SEVEN.is_file() or SEVEN.stat().st_size < 10000:
        raise RuntimeError("7zr.exe download failed")
    return SEVEN


def extract_7z(archive: Path, dest: Path) -> None:
    seven = ensure_7zr()
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [str(seven), "x", str(archive), f"-o{dest}", "-y"]
    log("extract " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(VENDOR))


def mpv_exe() -> Path:
    return MPV_DIR / "mpv.exe"


def install_shaders() -> None:
    SHADER_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    targets = {
        "FSRCNNX_x2_8-0-4-1.glsl": SHADER_8,
        "FSRCNNX_x2_16-0-4-1.glsl": SHADER_16,
    }
    for name, url in targets.items():
        dest = SHADER_DIR / name
        if dest.is_file() and dest.stat().st_size > 1000:
            log(f"shader ok {dest.name}")
            continue
        download(url, dest)


def install_mpv() -> None:
    if mpv_exe().is_file():
        log(f"mpv already present: {mpv_exe()}")
        return
    rel = fetch_json(MPV_API)
    name, url = pick_mpv_asset(rel)
    archive = VENDOR / name
    if not archive.is_file():
        download(url, archive)
    if MPV_DIR.exists():
        shutil.rmtree(MPV_DIR)
    extract_7z(archive, MPV_DIR)
    if not mpv_exe().is_file():
        # some archives nest a folder
        nested = list(MPV_DIR.glob("**/mpv.exe"))
        if nested:
            real = nested[0].parent
            if real != MPV_DIR:
                for item in real.iterdir():
                    shutil.move(str(item), str(MPV_DIR / item.name))
        if not mpv_exe().is_file():
            raise RuntimeError("mpv.exe missing after extract")
    log(f"mpv ready: {mpv_exe()}")


def sync_portable_config() -> None:
    """mpv portable mode: portable_config next to mpv.exe."""
    dest = MPV_DIR / "portable_config"
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    src = ROOT / "portable_config"
    try:
        os.symlink(src, dest, target_is_directory=True)
        log(f"linked {dest} -> {src}")
    except OSError:
        shutil.copytree(src, dest)
        log(f"copied portable_config -> {dest}")


def windows_desktop() -> Path:
    if sys.platform != "win32":
        return Path.home() / "Desktop"
    try:
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        # CSIDL_DESKTOPDIRECTORY = 0x0010 (OneDrive\\Bureau on this PC)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
        p = Path(buf.value)
        if p.is_dir():
            return p
    except Exception:
        pass
    for cand in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Bureau", Path.home() / "Bureau"):
        if cand.is_dir():
            return cand
    return Path.home() / "Desktop"


def desktop_shortcut() -> None:
    if sys.platform != "win32":
        return
    bat = ROOT / "launch.bat"
    desk = windows_desktop() / "FSRCNNX Player.lnk"
    if not bat.is_file():
        return
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{desk}'); "
        f"$sc.TargetPath = '{bat}'; "
        f"$sc.WorkingDirectory = '{ROOT}'; "
        "$sc.WindowStyle = 1; "
        "$sc.Description = 'FSRCNNX-8 / FSRCNNX-16 player'; "
        "$sc.Save()"
    )
    try:
        subprocess.check_call(
            ["powershell", "-NoProfile", "-Command", ps],
            cwd=str(ROOT),
        )
        log(f"shortcut {desk}")
    except Exception as e:
        log(f"shortcut skipped: {e}")


def verify() -> None:
    exe = mpv_exe()
    out = subprocess.check_output([str(exe), "--version"], text=True, errors="replace")
    log(out.splitlines()[0] if out else "mpv --version")
    for name in ("FSRCNNX_x2_8-0-4-1.glsl", "FSRCNNX_x2_16-0-4-1.glsl"):
        p = SHADER_DIR / name
        if not p.is_file():
            raise RuntimeError(f"missing shader {name}")
        log(f"  {name}  {p.stat().st_size} bytes")


def main() -> int:
    VENDOR.mkdir(parents=True, exist_ok=True)
    log("FSRCNNX Player install — mpv + FSRCNNX-8 + FSRCNNX-16 only")
    install_shaders()
    install_mpv()
    sync_portable_config()
    verify()
    desktop_shortcut()
    log("done")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        log(f"INSTALL FAILED: {e}")
        raise
