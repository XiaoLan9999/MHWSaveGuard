# -*- coding: utf-8 -*-
"""MHWSaveGuard - GUI save protector for Monster Hunter: World.

Workaround for the case where the game updates:
  <MHW>\savedata_backup\SAVEDATA1000
but Steam userdata does not update:
  <Steam>\userdata\<account>\582010\remote\SAVEDATA1000
"""

from __future__ import annotations

import ctypes
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
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

APP_NAME = "MHWSaveGuard"
APP_VERSION = "0.2.0"
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


def dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def file_brief(path: Path) -> str:
    if not path.exists():
        return "不存在"
    st = path.stat()
    return f"{dt(st.st_mtime)} / {st.st_size:,} bytes / sha256={sha256(path)[:12]}..."


def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def wait_stable(path: Path, stable_seconds=2.0, timeout=30.0) -> bool:
    start = time.time()
    last = None
    stable_at = None
    while time.time() - start < timeout:
        if not path.exists():
            time.sleep(0.25)
            continue
        st = path.stat()
        cur = (st.st_size, st.st_mtime_ns)
        if cur == last:
            if stable_at is None:
                stable_at = time.time()
            if time.time() - stable_at >= stable_seconds:
                return True
        else:
            last = cur
            stable_at = None
        time.sleep(0.25)
    return False


def process_running() -> bool:
    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        cp = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}"], capture_output=True, text=True, timeout=5, creationflags=flags)
        return GAME_EXE.lower() in cp.stdout.lower()
    except Exception:
        return False


def copy_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".mhwsg_tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def simple_vdf_paths(text: str):
    # enough for libraryfolders.vdf: "path" "D:\\SteamLibrary"
    return [m.group(1).replace("\\\\", "\\") for m in re.finditer(r'"path"\s+"([^"]+)"', text)]


def find_steam_candidates():
    c = [Path(r"D:\Steam"), Path(r"C:\Steam"), Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    return [p for p in c if (p / "steam.exe").exists() or (p / "Steam.exe").exists()]


def steam_libraries(steam_root: Path):
    libs = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            for s in simple_vdf_paths(vdf.read_text(encoding="utf-8", errors="ignore")):
                p = Path(s)
                if p.exists() and p not in libs:
                    libs.append(p)
        except Exception:
            pass
    for d in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        p = Path(f"{d}:\\SteamLibrary")
        if p.exists() and p not in libs:
            libs.append(p)
    return libs


def find_mhw(steam_root: Path) -> Path | None:
    for lib in steam_libraries(steam_root):
        manifest = lib / "steamapps" / f"appmanifest_{APPID}.acf"
        if manifest.exists():
            try:
                txt = manifest.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'"installdir"\s+"([^"]+)"', txt)
                name = m.group(1) if m else "Monster Hunter World"
                p = lib / "steamapps" / "common" / name
                if (p / GAME_EXE).exists():
                    return p
            except Exception:
                pass
        p = lib / "steamapps" / "common" / "Monster Hunter World"
        if (p / GAME_EXE).exists():
            return p
    return None


def account_to_steamid64(account: str) -> str:
    try:
        return str(STEAMID64_BASE + int(account))
    except Exception:
        return ""


def fetch_steam_name(steamid64: str) -> tuple[str, str]:
    if not steamid64:
        return "", ""
    try:
        req = urllib.request.Request(f"https://steamcommunity.com/profiles/{steamid64}/?xml=1", headers={"User-Agent": APP_NAME})
        with urllib.request.urlopen(req, timeout=8) as r:
            root = ET.fromstring(r.read())
        return (root.findtext("steamID") or "", root.findtext("onlineState") or "")
    except Exception as e:
        return (f"读取失败: {e}", "")


