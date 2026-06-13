# -*- coding: utf-8 -*-
r"""MHWSaveGuard - GUI save protector for Monster Hunter: World.

This tool is a workaround for the MHW save issue where the game updates
savedata_backup/SAVEDATA1000 but Steam userdata remote/SAVEDATA1000 does not.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "MHWSaveGuard"
APP_VERSION = "0.2.1"
APPID = "582010"
GAME_EXE = "MonsterHunterWorld.exe"
STEAMID64_BASE = 76561197960265728
CONFIG_NAME = "mhw_save_guard_config.json"


def tool_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_brief(path: Path) -> str:
    if not path.exists():
        return "不存在"
    st = path.stat()
    return f"{fmt_time(st.st_mtime)} / {st.st_size:,} bytes / sha256={sha256(path)[:12]}..."


def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def wait_stable(path: Path, stable_seconds: float = 2.0, timeout: float = 30.0) -> bool:
    start = time.time()
    last = None
    stable_at = None
    while time.time() - start < timeout:
        if not path.exists():
            time.sleep(0.25)
            continue
        st = path.stat()
        current = (st.st_size, st.st_mtime_ns)
        if current == last:
            if stable_at is None:
                stable_at = time.time()
            if time.time() - stable_at >= stable_seconds:
                return True
        else:
            last = current
            stable_at = None
        time.sleep(0.25)
    return False


def process_running() -> bool:
    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        cp = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=flags,
        )
        return GAME_EXE.lower() in cp.stdout.lower()
    except Exception:
        return False


def copy_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".mhwsg_tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def steam_candidates() -> list[Path]:
    candidates = [
        Path(r"D:\Steam"),
        Path(r"C:\Steam"),
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]
    return [p for p in candidates if (p / "steam.exe").exists() or (p / "Steam.exe").exists()]


def steam_libraries(steam_root: Path) -> list[Path]:
    libs = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                p = Path(m.group(1).replace("\\\\", "\\"))
                if p.exists() and p not in libs:
                    libs.append(p)
        except Exception:
            pass
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        p = Path(f"{drive}:\\SteamLibrary")
        if p.exists() and p not in libs:
            libs.append(p)
    return libs


def find_mhw(steam_root: Path) -> Path | None:
    for lib in steam_libraries(steam_root):
        manifest = lib / "steamapps" / f"appmanifest_{APPID}.acf"
        if manifest.exists():
            try:
                text = manifest.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'"installdir"\s+"([^"]+)"', text)
                folder_name = m.group(1) if m else "Monster Hunter World"
                game = lib / "steamapps" / "common" / folder_name
                if (game / GAME_EXE).exists():
                    return game
            except Exception:
                pass
        fallback = lib / "steamapps" / "common" / "Monster Hunter World"
        if (fallback / GAME_EXE).exists():
            return fallback
    return None


def account_to_steamid64(account_id: str) -> str:
    try:
        return str(STEAMID64_BASE + int(account_id))
    except Exception:
        return ""


def fetch_steam_profile(steamid64: str) -> tuple[str, str]:
    if not steamid64:
        return "", ""
    try:
        req = urllib.request.Request(
            f"https://steamcommunity.com/profiles/{steamid64}/?xml=1",
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            root = ET.fromstring(resp.read())
        return root.findtext("steamID") or "", root.findtext("onlineState") or ""
    except Exception as exc:
        return f"读取失败: {exc}", ""


def char_candidates(save_path: Path) -> str:
    if not save_path.exists():
        return ""
    try:
        raw = save_path.read_bytes()
    except Exception:
        return ""
    found: list[str] = []
    for enc in ("utf-16le", "utf-8"):
        try:
            text = raw.decode(enc, errors="ignore")
            for m in re.finditer(r"[\u3040-\u30ff\u3400-\u9fffA-Za-z0-9_\- ]{3,16}", text):
                item = m.group(0).strip()
                if item and item not in found:
                    found.append(item)
                if len(found) >= 4:
                    return ", ".join(found)
        except Exception:
            pass
    return ", ".join(found)


class SaveGuard:
    def __init__(self, log_func):
        self.log = log_func
        self.lock = threading.RLock()

    def snapshot(self, backup_save: Path, remote_save: Path, reason: str) -> Path:
        with self.lock:
            folder = tool_dir() / "backups" / f"{stamp()}_{reason}"
            folder.mkdir(parents=True, exist_ok=True)
            manifest = {
                "app": APP_NAME,
                "version": APP_VERSION,
                "reason": reason,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "files": {},
            }

            if backup_save.exists():
                dst = folder / "SAVEDATA1000_from_game_savedata_backup"
                shutil.copy2(backup_save, dst)
                manifest["files"]["game_backup"] = {
                    "source_path": str(backup_save),
                    "snapshot_file": dst.name,
                    "size": dst.stat().st_size,
                    "sha256": sha256(dst),
                }
            else:
                manifest["files"]["game_backup"] = {"source_path": str(backup_save), "exists": False}

            if remote_save.exists():
                dst = folder / "SAVEDATA1000_from_steam_remote"
                shutil.copy2(remote_save, dst)
                manifest["files"]["steam_remote"] = {
                    "source_path": str(remote_save),
                    "snapshot_file": dst.name,
                    "size": dst.stat().st_size,
                    "sha256": sha256(dst),
                }
            else:
                manifest["files"]["steam_remote"] = {"source_path": str(remote_save), "exists": False}

            write_json(folder / "manifest.json", manifest)
            self.log(f"已创建快照: {folder}")
            return folder

    def sync_backup_to_remote(self, backup_save: Path, remote_save: Path, reason: str) -> bool:
        with self.lock:
            if not backup_save.exists():
                self.log(f"找不到游戏 backup 存档: {backup_save}")
                return False
            self.log("等待 backup 存档写入稳定...")
            if not wait_stable(backup_save):
                self.log("backup 文件未稳定，取消本次同步。")
                return False
            self.snapshot(backup_save, remote_save, f"before_sync_{reason}")
            copy_atomic(backup_save, remote_save)
            self.log(f"已同步 backup -> remote，原因: {reason}")
            return True


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1120x740")
        self.minsize(980, 620)

        self.config_path = tool_dir() / CONFIG_NAME
        self.cfg = read_json(self.config_path, {})
        self.msgq: queue.Queue = queue.Queue()
        self.guard = SaveGuard(lambda msg: self.msgq.put(("log", msg)))

        self.monitor_stop = threading.Event()
        self.monitor_thread: threading.Thread | None = None
        self.was_running = process_running()
        self.last_remote_hash: str | None = None
        self.last_backup_mtime_ns: int | None = None
        self.users: dict[str, dict[str, str]] = {}

        self._init_vars()
        self._build_ui()
        self.after(200, self._pump)
        self.after(500, self.initial_autodetect)

    def _init_vars(self):
        steam_default = self.cfg.get("steam_root") or (str(steam_candidates()[0]) if steam_candidates() else "")
        self.steam_var = tk.StringVar(value=steam_default)
        self.game_var = tk.StringVar(value=self.cfg.get("game_dir", ""))
        self.backup_var = tk.StringVar(value=self.cfg.get("backup_save", ""))
        self.remote_var = tk.StringVar(value=self.cfg.get("remote_save", ""))
        self.account_var = tk.StringVar(value=self.cfg.get("account_id", ""))
        self.poll_var = tk.IntVar(value=int(self.cfg.get("poll", 2)))
        self.snapshot_on_close_var = tk.BooleanVar(value=bool(self.cfg.get("snapshot_on_close", True)))
        self.sync_on_close_var = tk.BooleanVar(value=bool(self.cfg.get("sync_on_close", True)))
        self.rollback_guard_var = tk.BooleanVar(value=bool(self.cfg.get("rollback_guard", True)))
        self.sync_while_running_var = tk.BooleanVar(value=bool(self.cfg.get("sync_while_running", False)))
        self.online_profiles_var = tk.BooleanVar(value=bool(self.cfg.get("online_profiles", True)))

    def save_config(self):
        data = {
            "steam_root": self.steam_var.get(),
            "game_dir": self.game_var.get(),
            "backup_save": self.backup_var.get(),
            "remote_save": self.remote_var.get(),
            "account_id": self.account_var.get(),
            "poll": self.poll_var.get(),
            "snapshot_on_close": self.snapshot_on_close_var.get(),
            "sync_on_close": self.sync_on_close_var.get(),
            "rollback_guard": self.rollback_guard_var.get(),
            "sync_while_running": self.sync_while_running_var.get(),
            "online_profiles": self.online_profiles_var.get(),
        }
        write_json(self.config_path, data)
        self.log(f"配置已保存: {self.config_path}")

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, font=("Microsoft YaHei UI", 20, "bold")).pack(side="left")
        self.monitor_label = ttk.Label(header, text="监控未启动", foreground="#a33")
        self.monitor_label.pack(side="right")

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, pady=(10, 0))
        self.tab_steam = ttk.Frame(self.tabs, padding=10)
        self.tab_user = ttk.Frame(self.tabs, padding=10)
        self.tab_guard = ttk.Frame(self.tabs, padding=10)
        self.tab_log = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.tab_steam, text="1 Steam 与游戏")
        self.tabs.add(self.tab_user, text="2 选择 userdata")
        self.tabs.add(self.tab_guard, text="3 保护与同步")
        self.tabs.add(self.tab_log, text="日志")

        self._build_steam_tab()
        self._build_user_tab()
        self._build_guard_tab()
        self._build_log_tab()

    def path_row(self, parent, row: int, label: str, var: tk.StringVar, command):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(parent, text="选择", command=command).grid(row=row, column=2, pady=5)

    def _build_steam_tab(self):
        self.path_row(self.tab_steam, 0, "Steam 根目录", self.steam_var, self.choose_steam)
        self.path_row(self.tab_steam, 1, "MHW 游戏目录", self.game_var, self.choose_game)
        self.path_row(self.tab_steam, 2, "游戏 backup 存档", self.backup_var, self.choose_backup)

        row = ttk.Frame(self.tab_steam)
        row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Button(row, text="自动查找 MHW", command=self.find_game).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="扫描 userdata", command=lambda: (self.scan_users(), self.tabs.select(self.tab_user))).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="保存配置", command=self.save_config).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="启动 MHW", command=self.launch_game).pack(side="left", padx=(0, 8))

        ttk.Label(
            self.tab_steam,
            text="选择 Steam 后会自动读取库文件并定位 Monster Hunter World。",
            foreground="#555",
        ).grid(row=4, column=0, columnspan=3, sticky="w")

    def _build_user_tab(self):
        top = ttk.Frame(self.tab_user)
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text="扫描 userdata", command=self.scan_users).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="联网刷新 Steam 昵称", command=self.refresh_profiles).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(top, text="允许联网读取公开 Steam 资料", variable=self.online_profiles_var).pack(side="left")

        cols = ("account", "steamid64", "name", "state", "has", "char", "mtime")
        self.user_tree = ttk.Treeview(self.tab_user, columns=cols, show="headings", height=16)
        headings = [
            ("account", "AccountID", 100),
            ("steamid64", "SteamID64", 150),
            ("name", "Steam昵称", 180),
            ("state", "状态", 80),
            ("has", "MHW存档", 70),
            ("char", "角色名候选", 180),
            ("mtime", "remote修改时间/大小", 280),
        ]
        for key, title, width in headings:
            self.user_tree.heading(key, text=title)
            self.user_tree.column(key, width=width, stretch=key in {"name", "char", "mtime"})
        self.user_tree.pack(fill="both", expand=True)
        self.user_tree.bind("<<TreeviewSelect>>", self.select_user)
        ttk.Label(
            self.tab_user,
            text="角色名候选只是从二进制存档中扫描出的可打印字符串，不用于自动选择。",
            foreground="#666",
        ).pack(anchor="w", pady=(8, 0))

    def _build_guard_tab(self):
        self.path_row(self.tab_guard, 0, "Steam remote 主存档", self.remote_var, self.choose_remote)

        opts = ttk.LabelFrame(self.tab_guard, text="保护选项", padding=10)
        opts.grid(row=1, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Checkbutton(opts, text="游戏关闭后在工具目录 backups 下创建快照", variable=self.snapshot_on_close_var).pack(anchor="w")
        ttk.Checkbutton(opts, text="游戏关闭后自动将 backup 同步到 remote", variable=self.sync_on_close_var).pack(anchor="w")
        ttk.Checkbutton(opts, text="回档保护：游戏未运行时，remote 被改写就先备份再恢复 backup", variable=self.rollback_guard_var).pack(anchor="w")
        ttk.Checkbutton(opts, text="游戏运行中 backup 更新也自动同步（更激进）", variable=self.sync_while_running_var).pack(anchor="w")

        poll_row = ttk.Frame(opts)
        poll_row.pack(anchor="w", pady=(6, 0))
        ttk.Label(poll_row, text="轮询间隔").pack(side="left")
        ttk.Spinbox(poll_row, from_=1, to=30, textvariable=self.poll_var, width=6).pack(side="left", padx=4)
        ttk.Label(poll_row, text="秒").pack(side="left")

        buttons = ttk.Frame(self.tab_guard)
        buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Button(buttons, text="立即创建快照", command=self.manual_snapshot).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="立即同步 backup → remote", command=self.manual_sync).pack(side="left", padx=(0, 8))
        self.monitor_button = ttk.Button(buttons, text="启动监控", command=self.toggle_monitor)
        self.monitor_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="打开 backups 文件夹", command=self.open_backups).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="刷新状态", command=self.refresh_status).pack(side="left", padx=(0, 8))

        box = ttk.LabelFrame(self.tab_guard, text="当前状态", padding=8)
        box.grid(row=3, column=0, columnspan=3, sticky="nsew")
        self.tab_guard.rowconfigure(3, weight=1)
        self.status_text = tk.Text(box, height=16, wrap="word")
        self.status_text.pack(fill="both", expand=True)
        self.status_text.configure(state="disabled")

    def _build_log_tab(self):
        row = ttk.Frame(self.tab_log)
        row.pack(fill="x", pady=(0, 8))
        ttk.Button(row, text="清空日志", command=lambda: self.log_text.delete("1.0", "end")).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="打开工具目录", command=lambda: os.startfile(tool_dir())).pack(side="left")
        self.log_text = tk.Text(self.tab_log, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log(f"{APP_NAME} v{APP_VERSION} 已启动，工具目录: {tool_dir()}")

    def initial_autodetect(self):
        if self.steam_var.get() and not self.game_var.get():
            self.find_game(silent=True)
        if self.steam_var.get():
            self.scan_users(silent=True)
        self.refresh_status()

    def choose_steam(self):
        path = filedialog.askdirectory(title="选择 Steam 根目录")
        if path:
            self.steam_var.set(path)
            self.find_game()
            self.scan_users()
            self.tabs.select(self.tab_user)

    def choose_game(self):
        path = filedialog.askdirectory(title="选择 Monster Hunter World 游戏目录")
        if path:
            self.game_var.set(path)
            self.backup_var.set(str(Path(path) / "savedata_backup" / "SAVEDATA1000"))
            self.refresh_status()

    def choose_backup(self):
        path = filedialog.askopenfilename(title="选择 savedata_backup 里的 SAVEDATA1000")
        if path:
            self.backup_var.set(path)
            self.refresh_status()

    def choose_remote(self):
        path = filedialog.askopenfilename(title="选择 Steam userdata remote 里的 SAVEDATA1000")
        if path:
            self.remote_var.set(path)
            self.refresh_status()

    def find_game(self, silent: bool = False):
        game = find_mhw(Path(self.steam_var.get()))
        if game:
            self.game_var.set(str(game))
            self.backup_var.set(str(game / "savedata_backup" / "SAVEDATA1000"))
            self.log(f"已找到 MHW: {game}")
            self.save_config()
        elif not silent:
            messagebox.showwarning(APP_NAME, "没有自动找到 MHW，请手动选择。")
        self.refresh_status()

    def scan_users(self, silent: bool = False):
        root = Path(self.steam_var.get()) / "userdata"
        self.user_tree.delete(*self.user_tree.get_children())
        self.users.clear()
        if not root.exists():
            if not silent:
                messagebox.showerror(APP_NAME, f"找不到 userdata: {root}")
            return

        for user_dir in sorted(root.iterdir(), key=lambda p: p.name):
            if not user_dir.is_dir() or not user_dir.name.isdigit():
                continue
            account = user_dir.name
            steamid64 = account_to_steamid64(account)
            remote = user_dir / APPID / "remote" / "SAVEDATA1000"
            has = remote.exists()
            info = file_brief(remote) if has else "不存在"
            candidate = char_candidates(remote) if has else ""
            self.users[account] = {"steamid64": steamid64, "remote": str(remote)}
            self.user_tree.insert(
                "",
                "end",
                iid=account,
                values=(account, steamid64, "未联网读取", "", "有" if has else "无", candidate, info),
            )
        self.log(f"已扫描 userdata: {len(self.users)} 个目录")

    def refresh_profiles(self):
        if not self.online_profiles_var.get():
            self.log("已关闭联网读取。")
            return
        if not self.users:
            self.scan_users(silent=True)
        threading.Thread(target=self._profile_worker, daemon=True).start()

    def _profile_worker(self):
        self.msgq.put(("log", "开始联网读取 Steam 公开资料..."))
        for account, data in self.users.items():
            name, state = fetch_steam_profile(data["steamid64"])
            self.msgq.put(("profile", (account, name, state)))
        self.msgq.put(("log", "Steam 资料刷新完成。"))

    def select_user(self, _event=None):
        selection = self.user_tree.selection()
        if not selection:
            return
        account = selection[0]
        self.account_var.set(account)
        self.remote_var.set(self.users[account]["remote"])
        self.save_config()
        self.log(f"已选择 userdata: {account}")
        self.tabs.select(self.tab_guard)
        self.refresh_status()

    def manual_snapshot(self):
        self.save_config()
        self.guard.snapshot(Path(self.backup_var.get()), Path(self.remote_var.get()), "manual_snapshot")
        self.refresh_status()

    def manual_sync(self):
        self.save_config()
        ok = self.guard.sync_backup_to_remote(Path(self.backup_var.get()), Path(self.remote_var.get()), "manual")
        self.refresh_status()
        if ok:
            messagebox.showinfo(APP_NAME, "同步完成。")

    def toggle_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_stop.set()
            self.monitor_thread = None
            self.monitor_button.configure(text="启动监控")
            self.monitor_label.configure(text="监控未启动", foreground="#a33")
            self.log("已请求停止监控。")
            return

        self.save_config()
        self.monitor_stop.clear()
        self.was_running = process_running()
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.monitor_button.configure(text="停止监控")
        self.monitor_label.configure(text="监控运行中", foreground="#080")
        self.log("监控已启动。")

    def monitor_loop(self):
        while not self.monitor_stop.is_set():
            try:
                running = process_running()
                backup = Path(self.backup_var.get())
                remote = Path(self.remote_var.get())

                if backup.exists():
                    mtime_ns = backup.stat().st_mtime_ns
                    if self.last_backup_mtime_ns is None:
                        self.last_backup_mtime_ns = mtime_ns
                    elif mtime_ns != self.last_backup_mtime_ns:
                        self.last_backup_mtime_ns = mtime_ns
                        self.msgq.put(("log", "检测到游戏 backup 更新。"))
                        if self.sync_while_running_var.get():
                            self.guard.sync_backup_to_remote(backup, remote, "backup_changed_while_running")

                if self.was_running and not running:
                    self.msgq.put(("log", "检测到 MHW 已关闭，执行关闭后保护流程。"))
                    if self.snapshot_on_close_var.get():
                        self.guard.snapshot(backup, remote, "game_closed")
                    if self.sync_on_close_var.get() and backup.exists():
                        if (not remote.exists()) or sha256(backup) != sha256(remote):
                            self.guard.sync_backup_to_remote(backup, remote, "game_closed")
                        else:
                            self.msgq.put(("log", "backup 与 remote 已一致。"))
                    self.msgq.put(("status", None))

                self.was_running = running

                if (not running) and self.rollback_guard_var.get() and backup.exists() and remote.exists():
                    current_remote_hash = sha256(remote)
                    if self.last_remote_hash is None:
                        self.last_remote_hash = current_remote_hash
                    elif current_remote_hash != self.last_remote_hash:
                        self.last_remote_hash = current_remote_hash
                        self.msgq.put(("log", "检测到游戏未运行时 remote 被改写，执行回档保护检查。"))
                        if sha256(backup) != sha256(remote):
                            self.guard.sync_backup_to_remote(backup, remote, "rollback_guard")
                        self.msgq.put(("status", None))

                time.sleep(max(1, int(self.poll_var.get())))
            except Exception as exc:
                self.msgq.put(("log", f"监控异常: {exc}"))
                time.sleep(3)
        self.msgq.put(("log", "监控已停止。"))

    def refresh_status(self):
        backup = Path(self.backup_var.get())
        remote = Path(self.remote_var.get())
        relation = "未知"
        if backup.exists() and remote.exists():
            relation = "一致" if sha256(backup) == sha256(remote) else "不一致"

        data = {
            "Steam": self.steam_var.get(),
            "MHW": self.game_var.get(),
            "AccountID": self.account_var.get(),
            "backup": file_brief(backup),
            "remote": file_brief(remote),
            "backup_vs_remote": relation,
            "game_running": process_running(),
            "tool_backups": str(tool_dir() / "backups"),
        }
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        self.status_text.configure(state="disabled")

    def launch_game(self):
        try:
            os.startfile(f"steam://rungameid/{APPID}")
            self.log("已请求 Steam 启动 MHW。")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def open_backups(self):
        path = tool_dir() / "backups"
        path.mkdir(exist_ok=True)
        os.startfile(path)

    def _pump(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "log":
                    self.log(str(payload))
                elif kind == "status":
                    self.refresh_status()
                elif kind == "profile":
                    account, name, state = payload
                    if self.user_tree.exists(account):
                        values = list(self.user_tree.item(account, "values"))
                        values[2] = name
                        values[3] = state
                        self.user_tree.item(account, values=values)
        except queue.Empty:
            pass
        self.after(150, self._pump)

    def log(self, msg: str):
        self.log_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see("end")

    def close(self):
        self.save_config()
        self.monitor_stop.set()
        self.destroy()


def main():
    try:
        # On Windows this improves scaling on high-DPI screens. It is ignored elsewhere.
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.close)
    app.mainloop()


if __name__ == "__main__":
    main()
