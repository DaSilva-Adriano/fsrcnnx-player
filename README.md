# FSRCNNX Player

Realtime Windows player: **LIVE_NONE** (no AI) plus **FSRCNNX-8** and **FSRCNNX-16**.

Same live-none / file-queue pattern as `clientsr-dump-lab`. No Anime4K, ArtCNN, RAVU, RTX VSR, or any other upscaler.

## What you get

| Key | Model | Role |
|-----|--------|------|
| **0** | `LIVE_NONE` | Native playback, no shaders, `d3d11va` + `gpu-api=d3d11` (Chrome-like) |
| **1** | `FSRCNNX_x2_8-0-4-1.glsl` | Fast 2× luma CNN |
| **2** | `FSRCNNX_x2_16-0-4-1.glsl` | Heavier 2× luma CNN |

**Add files** (Ctrl+click for several) or **Add folder**, then select the row you want and **Play**. Double-click a row also plays. LIVE_NONE is the default, matching ClientSR Dump Lab’s live combobox.

FSRCNNX is a **2× doubler**. It only hooks when the output is more than about 1.3× the source (720p on a 1080p/1440p/4K window, 1080p on a 4K window, …). At 1:1 it stays off; that is how the shader is written.

## Run

Double-click `launch.bat`.

First launch downloads a portable **mpv** build (zhongfly) and the two shaders if they are not already in `vendor\mpv` / `portable_config\shaders`. After that: add videos to the queue, pick **None** / FSRCNNX-8 / FSRCNNX-16, select a row, **Play**.

```bat
launch.bat
```

Or, once Python with tkinter is on PATH:

```bat
python install.py
python mpvai.py
```

No pip packages. Python 3.10+ with tkinter (Windows standard library).

## Tested hardware

GPU-tested on **Intel Iris Xe** (`gpu-next` + D3D11, feature level 12_1) with a 2256×1504 panel. Default live model is **None**. FSRCNNX-16 may drop frames on 1080p+.

LIVE_NONE uses a native window (no 2×). For FSRCNNX, **Force 2× window** is on so the 1.3× hook fires. Fullscreen on that panel size will skip FSRCNNX for 1080p sources (scale is only ~1.17×).

In the player: `0` None, `1` / `2` FSRCNNX, `i` stats, `f` fullscreen, `q` quit.

## Layout

```
portable_config/          mpv.conf, input.conf, shaders, lua OSD
vendor/mpv/               portable mpv (created by install.py)
install.py                downloads mpv + both shaders
mpvai.py                  Windows GUI
launch.bat
```

`install.py` puts `portable_config` next to `mpv.exe` so mpv runs in portable mode and **ignores** `%APPDATA%\mpv`. A global mpv config cannot pull in extra shaders.

## License

[GNU General Public License v3.0](LICENSE) (GPL-3.0-or-later).

Copyright (C) 2026 Adriano.

FSRCNNX shaders are from [igv/FSRCNN-TensorFlow](https://github.com/igv/FSRCNN-TensorFlow) (GPL-3.0). mpv is GPL-2.0-or-later. The Windows binary is the zhongfly auto-build, not redistributed in git.
