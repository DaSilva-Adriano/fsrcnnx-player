# SPDX-License-Identifier: GPL-3.0-or-later
"""
FSRCNNX Player
==============
Copyright (C) 2026 Adriano

Windows player: LIVE_NONE (no AI, native hw decode) plus FSRCNNX-8
and FSRCNNX-16. Same live-none / queue pattern as clientsr-dump-lab.

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
TOKEN_LIVE_NONE = "LIVE_NONE"
LIVE_NONE_LABEL = "None — native (no AI, hw decode)"
BG = "#1b1b1b"
BG2 = "#111111"
FG = "#e8e8e8"
ACCENT = "#5b9fd4"
MUTED = "#9a9a9a"
BTN_BG = "#2c2c2c"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".avi",
    ".mov",
    ".m4v",
    ".ts",
    ".m2ts",
    ".wmv",
    ".flv",
    ".mpeg",
    ".mpg",
    ".ogv",
}
VIDEO_TYPES = [
    ("Video", " ".join(f"*{e}" for e in sorted(VIDEO_EXTENSIONS))),
    ("All", "*.*"),
]


def collect_videos(paths: list[Path], *, recursive: bool = True) -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        p = Path(raw)
        candidates: list[Path] = []
        if p.is_file():
            candidates.append(p)
        elif p.is_dir():
            iterator = p.rglob("*") if recursive else p.glob("*")
            candidates.extend(iterator)
        for child in candidates:
            if not child.is_file() or child.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            try:
                key = str(child.resolve()).lower()
            except OSError:
                key = str(child).lower()
            if key in seen:
                continue
            seen.add(key)
            files.append(child)
    files.sort(key=lambda x: str(x).lower())
    return files


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
        self.geometry("920x780")
        self.minsize(800, 680)
        self.q: queue.Queue = queue.Queue()
        self.drop_hook = None
        self.player_proc: subprocess.Popen | None = None

        self.queue_paths: list[Path] = []
        self.var_model = tk.StringVar(value="none")
        self.var_fs = tk.BooleanVar(value=False)
        self.var_force2x = tk.BooleanVar(value=True)
        self.queue_count_var = tk.StringVar(value="0 files")

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
            text="LIVE_NONE (no AI) + FSRCNNX-8 / FSRCNNX-16. Same live-none / queue as ClientSR Dump Lab.",
            foreground=MUTED,
        ).pack(anchor="w", padx=10)

        capf = ttk.LabelFrame(top, text="Capabilities")
        capf.pack(fill=tk.X, padx=10, pady=6)
        self.caps = tk.Text(
            capf, height=5, bg=BG2, fg=FG, insertbackground=FG, relief=tk.FLAT, wrap=tk.WORD
        )
        self.caps.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.caps.insert("1.0", "Probing mpv, shaders, and GPU…")
        self.caps.configure(state=tk.DISABLED)

        qf = ttk.LabelFrame(top, text="Queue")
        qf.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        tools = ttk.Frame(qf)
        tools.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(tools, text="Add files", command=self._add_files).pack(side=tk.LEFT)
        ttk.Button(tools, text="Add folder", command=self._add_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(tools, text="Remove", command=self._remove_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(tools, text="Clear", command=self._clear_queue).pack(side=tk.LEFT, padx=4)
        ttk.Label(tools, textvariable=self.queue_count_var, foreground=MUTED).pack(side=tk.RIGHT)

        list_wrap = ttk.Frame(qf)
        list_wrap.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))
        scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL)
        self.listbox = tk.Listbox(
            list_wrap,
            selectmode=tk.BROWSE,
            height=8,
            activestyle="dotbox",
            font=("Consolas", 9),
            bg=BG2,
            fg=FG,
            selectbackground="#2a4a6a",
            selectforeground=FG,
            highlightthickness=0,
            relief=tk.FLAT,
            yscrollcommand=scroll.set,
        )
        scroll.config(command=self.listbox.yview)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._play())
        self.listbox.bind("<Return>", lambda _e: self._play())
        self.listbox.bind("<Delete>", lambda _e: self._remove_selected())
        ttk.Label(
            qf,
            text="Drop files/folders here. Select one row, then Play. Double-click also plays.",
            foreground=MUTED,
        ).pack(anchor="w", padx=6, pady=(0, 6))

        model = ttk.LabelFrame(top, text="Live model")
        model.pack(fill=tk.X, padx=10, pady=6)
        rf = ttk.Frame(model)
        rf.pack(fill=tk.X, padx=6, pady=6)
        ttk.Radiobutton(
            rf,
            text=f"{LIVE_NONE_LABEL}  [{TOKEN_LIVE_NONE}]",
            value="none",
            variable=self.var_model,
        ).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            rf,
            text="FSRCNNX-8  (fast — Intel Iris Xe)  [FSRCNNX8]",
            value="fsrcnnx8",
            variable=self.var_model,
        ).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            rf,
            text="FSRCNNX-16  (heavier, slightly sharper)  [FSRCNNX16]",
            value="fsrcnnx16",
            variable=self.var_model,
        ).pack(anchor="w", pady=2)
        ttk.Label(
            model,
            text="None: d3d11va + gpu-api=d3d11, no shaders, native window (Chrome-like). "
            "FSRCNNX is a 2× luma doubler (hooks above ~1.3×). In the player: 0 = None, 1 = FSRCNNX-8, 2 = FSRCNNX-16.",
            foreground=MUTED,
            wraplength=780,
        ).pack(anchor="w", padx=6, pady=(0, 6))

        opt = ttk.Frame(top)
        opt.pack(fill=tk.X, **pad)
        ttk.Checkbutton(
            opt,
            text="Force 2× window (FSRCNNX only — ignored for LIVE_NONE)",
            variable=self.var_force2x,
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(opt, text="Fullscreen", variable=self.var_fs).pack(side=tk.LEFT, padx=16)

        btns = ttk.Frame(top)
        btns.pack(fill=tk.X, padx=10, pady=8)
        self.install_btn = ttk.Button(btns, text="Install / repair", command=self._install)
        self.install_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(btns, text="Stop", command=self._stop)
        self.stop_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.play_btn = ttk.Button(btns, text="▶ Play", command=self._play, style="Accent.TButton")
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
        self._ingest_paths([Path(p) for p in paths])

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Add videos — hold Ctrl to pick more than one",
            filetypes=VIDEO_TYPES,
            parent=self,
        )
        self._ingest_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        path = filedialog.askdirectory(title="Add folder of videos", parent=self)
        if path:
            self._ingest_paths([Path(path)])

    def _ingest_paths(self, paths: list[Path]) -> None:
        videos = collect_videos(paths)
        if not videos:
            if paths:
                messagebox.showinfo(APP_NAME, "No video files found.")
            return
        existing = {str(p).lower() for p in self.queue_paths}
        added: list[Path] = []
        for p in videos:
            key = str(p).lower()
            if key in existing:
                continue
            existing.add(key)
            self.queue_paths.append(p)
            self.listbox.insert(tk.END, p.name)
            added.append(p)
        self._refresh_queue_count()
        if added:
            self._log(f"queue +{len(added)}  ({self.listbox.size()} total)")
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.listbox.size() - 1)
            self.listbox.see(tk.END)

    def _refresh_queue_count(self) -> None:
        n = len(self.queue_paths)
        self.queue_count_var.set(f"{n} file{'s' if n != 1 else ''}")

    def _selected_index(self) -> int | None:
        sel = self.listbox.curselection()
        if not sel:
            return None
        i = int(sel[0])
        if 0 <= i < len(self.queue_paths):
            return i
        return None

    def _selected_path(self) -> Path | None:
        i = self._selected_index()
        if i is None:
            return None
        return self.queue_paths[i]

    def _remove_selected(self) -> None:
        i = self._selected_index()
        if i is None:
            return
        self.listbox.delete(i)
        removed = self.queue_paths.pop(i)
        self._refresh_queue_count()
        if self.queue_paths:
            nxt = min(i, len(self.queue_paths) - 1)
            self.listbox.selection_set(nxt)
        self._log(f"removed {removed.name}")

    def _clear_queue(self) -> None:
        self.listbox.delete(0, tk.END)
        self.queue_paths.clear()
        self._refresh_queue_count()
        self._log("queue cleared")

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
                lines.append(f"{label}: MISSING (needed only for that model)")
        lines.append("")
        lines.append(
            f"{TOKEN_LIVE_NONE}: no shaders, d3d11va + gpu-api=d3d11, native window. "
            "FSRCNNX-8 / 16 are the only AI models."
        )
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
        path = self._selected_path()
        if path is None:
            if self.queue_paths:
                messagebox.showerror(APP_NAME, "Select one queue file to play.")
            else:
                messagebox.showerror(APP_NAME, "Add videos to the queue, then select one.")
            return
        if not path.is_file():
            messagebox.showerror(APP_NAME, f"Input not found:\n{path}")
            return
        if not VENDOR_MPV.is_file():
            if messagebox.askyesno(APP_NAME, "mpv is missing. Install now?"):
                self._install()
            return
        profile = self.var_model.get()
        passthrough = profile == "none"
        if not passthrough:
            shader = SHADER_8 if profile == "fsrcnnx8" else SHADER_16
            if not shader.is_file():
                if messagebox.askyesno(APP_NAME, f"{shader.name} is missing. Install now?"):
                    self._install()
                return
        if self._live_is_running():
            self._log("live: stopping previous mpv")
            self._stop()
        if passthrough:
            cmd = [
                str(VENDOR_MPV),
                "--no-config",
                "--force-window=yes",
                "--keep-open=yes",
                "--idle=no",
                "--osc=yes",
                "--osd-level=1",
                "--vo=gpu-next",
                "--gpu-api=d3d11",
                "--hwdec=d3d11va",
                f"--title={APP_NAME} — {TOKEN_LIVE_NONE}",
            ]
            self._log(
                "LIVE_NONE: no shaders, no vf=gpu — native window scale (Chrome-like baseline)"
            )
        else:
            shader = SHADER_8 if profile == "fsrcnnx8" else SHADER_16
            token = "FSRCNNX8" if profile == "fsrcnnx8" else "FSRCNNX16"
            cmd = [
                str(VENDOR_MPV),
                f"--profile={profile}",
                f"--glsl-shaders={shader}",
                "--force-window=yes",
                "--keep-open=yes",
                "--hwdec=auto-copy",
                f"--title={APP_NAME} — {token}",
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

    def _live_is_running(self) -> bool:
        proc = self.player_proc
        return proc is not None and proc.poll() is None

    def _stop(self) -> None:
        proc = self.player_proc
        if proc is None or proc.poll() is not None:
            return
        self._log("live: stop")
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass
        self.player_proc = None

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