def char_candidates(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        raw = path.read_bytes()
    except Exception:
        return ""
    out = []
    for enc in ("utf-16le", "utf-8"):
        try:
            text = raw.decode(enc, errors="ignore")
            for m in re.finditer(r"[\u3040-\u30ff\u3400-\u9fffA-Za-z0-9_\- ]{3,16}", text):
                s = m.group(0).strip()
                if s and s not in out:
                    out.append(s)
                if len(out) >= 4:
                    return ", ".join(out)
        except Exception:
            pass
    return ", ".join(out)


class Guard:
    def __init__(self, log):
        self.log = log
        self.lock = threading.RLock()

    def snapshot(self, backup_save: Path, remote_save: Path, reason: str) -> Path:
        with self.lock:
            folder = tool_dir() / "backups" / f"{stamp()}_{reason}"
            folder.mkdir(parents=True, exist_ok=True)
            manifest = {"reason": reason, "created_at": datetime.now().isoformat(timespec="seconds"), "files": {}}
            if backup_save.exists():
                dst = folder / "SAVEDATA1000_from_game_savedata_backup"
                shutil.copy2(backup_save, dst)
                manifest["files"]["game_backup"] = {"path": str(backup_save), "sha256": sha256(dst), "size": dst.stat().st_size}
            else:
                manifest["files"]["game_backup"] = {"path": str(backup_save), "exists": False}
            if remote_save.exists():
                dst = folder / "SAVEDATA1000_from_steam_remote"
                shutil.copy2(remote_save, dst)
                manifest["files"]["steam_remote"] = {"path": str(remote_save), "sha256": sha256(dst), "size": dst.stat().st_size}
            else:
                manifest["files"]["steam_remote"] = {"path": str(remote_save), "exists": False}
            write_json(folder / "manifest.json", manifest)
            self.log(f"已创建快照: {folder}")
            return folder

    def sync(self, backup_save: Path, remote_save: Path, reason: str) -> bool:
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
        self.geometry("1100x720")
        self.minsize(980, 620)
        self.config_path = tool_dir() / CONFIG_NAME
        self.cfg = read_json(self.config_path, {})
        self.queue = queue.Queue()
        self.guard = Guard(lambda m: self.queue.put(("log", m)))
        self.monitor_stop = threading.Event()
        self.monitor_thread = None
        self.was_running = process_running()
        self.last_remote_sha = None
        self.last_backup_mtime = None
        self.users = {}
        self._vars()
        self._ui()
        self.after(200, self._pump)
        self.after(500, self.autodetect_initial)

    def _vars(self):
        steam = self.cfg.get("steam_root") or (str(find_steam_candidates()[0]) if find_steam_candidates() else "")
        self.steam_var = tk.StringVar(value=steam)
        self.game_var = tk.StringVar(value=self.cfg.get("game_dir", ""))
        self.backup_var = tk.StringVar(value=self.cfg.get("backup_save", ""))
        self.remote_var = tk.StringVar(value=self.cfg.get("remote_save", ""))
        self.account_var = tk.StringVar(value=self.cfg.get("account_id", ""))
        self.poll_var = tk.IntVar(value=int(self.cfg.get("poll", 2)))
        self.snap_close_var = tk.BooleanVar(value=bool(self.cfg.get("snapshot_on_close", True)))
        self.sync_close_var = tk.BooleanVar(value=bool(self.cfg.get("sync_on_close", True)))
        self.rollback_var = tk.BooleanVar(value=bool(self.cfg.get("rollback_guard", True)))
        self.sync_running_var = tk.BooleanVar(value=bool(self.cfg.get("sync_while_running", False)))
        self.online_var = tk.BooleanVar(value=bool(self.cfg.get("online_profiles", True)))

    def save_cfg(self):
        self.cfg = {
            "steam_root": self.steam_var.get(), "game_dir": self.game_var.get(), "backup_save": self.backup_var.get(),
            "remote_save": self.remote_var.get(), "account_id": self.account_var.get(), "poll": self.poll_var.get(),
            "snapshot_on_close": self.snap_close_var.get(), "sync_on_close": self.sync_close_var.get(),
            "rollback_guard": self.rollback_var.get(), "sync_while_running": self.sync_running_var.get(),
            "online_profiles": self.online_var.get(),
        }
        write_json(self.config_path, self.cfg)
        self.log(f"配置已保存: {self.config_path}")

    def _ui(self):
        root = ttk.Frame(self, padding=10); root.pack(fill="both", expand=True)
        head = ttk.Frame(root); head.pack(fill="x")
        ttk.Label(head, text=APP_NAME, font=("Microsoft YaHei UI", 20, "bold")).pack(side="left")
        self.monitor_label = ttk.Label(head, text="监控未启动", foreground="#a33"); self.monitor_label.pack(side="right")
        self.nb = ttk.Notebook(root); self.nb.pack(fill="both", expand=True, pady=(10,0))
        self.tab1 = ttk.Frame(self.nb, padding=10); self.tab2 = ttk.Frame(self.nb, padding=10); self.tab3 = ttk.Frame(self.nb, padding=10); self.tab4 = ttk.Frame(self.nb, padding=10)
        self.nb.add(self.tab1, text="1 Steam 与游戏"); self.nb.add(self.tab2, text="2 选择 userdata"); self.nb.add(self.tab3, text="3 保护与同步"); self.nb.add(self.tab4, text="日志")
        self._tab1(); self._tab2(); self._tab3(); self._tab4()

    def row(self, parent, r, label, var, cmd):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=var).grid(row=r, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(parent, text="选择", command=cmd).grid(row=r, column=2, pady=5)

    def _tab1(self):
        self.row(self.tab1, 0, "Steam 根目录", self.steam_var, self.choose_steam)
        self.row(self.tab1, 1, "MHW 游戏目录", self.game_var, self.choose_game)
        self.row(self.tab1, 2, "游戏 backup 存档", self.backup_var, self.choose_backup)
        b = ttk.Frame(self.tab1); b.grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Button(b, text="自动查找 MHW", command=self.find_game).pack(side="left", padx=(0,8))
        ttk.Button(b, text="扫描 userdata", command=lambda: (self.scan_users(), self.nb.select(self.tab2))).pack(side="left", padx=(0,8))
        ttk.Button(b, text="保存配置", command=self.save_cfg).pack(side="left", padx=(0,8))
        ttk.Button(b, text="启动 MHW", command=self.launch_game).pack(side="left", padx=(0,8))
        ttk.Label(self.tab1, text="选择 Steam 后会自动读取库文件并定位 Monster Hunter World。", foreground="#555").grid(row=4, column=0, columnspan=3, sticky="w")

    def _tab2(self):
        top = ttk.Frame(self.tab2); top.pack(fill="x", pady=(0,8))
        ttk.Button(top, text="扫描 userdata", command=self.scan_users).pack(side="left", padx=(0,8))
        ttk.Button(top, text="联网刷新 Steam 昵称", command=self.refresh_profiles).pack(side="left", padx=(0,8))
        ttk.Checkbutton(top, text="允许联网读取公开 Steam 资料", variable=self.online_var).pack(side="left")
        cols = ("account", "steamid64", "name", "state", "has", "char", "mtime")
        self.tree = ttk.Treeview(self.tab2, columns=cols, show="headings", height=16)
        for c, t, w in [("account","AccountID",100),("steamid64","SteamID64",150),("name","Steam昵称",180),("state","状态",80),("has","MHW存档",70),("char","角色名候选",170),("mtime","remote修改时间/大小",260)]:
            self.tree.heading(c, text=t); self.tree.column(c, width=w, stretch=c in ("name","char","mtime"))
        self.tree.pack(fill="both", expand=True); self.tree.bind("<<TreeviewSelect>>", self.select_user)
        ttk.Label(self.tab2, text="角色名候选只是从二进制存档中扫描出的可打印字符串，不用于自动选择。", foreground="#666").pack(anchor="w", pady=(8,0))

    def _tab3(self):
        self.row(self.tab3, 0, "Steam remote 主存档", self.remote_var, self.choose_remote)
        opt = ttk.LabelFrame(self.tab3, text="保护选项", padding=10); opt.grid(row=1, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Checkbutton(opt, text="游戏关闭后在工具目录 backups 下创建快照", variable=self.snap_close_var).pack(anchor="w")
        ttk.Checkbutton(opt, text="游戏关闭后自动将 backup 同步到 remote", variable=self.sync_close_var).pack(anchor="w")
        ttk.Checkbutton(opt, text="回档保护：游戏未运行时，remote 被改写就先备份再恢复 backup", variable=self.rollback_var).pack(anchor="w")
        ttk.Checkbutton(opt, text="游戏运行中 backup 更新也自动同步（更激进）", variable=self.sync_running_var).pack(anchor="w")
        p = ttk.Frame(opt); p.pack(anchor="w", pady=(6,0)); ttk.Label(p,text="轮询间隔").pack(side="left"); ttk.Spinbox(p,from_=1,to=30,textvariable=self.poll_var,width=6).pack(side="left", padx=4); ttk.Label(p,text="秒").pack(side="left")
        btn = ttk.Frame(self.tab3); btn.grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Button(btn, text="立即创建快照", command=lambda: self.guard.snapshot(Path(self.backup_var.get()), Path(self.remote_var.get()), "manual_snapshot")).pack(side="left", padx=(0,8))
        ttk.Button(btn, text="立即同步 backup → remote", command=self.manual_sync).pack(side="left", padx=(0,8))
        self.mon_btn = ttk.Button(btn, text="启动监控", command=self.toggle_monitor); self.mon_btn.pack(side="left", padx=(0,8))
        ttk.Button(btn, text="打开 backups 文件夹", command=self.open_backups).pack(side="left", padx=(0,8))
        ttk.Button(btn, text="刷新状态", command=self.refresh_status).pack(side="left", padx=(0,8))
        box = ttk.LabelFrame(self.tab3, text="当前状态", padding=8); box.grid(row=3, column=0, columnspan=3, sticky="nsew"); self.tab3.rowconfigure(3, weight=1)
        self.status = tk.Text(box, height=16, wrap="word"); self.status.pack(fill="both", expand=True); self.status.configure(state="disabled")

    def _tab4(self):
        top = ttk.Frame(self.tab4); top.pack(fill="x", pady=(0,8))
        ttk.Button(top, text="清空日志", command=lambda: self.log_text.delete("1.0", "end")).pack(side="left", padx=(0,8))
        ttk.Button(top, text="打开工具目录", command=lambda: os.startfile(tool_dir())).pack(side="left")
        self.log_text = tk.Text(self.tab4, wrap="word"); self.log_text.pack(fill="both", expand=True)
        self.log(f"{APP_NAME} v{APP_VERSION} 已启动，工具目录: {tool_dir()}")

    def autodetect_initial(self):
        if self.steam_var.get() and not self.game_var.get(): self.find_game(silent=True)
        if self.steam_var.get(): self.scan_users(silent=True)
        self.refresh_status()

    def choose_steam(self):
        p = filedialog.askdirectory(title="选择 Steam 根目录")
        if p: self.steam_var.set(p); self.find_game(); self.scan_users(); self.nb.select(self.tab2)

    def choose_game(self):
        p = filedialog.askdirectory(title="选择 Monster Hunter World 游戏目录")
        if p: self.game_var.set(p); self.backup_var.set(str(Path(p)/"savedata_backup"/"SAVEDATA1000")); self.refresh_status()

    def choose_backup(self):
        p = filedialog.askopenfilename(title="选择 savedata_backup 里的 SAVEDATA1000")
        if p: self.backup_var.set(p); self.refresh_status()

    def choose_remote(self):
        p = filedialog.askopenfilename(title="选择 Steam userdata remote 里的 SAVEDATA1000")
        if p: self.remote_var.set(p); self.refresh_status()

    def find_game(self, silent=False):
        p = find_mhw(Path(self.steam_var.get()))
        if p:
            self.game_var.set(str(p)); self.backup_var.set(str(p/"savedata_backup"/"SAVEDATA1000")); self.log(f"已找到 MHW: {p}"); self.save_cfg()
        elif not silent: messagebox.showwarning(APP_NAME, "没有自动找到 MHW，请手动选择。")
        self.refresh_status()

    def scan_users(self, silent=False):
        root = Path(self.steam_var.get())/"userdata"
        self.tree.delete(*self.tree.get_children()); self.users.clear()
        if not root.exists():
            if not silent: messagebox.showerror(APP_NAME, f"找不到 userdata: {root}")
            return
        for d in sorted(root.iterdir(), key=lambda x:x.name):
            if not d.is_dir() or not d.name.isdigit(): continue
            account = d.name; sid = account_to_steamid64(account); remote = d/APPID/"remote"/"SAVEDATA1000"
            has = remote.exists(); info = file_brief(remote) if has else "不存在"; cand = char_candidates(remote) if has else ""
            self.users[account] = {"sid": sid, "remote": str(remote)}
            self.tree.insert("", "end", iid=account, values=(account, sid, "未联网读取", "", "有" if has else "无", cand, info))
        self.log(f"已扫描 userdata: {len(self.users)} 个目录")

    def refresh_profiles(self):
        if not self.online_var.get(): self.log("已关闭联网读取。"); return
        if not self.users: self.scan_users(silent=True)
        threading.Thread(target=self._profile_worker, daemon=True).start()

    def _profile_worker(self):
        self.queue.put(("log", "开始联网读取 Steam 公开资料..."))
        for account, data in self.users.items():
            name, state = fetch_steam_name(data["sid"])
            self.queue.put(("profile", (account, name, state)))
        self.queue.put(("log", "Steam 资料刷新完成。"))

    def select_user(self, _=None):
        sel = self.tree.selection()
        if not sel: return
        account = sel[0]; self.account_var.set(account); self.remote_var.set(self.users[account]["remote"]); self.save_cfg(); self.log(f"已选择 userdata: {account}"); self.nb.select(self.tab3); self.refresh_status()

    def manual_sync(self):
        self.save_cfg()
        ok = self.guard.sync(Path(self.backup_var.get()), Path(self.remote_var.get()), "manual")
        self.refresh_status()
        if ok: messagebox.showinfo(APP_NAME, "同步完成。")

    def toggle_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_stop.set(); self.monitor_thread = None; self.mon_btn.configure(text="启动监控"); self.monitor_label.configure(text="监控未启动", foreground="#a33"); self.log("已请求停止监控。")
            return
        self.save_cfg(); self.monitor_stop.clear(); self.was_running = process_running(); self.monitor_thread = threading.Thread(target=self.monitor, daemon=True); self.monitor_thread.start(); self.mon_btn.configure(text="停止监控"); self.monitor_label.configure(text="监控运行中", foreground="#080"); self.log("监控已启动。")

    def monitor(self):
        while not self.monitor_stop.is_set():
            try:
                running = process_running(); backup = Path(self.backup_var.get()); remote = Path(self.remote_var.get())
                if backup.exists():
                    mt = backup.stat().st_mtime_ns
                    if self.last_backup_mtime is None: self.last_backup_mtime = mt
                    elif mt != self.last_backup_mtime:
                        self.last_backup_mtime = mt; self.queue.put(("log", "检测到游戏 backup 更新。"))
                        if self.sync_running_var.get(): self.guard.sync(backup, remote, "backup_changed_while_running")
                if self.was_running and not running:
                    self.queue.put(("log", "检测到 MHW 已关闭，执行关闭后保护流程。"))
                    if self.snap_close_var.get(): self.guard.snapshot(backup, remote, "game_closed")
                    if self.sync_close_var.get() and backup.exists():
                        if (not remote.exists()) or sha256(backup) != sha256(remote): self.guard.sync(backup, remote, "game_closed")
                        else: self.queue.put(("log", "backup 与 remote 已一致。"))
                    self.queue.put(("status", None))
                self.was_running = running
                if (not running) and self.rollback_var.get() and backup.exists() and remote.exists():
                    rs = sha256(remote)
                    if self.last_remote_sha is None: self.last_remote_sha = rs
                    elif rs != self.last_remote_sha:
                        self.last_remote_sha = rs; self.queue.put(("log", "检测到游戏未运行时 remote 被改写，执行回档保护检查。"))
                        if sha256(backup) != sha256(remote): self.guard.sync(backup, remote, "rollback_guard")
                        self.queue.put(("status", None))
                time.sleep(max(1, int(self.poll_var.get())))
            except Exception as e:
                self.queue.put(("log", f"监控异常: {e}")); time.sleep(3)
        self.queue.put(("log", "监控已停止。"))

    def refresh_status(self):
        backup = Path(self.backup_var.get()); remote = Path(self.remote_var.get())
        same = "未知"
        if backup.exists() and remote.exists(): same = "一致" if sha256(backup) == sha256(remote) else "不一致"
        data = {"Steam": self.steam_var.get(), "MHW": self.game_var.get(), "AccountID": self.account_var.get(), "backup": file_brief(backup), "remote": file_brief(remote), "backup_vs_remote": same, "game_running": process_running(), "tool_backups": str(tool_dir()/"backups")}
        self.status.configure(state="normal"); self.status.delete("1.0", "end"); self.status.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2)); self.status.configure(state="disabled")

    def launch_game(self):
        try: os.startfile(f"steam://rungameid/{APPID}"); self.log("已请求 Steam 启动 MHW。")
        except Exception as e: messagebox.showerror(APP_NAME, str(e))

    def open_backups(self):
        p = tool_dir()/"backups"; p.mkdir(exist_ok=True); os.startfile(p)

    def _pump(self):
        try:
            while True:
                k, v = self.queue.get_nowait()
                if k == "log": self.log(str(v))
                elif k == "status": self.refresh_status()
                elif k == "profile":
                    account, name, state = v
                    if self.tree.exists(account):
                        vals = list(self.tree.item(account, "values")); vals[2] = name; vals[3] = state; self.tree.item(account, values=vals)
        except queue.Empty: pass
        self.after(150, self._pump)

    def log(self, msg):
        self.log_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"); self.log_text.see("end")

    def close(self):
        self.save_cfg(); self.monitor_stop.set(); self.destroy()


def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    app = App(); app.protocol("WM_DELETE_WINDOW", app.close); app.mainloop()


if __name__ == "__main__":
    main()
