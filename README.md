# FSRCNNX Player

Realtime Windows player for **FSRCNNX-8** and **FSRCNNX-16** only.

mpv + igv’s two FSRCNNX GLSL shaders. No Anime4K, ArtCNN, RAVU, RTX VSR, or any other upscaler. This is the playback counterpart to the offline SR labs (`rtx-vsr-lab`, `noai-classic-upscale`, `clientsr-dump-lab`).

## What you get

| Key | Model | Role |
|-----|--------|------|
| **1** | `FSRCNNX_x2_8-0-4-1.glsl` | Fast 2× luma CNN (default) |
| **2** | `FSRCNNX_x2_16-0-4-1.glsl` | Heavier 2× luma CNN |

FSRCNNX is a **2× doubler**. It only hooks when the output is more than about 1.3× the source (720p on a 1080p/1440p/4K window, 1080p on a 4K window, …). At 1:1 it stays off; that is how the shader is written.

## Run

Double-click `launch.bat`, or the **FSRCNNX Player** shortcut on the desktop.

First launch downloads a portable **mpv** build (zhongfly) and the two shaders if they are not already in `vendor\mpv` / `portable_config\shaders`. After that, pick a video, choose 8 or 16, **Play**.

```bat
launch.bat
```

Or, once Python with tkinter is on PATH:

```bat
python install.py
python mpvai.py
```

No pip packages. Python 3.10+ with tkinter (Windows standard library).

## This computer

Installed and GPU-tested on **Intel Iris Xe** (`gpu-next` + D3D11, feature level 12_1). Panel is 2256×1504. Default is FSRCNNX-8. FSRCNNX-16 may drop frames on 1080p+.

The GUI defaults to a **2× window** so FSRCNNX’s 1.3× hook always fires. Fullscreen on this panel will skip FSRCNNX for 1080p sources (scale is only ~1.17×). Use 720p or keep 2× windowed.

In the player: `1` / `2` switch models, `i` shows stats (confirm the shader hooked), `f` fullscreen, `q` quit.

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
