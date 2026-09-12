# SPDX-License-Identifier: GPL-3.0-or-later
"""
FSRCNNX Player
==============
Copyright (C) 2026 Adriano

Windows player that plays video through mpv with only two shaders:
FSRCNNX-8 (fast) and FSRCNNX-16 (quality). No other upscalers.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
VENDOR_MPV = ROOT / "vendor" / "mpv" / "mpv.exe"
SHADER_8 = ROOT / "portable_config" / "shaders" / "FSRCNNX_x2_8-0-4-1.glsl"
SHADER_16 = ROOT / "portable_config" / "shaders" / "FSRCNNX_x2_16-0-4-1.glsl"

APP_NAME = "FSRCNNX Player"
BG = "#1b1b1b"
BG2 = "#111111"
FG = "#e8e8e8"
ACCENT = "#5b9fd4"
MUTED = "#9a9a9a"
BTN_BG = "#2c2c2c"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

VIDEO_TYPES = [
    (
        "Video",
        "*.mp4 *.mkv *.webm *.avi *.mov *.m4v *.ts *.m2ts *.wmv *.flv *.mpeg *.mpg *.ogv",
    ),
    ("All", "*.*"),
]


def gpu_name() -> str:
    if sys.platform != "win32":
        return "unknown"
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)",
            ],
            creationflags=CREATE_NO_WINDOW,
            text=True,
            errors="replace",
            timeout=8,
        )
        return (out or "").strip() or "unknown"
    except Exception:
        return "unknown"


def display_size() -> str:
    if sys.platform != "win32":
        return "unknown"
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$v = Get-CimInstance Win32_VideoController | Select-Object -First 1; "
                "'{0}x{1}' -f $v.CurrentHorizontalResolution, $v.CurrentVerticalResolution",
            ],
            creationflags=CREATE_NO_WINDOW,
            text=True,
            errors="replace",
            timeout=8,
        )
        return (out or "").strip() or "unknown"
    except Exception:
        return "unknown"


def mpv_version(exe: Path) -> str:
    try:
        out = subprocess.check_output(
            [str(exe), "--version"],
            creationflags=CREATE_NO_WINDOW,
            text=True,
            errors="replace",
            timeout=8,
        )
        return (out.splitlines() or ["mpv"])[0].strip()
    except Exception as e:
        return f"unreadable ({e})"


def _try_enable_file_drop(window: tk.Misc, on_files) -> object | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    WM_DROPFILES = 0x0233
    GWLP_WNDPROC = -4
    GA_ROOT = 2
    LONG_PTR = ctypes.c_ssize_t
    LRESULT = LONG_PTR
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetAncestor.restype = wintypes.HWND
    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    shell32.DragQueryFileW.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
        wintypes.LPWSTR,
        wintypes.UINT,
    ]
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragFinish.argtypes = [wintypes.HANDLE]

    if ctypes.sizeof(ctypes.c_void_p) == 8:
        set_long = user32.SetWindowLongPtrW
        call_proc = user32.CallWindowProcW
    else:
        set_long = user32.SetWindowLongW
        call_proc = user32.CallWindowProcW
    set_long.restype = LONG_PTR
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
    call_proc.restype = LRESULT
    call_proc.argtypes = [
        LONG_PTR,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    WNDPROC = ctypes.WINFUNCTYPE(
        LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    class DropHook:
        def __init__(self):
            self.hwnd = 0
            self.old_proc = 0
            self._wndproc = None
            self.alive = False

        def attach(self) -> bool:
            window.update_idletasks()
            inner = int(window.winfo_id())
            root_hwnd = user32.GetAncestor(inner, GA_ROOT) or inner
            self.hwnd = int(root_hwnd)
            if not self.hwnd:
                return False
            shell32.DragAcceptFiles(self.hwnd, True)
            self._wndproc = WNDPROC(self._dispatch)
            new_ptr = ctypes.cast(self._wndproc, ctypes.c_void_p).value
            self.old_proc = set_long(self.hwnd, GWLP_WNDPROC, new_ptr)
            self.alive = True
            return True

        def detach(self) -> None:
            if not self.alive:
                return
            try:
                if self.old_proc and self.hwnd:
                    set_long(self.hwnd, GWLP_WNDPROC, self.old_proc)
                if self.hwnd:
                    shell32.DragAcceptFiles(self.hwnd, False)
            except OSError:
                pass
            self.alive = False

        def _handle_drop(self, hdrop) -> None:
            count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
            files: list[str] = []
            for i in range(count):
                nchars = shell32.DragQueryFileW(hdrop, i, None, 0)
                buf = ctypes.create_unicode_buffer(nchars + 1)
                shell32.DragQueryFileW(hdrop, i, buf, nchars + 1)
                files.append(buf.value)
            shell32.DragFinish(hdrop)
            if files:
                window.after(0, lambda paths=files: on_files(paths))

        def _dispatch(self, hwnd, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                try:
                    self._handle_drop(wparam)
                except Exception:
                    try:
                        shell32.DragFinish(wparam)
                    except Exception:
                        pass
                return 0
            return call_proc(self.old_proc, hwnd, msg, wparam, lparam)

    hook = DropHook()
    try:
        if hook.attach():
            return hook
    except Exception:
        try:
            hook.detach()
        except Exception:
            pass
    return None


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=BG)
        self.geometry("880x640")
        self.minsize(760, 560)
        self.q: queue.Queue = queue.Queue()
        self.drop_hook = None
        self.player_proc: subprocess.Popen | None = None

        self.var_in = tk.StringVar()
        self.var_model = tk.StringVar(value="fsrcnnx8")
        self.var_fs = tk.BooleanVar(value=False)
        self.var_force2x = tk.BooleanVar(value=True)

        self._style()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._attach_dnd)
        self.after(50, self._drain)
        self.after(120, self._probe_async)

    def _style(self) -> None:
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=FG, fieldbackground=BG2)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("TFrame", background=BG)
        st.configure("TLabelframe", background=BG, foreground=ACCENT)
        st.configure("TLabelframe.Label", background=BG, foreground=ACCENT)
        st.configure("TCheckbutton", background=BG, foreground=FG)
        st.configure("TRadiobutton", background=BG, foreground=FG)
        st.configure("TButton", background=BTN_BG, foreground=FG)
        st.configure("Accent.TButton", background=ACCENT, foreground="#111")
        st.map("TButton", background=[("active", "#3a3a3a")])
        st.configure("TEntry", fieldbackground=BG2, foreground=FG)

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 6}
        top = ttk.Frame(self)
        top.pack(fill=tk.BOTH, expand=True)

        ttk.Label(top, text=APP_NAME, font=("Segoe UI", 16, "bold"), foreground=ACCENT).pack(
            anchor="w", **pad
        )
        ttk.Label(
            top,
            text="Realtime FSRCNNX-8 / FSRCNNX-16 in mpv. No other shaders.",
            foreground=MUTED,
        ).pack(anchor="w", padx=10)

        capf = ttk.LabelFrame(top, text="Capabilities")
        capf.pack(fill=tk.BOTH, padx=10, pady=6)
        self.caps = tk.Text(
            capf, height=8, bg=BG2, fg=FG, insertbackground=FG, relief=tk.FLAT, wrap=tk.WORD
        )
        self.caps.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.caps.insert("1.0", "Probing mpv, shaders, and GPU…")
        self.caps.configure(state=tk.DISABLED)

        row = ttk.Frame(top)
        row.pack(fill=tk.X, **pad)
        ttk.Label(row, text="Video").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.var_in).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(row, text="Browse", command=self._browse_in).pack(side=tk.LEFT)

        model = ttk.LabelFrame(top, text="Upscaler (only these two)")
        model.pack(fill=tk.X, padx=10, pady=6)
        rf = ttk.Frame(model)
        rf.pack(fill=tk.X, padx=6, pady=6)
        ttk.Radiobutton(
            rf,
            text="FSRCNNX-8  (fast, default — Intel Iris Xe)",
            value="fsrcnnx8",
            variable=self.var_model,
        ).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            rf,
            text="FSRCNNX-16  (heavier, slightly sharper)",
            value="fsrcnnx16",
            variable=self.var_model,
        ).pack(anchor="w", pady=2)
        ttk.Label(
            model,
            text="In the player: 1 = FSRCNNX-8,  2 = FSRCNNX-16. FSRCNNX is a 2× luma doubler and only hooks when the window is more than ~1.3× the source.",
            foreground=MUTED,
            wraplength=780,
        ).pack(anchor="w", padx=6, pady=(0, 6))

        opt = ttk.Frame(top)
        opt.pack(fill=tk.X, **pad)
        ttk.Checkbutton(
            opt,
            text="Force 2× window (needed so FSRCNNX hooks; default ON)",
            variable=self.var_force2x,
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(opt, text="Fullscreen", variable=self.var_fs).pack(side=tk.LEFT, padx=16)

        btns = ttk.Frame(top)
        btns.pack(fill=tk.X, padx=10, pady=8)
        self.install_btn = ttk.Button(btns, text="Install / repair", command=self._install)
        self.install_btn.pack(side=tk.LEFT)
        self.play_btn = ttk.Button(btns, text="Play", command=self._play, style="Accent.TButton")
        self.play_btn.pack(side=tk.RIGHT)

        logf = ttk.LabelFrame(top, text="Log")
        logf.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log = tk.Text(logf, height=10, bg=BG2, fg=FG, insertbackground=FG, relief=tk.FLAT, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _set_caps(self, text: str) -> None:
        self.caps.configure(state=tk.NORMAL)
        self.caps.delete("1.0", tk.END)
        self.caps.insert("1.0", text)
        self.caps.configure(state=tk.DISABLED)

    def _log(self, msg: str) -> None:
        self.log.insert(tk.END, msg.rstrip() + "\n")
        self.log.see(tk.END)

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "caps":
                    self._set_caps(payload)
                elif kind == "err":
                    messagebox.showerror(APP_NAME, payload)
                elif kind == "info":
                    messagebox.showinfo(APP_NAME, payload)
                elif kind == "busy":
                    state = tk.DISABLED if payload else tk.NORMAL
                    self.play_btn.configure(state=state)
                    self.install_btn.configure(state=state)
        except queue.Empty:
            pass
        self.after(80, self._drain)

    def _attach_dnd(self) -> None:
        self.drop_hook = _try_enable_file_drop(self, self._on_drop)

    def _on_drop(self, paths: list[str]) -> None:
        files = [p for p in paths if Path(p).is_file()]
        if not files:
            return
        self.var_in.set(files[0])
        extra = f" (+{len(files) - 1} more ignored)" if len(files) > 1 else ""
        self._log(f"drop {files[0]}{extra}")

    def _browse_in(self) -> None:
        path = filedialog.askopenfilename(
            title="Open video",
            filetypes=VIDEO_TYPES,
            parent=self,
        )
        if path:
            self.var_in.set(path)
            self._log(f"source {path}")

    def _ready(self) -> tuple[bool, str]:
        lines = []
        ok = True
        gpu = gpu_name()
        lines.append(f"GPU: {gpu}")
        lines.append(f"Display: {display_size()}")
        if VENDOR_MPV.is_file():
            lines.append(f"mpv: {mpv_version(VENDOR_MPV)}")
            lines.append(f"     {VENDOR_MPV}")
        else:
            ok = False
            lines.append("mpv: MISSING — click Install / repair")
        for label, path in (("FSRCNNX-8", SHADER_8), ("FSRCNNX-16", SHADER_16)):
            if path.is_file():
                lines.append(f"{label}: {path.name}  ({path.stat().st_size} bytes)")
            else:
                ok = False
                lines.append(f"{label}: MISSING")
        lines.append("")
        lines.append("This player does not load Anime4K, ArtCNN, RAVU, RTX VSR, or any other shader.")
        if "Iris" in gpu or "Intel" in gpu:
            lines.append("Intel iGPU: keep FSRCNNX-8 for 1080p. FSRCNNX-16 may drop frames.")
        return ok, "\n".join(lines)

    def _probe_async(self) -> None:
        def work():
            try:
                ok, text = self._ready()
                self.q.put(("caps", text))
                self.q.put(("log", "ready" if ok else "dependencies missing — run Install / repair"))
            except Exception as e:
                self.q.put(("caps", str(e)))
                self.q.put(("log", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _install(self) -> None:
        self.q.put(("busy", True))
        self.q.put(("log", "installing mpv + FSRCNNX-8 + FSRCNNX-16…"))

        def work():
            try:
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "install.py")],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    errors="replace",
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                for line in out.splitlines():
                    self.q.put(("log", line))
                if proc.returncode != 0:
                    self.q.put(("err", "Install failed. See log."))
                else:
                    self.q.put(("info", "mpv and both FSRCNNX shaders are installed."))
                _, text = self._ready()
                self.q.put(("caps", text))
            except Exception as e:
                self.q.put(("err", str(e)))
            finally:
                self.q.put(("busy", False))

        threading.Thread(target=work, daemon=True).start()

    def _play(self) -> None:
        src = self.var_in.get().strip().strip('"')
        if not src:
            messagebox.showerror(APP_NAME, "Pick a video")
            return
        path = Path(src)
        if not path.is_file():
            messagebox.showerror(APP_NAME, f"Input not found:\n{path}")
            return
        if not VENDOR_MPV.is_file() or not SHADER_8.is_file() or not SHADER_16.is_file():
            if messagebox.askyesno(APP_NAME, "mpv or shaders are missing. Install now?"):
                self._install()
            return
        profile = self.var_model.get()
        shader = SHADER_8 if profile == "fsrcnnx8" else SHADER_16
        cmd = [
            str(VENDOR_MPV),
            f"--profile={profile}",
            f"--glsl-shaders={shader}",
            "--force-window=yes",
        ]
        if self.var_force2x.get():
            cmd.append("--window-scale=2")
        if self.var_fs.get():
            cmd.append("--fullscreen=yes")
        cmd.append(str(path))
        self._log(" ".join(cmd))
        try:
            self.player_proc = subprocess.Popen(cmd, cwd=str(VENDOR_MPV.parent))
        except OSError as e:
            messagebox.showerror(APP_NAME, str(e))

    def _on_close(self) -> None:
        if self.drop_hook is not None:
            try:
                self.drop_hook.detach()
            except Exception:
                pass
        self.destroy()


def main() -> None:
    if sys.platform != "win32":
        print("Windows only", file=sys.stderr)
        raise SystemExit(1)
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
