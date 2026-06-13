# -*- coding: utf-8 -*-
r"""MHWSaveGuard - GUI save protector for Monster Hunter: World."""

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
from tkinter import font as tkfont

APP_NAME = "MHWSaveGuard"
APP_VERSION = "0.3.0"
APPID = "582010"
GAME_EXE = "MonsterHunterWorld.exe"
STEAMID64_BASE = 76561197960265728
CONFIG_NAME = "mhw_save_guard_config.json"

SKY_BG = "#EAF7FF"
CARD_BG = "#F7FCFF"
PANEL_BG = "#DDF4FF"
PRIMARY = "#23A7E6"
PRIMARY_DARK = "#167FB4"
TEXT = "#123047"
MUTED = "#5B7485"
DANGER = "#D95454"
SUCCESS = "#23966E"

I18N = {
    "zh": {
        "language": "语言", "lang_zh": "中", "lang_en": "英", "lang_ja": "日", "monitor_off": "监控未启动", "monitor_on": "监控运行中",
        "tab_steam": "1 Steam 与游戏", "tab_user": "2 选择 userdata", "tab_guard": "3 保护与同步", "tab_log": "日志",
        "steam_root": "Steam 根目录", "game_dir": "MHW 游戏目录", "backup_save": "游戏 backup 存档", "remote_save": "Steam remote 主存档",
        "choose": "选择", "auto_find": "自动查找 MHW", "scan_userdata": "扫描 userdata", "save_config": "保存配置", "launch_game": "启动 MHW",
        "steam_help": "选择 Steam 后会自动读取库文件并定位 Monster Hunter World。", "refresh_profiles": "联网刷新 Steam 昵称", "allow_online": "允许联网读取公开 Steam 资料",
        "account": "AccountID", "steamid64": "SteamID64", "steam_name": "Steam昵称", "state": "状态", "has_save": "MHW存档", "remote_info": "remote修改时间/大小", "remote_path": "remote路径",
        "user_hint": "已隐藏角色名候选扫描：MHW 存档是二进制文件，强行扫描容易出现乱码。请按 Steam昵称 / AccountID / 修改时间判断。",
        "options": "保护选项", "snap_close": "游戏关闭后在工具目录 backups 下创建快照", "sync_close": "游戏关闭后自动将 backup 同步到 remote", "rollback": "回档保护：游戏未运行时，remote 被改写就先备份再恢复 backup", "sync_running": "游戏运行中 backup 更新也自动同步（更激进）", "poll": "轮询间隔", "sec": "秒",
        "manual_snapshot": "立即创建快照", "manual_sync": "立即同步 backup → remote", "start_monitor": "启动监控", "stop_monitor": "停止监控", "open_backups": "打开 backups 文件夹", "refresh_status": "刷新状态", "status": "当前状态", "clear_log": "清空日志", "open_tool_dir": "打开工具目录",
        "yes": "有", "no": "无", "missing": "不存在", "not_loaded": "未联网读取", "same": "一致", "different": "不一致", "unknown": "未知", "done": "完成", "sync_done": "同步完成。",
        "no_steam": "找不到 userdata 目录", "no_mhw": "没有自动找到 MHW，请手动选择。", "created_snapshot": "已创建快照", "saved_config": "配置已保存", "found_mhw": "已找到 MHW", "scanned_users": "已扫描 userdata", "chosen_user": "已选择 userdata", "online_start": "开始联网读取 Steam 公开资料...", "online_done": "Steam 资料刷新完成。", "online_disabled": "已关闭联网读取。", "monitor_started": "监控已启动。", "monitor_stop_req": "已请求停止监控。", "monitor_stopped": "监控已停止。", "game_closed": "检测到 MHW 已关闭，执行关闭后保护流程。", "backup_changed": "检测到游戏 backup 更新。", "remote_changed": "检测到游戏未运行时 remote 被改写，执行回档保护检查。", "backup_same": "backup 与 remote 已一致。", "wait_stable": "等待 backup 存档写入稳定...", "unstable": "backup 文件未稳定，取消本次同步。", "backup_missing": "找不到游戏 backup 存档", "synced": "已同步 backup -> remote，原因", "error_monitor": "监控异常", "started": "已启动，工具目录", "launch_requested": "已请求 Steam 启动 MHW。",
    },
    "en": {
        "language": "Language", "lang_zh": "CN", "lang_en": "EN", "lang_ja": "JP", "monitor_off": "Monitor off", "monitor_on": "Monitor running",
        "tab_steam": "1 Steam & Game", "tab_user": "2 Select userdata", "tab_guard": "3 Guard & Sync", "tab_log": "Log",
        "steam_root": "Steam root", "game_dir": "MHW game folder", "backup_save": "Game backup save", "remote_save": "Steam remote save",
        "choose": "Choose", "auto_find": "Auto-detect MHW", "scan_userdata": "Scan userdata", "save_config": "Save config", "launch_game": "Launch MHW",
        "steam_help": "Choose Steam root, then the tool will scan library folders and locate Monster Hunter World.", "refresh_profiles": "Refresh Steam names", "allow_online": "Allow online public Steam profile lookup",
        "account": "AccountID", "steamid64": "SteamID64", "steam_name": "Steam name", "state": "State", "has_save": "MHW save", "remote_info": "remote modified/size", "remote_path": "remote path",
        "user_hint": "Character-name scanning is hidden: MHW saves are binary and raw scanning often produces garbled text. Use Steam name / AccountID / modified time instead.",
        "options": "Guard options", "snap_close": "Create a snapshot under backups after the game closes", "sync_close": "Sync backup to remote after the game closes", "rollback": "Rollback guard: if remote changes while game is not running, snapshot first and restore backup", "sync_running": "Also sync when backup changes while game is running (aggressive)", "poll": "Polling interval", "sec": "sec",
        "manual_snapshot": "Create snapshot now", "manual_sync": "Sync backup → remote now", "start_monitor": "Start monitor", "stop_monitor": "Stop monitor", "open_backups": "Open backups folder", "refresh_status": "Refresh status", "status": "Status", "clear_log": "Clear log", "open_tool_dir": "Open tool folder",
        "yes": "Yes", "no": "No", "missing": "Missing", "not_loaded": "Not loaded", "same": "Same", "different": "Different", "unknown": "Unknown", "done": "Done", "sync_done": "Sync completed.",
        "no_steam": "userdata folder not found", "no_mhw": "MHW was not found automatically. Please choose it manually.", "created_snapshot": "Snapshot created", "saved_config": "Config saved", "found_mhw": "Found MHW", "scanned_users": "Scanned userdata", "chosen_user": "Selected userdata", "online_start": "Reading public Steam profiles...", "online_done": "Steam profile refresh completed.", "online_disabled": "Online lookup is disabled.", "monitor_started": "Monitor started.", "monitor_stop_req": "Stop requested.", "monitor_stopped": "Monitor stopped.", "game_closed": "MHW closed; running post-close guard flow.", "backup_changed": "Game backup changed.", "remote_changed": "Remote changed while game is not running; checking rollback guard.", "backup_same": "backup and remote are already the same.", "wait_stable": "Waiting for backup save to become stable...", "unstable": "Backup file is not stable; sync cancelled.", "backup_missing": "Game backup save not found", "synced": "Synced backup -> remote, reason", "error_monitor": "Monitor error", "started": "started, tool folder", "launch_requested": "Requested Steam to launch MHW.",
    },
    "ja": {
        "language": "言語", "lang_zh": "中", "lang_en": "英", "lang_ja": "日", "monitor_off": "監視停止中", "monitor_on": "監視中",
        "tab_steam": "1 Steam とゲーム", "tab_user": "2 userdata 選択", "tab_guard": "3 保護と同期", "tab_log": "ログ",
        "steam_root": "Steam ルート", "game_dir": "MHW フォルダー", "backup_save": "ゲーム backup セーブ", "remote_save": "Steam remote セーブ",
        "choose": "選択", "auto_find": "MHW 自動検索", "scan_userdata": "userdata をスキャン", "save_config": "設定を保存", "launch_game": "MHW 起動",
        "steam_help": "Steam ルートを選択すると、ライブラリを読み取り Monster Hunter World を探します。", "refresh_profiles": "Steam名を更新", "allow_online": "公開 Steam 情報の取得を許可",
        "account": "AccountID", "steamid64": "SteamID64", "steam_name": "Steam名", "state": "状態", "has_save": "MHWセーブ", "remote_info": "remote更新日時/サイズ", "remote_path": "remoteパス",
        "user_hint": "キャラ名候補のスキャンは非表示です。MHWセーブはバイナリのため、無理に読むと文字化けしやすいです。Steam名 / AccountID / 更新日時で判断してください。",
        "options": "保護オプション", "snap_close": "ゲーム終了後、backups にスナップショットを作成", "sync_close": "ゲーム終了後、backup を remote に同期", "rollback": "巻き戻り保護：ゲーム未実行時に remote が変更されたら、先に保存して backup で復元", "sync_running": "ゲーム実行中の backup 更新も同期する（強め）", "poll": "監視間隔", "sec": "秒",
        "manual_snapshot": "今すぐスナップショット", "manual_sync": "backup → remote 同期", "start_monitor": "監視開始", "stop_monitor": "監視停止", "open_backups": "backups を開く", "refresh_status": "状態更新", "status": "現在の状態", "clear_log": "ログ消去", "open_tool_dir": "ツールフォルダーを開く",
        "yes": "あり", "no": "なし", "missing": "存在しません", "not_loaded": "未取得", "same": "一致", "different": "不一致", "unknown": "不明", "done": "完了", "sync_done": "同期しました。",
        "no_steam": "userdata フォルダーが見つかりません", "no_mhw": "MHW を自動検出できませんでした。手動で選択してください。", "created_snapshot": "スナップショット作成", "saved_config": "設定を保存しました", "found_mhw": "MHW を検出", "scanned_users": "userdata をスキャン", "chosen_user": "userdata を選択", "online_start": "公開 Steam 情報を取得中...", "online_done": "Steam 情報の更新が完了しました。", "online_disabled": "オンライン取得は無効です。", "monitor_started": "監視を開始しました。", "monitor_stop_req": "監視停止を要求しました。", "monitor_stopped": "監視を停止しました。", "game_closed": "MHW の終了を検出。終了後の保護処理を実行します。", "backup_changed": "ゲーム backup の更新を検出。", "remote_changed": "ゲーム未実行時に remote の変更を検出。巻き戻り保護を確認します。", "backup_same": "backup と remote はすでに一致しています。", "wait_stable": "backup セーブの書き込み安定を待機中...", "unstable": "backup ファイルが安定していないため同期を中止しました。", "backup_missing": "ゲーム backup セーブが見つかりません", "synced": "backup -> remote を同期しました。理由", "error_monitor": "監視エラー", "started": "起動しました。ツールフォルダー", "launch_requested": "Steam に MHW 起動を要求しました。",
    },
}


def tool_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return tool_dir() / relative


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def fmt_time_short(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def fmt_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_brief(path: Path) -> str:
    if not path.exists():
        return "missing"
    st = path.stat()
    return f"{fmt_time(st.st_mtime)} / {fmt_size(st.st_size)} / sha256={sha256(path)[:12]}..."


def file_table_brief(path: Path, missing_text: str) -> str:
    if not path.exists():
        return missing_text
    st = path.stat()
    return f"{fmt_time_short(st.st_mtime)} / {fmt_size(st.st_size)}"


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
        cp = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}"], capture_output=True, text=True, timeout=5, creationflags=flags)
        return GAME_EXE.lower() in cp.stdout.lower()
    except Exception:
        return False


def copy_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".mhwsg_tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def steam_candidates() -> list[Path]:
    candidates = [Path(r"D:\Steam"), Path(r"C:\Steam"), Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
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
        req = urllib.request.Request(f"https://steamcommunity.com/profiles/{steamid64}/?xml=1", headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            root = ET.fromstring(resp.read())
        return root.findtext("steamID") or "", root.findtext("onlineState") or ""
    except Exception as exc:
        return f"error: {exc}", ""


class SaveGuard:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()

    def log(self, msg: str):
        self.app.thread_log(msg)

    def snapshot(self, backup_save: Path, remote_save: Path, reason: str) -> Path:
        with self.lock:
            folder = tool_dir() / "backups" / f"{stamp()}_{reason}"
            folder.mkdir(parents=True, exist_ok=True)
            manifest = {"app": APP_NAME, "version": APP_VERSION, "reason": reason, "created_at": datetime.now().isoformat(timespec="seconds"), "files": {}}
            if backup_save.exists():
                dst = folder / "SAVEDATA1000_from_game_savedata_backup"
                shutil.copy2(backup_save, dst)
                manifest["files"]["game_backup"] = {"source_path": str(backup_save), "snapshot_file": dst.name, "size": dst.stat().st_size, "sha256": sha256(dst)}
            else:
                manifest["files"]["game_backup"] = {"source_path": str(backup_save), "exists": False}
            if remote_save.exists():
                dst = folder / "SAVEDATA1000_from_steam_remote"
                shutil.copy2(remote_save, dst)
                manifest["files"]["steam_remote"] = {"source_path": str(remote_save), "snapshot_file": dst.name, "size": dst.stat().st_size, "sha256": sha256(dst)}
            else:
                manifest["files"]["steam_remote"] = {"source_path": str(remote_save), "exists": False}
            write_json(folder / "manifest.json", manifest)
            self.log(f"{self.app.t('created_snapshot')}: {folder}")
            return folder

    def sync_backup_to_remote(self, backup_save: Path, remote_save: Path, reason: str) -> bool:
        with self.lock:
            if not backup_save.exists():
                self.log(f"{self.app.t('backup_missing')}: {backup_save}")
                return False
            self.log(self.app.t("wait_stable"))
            if not wait_stable(backup_save):
                self.log(self.app.t("unstable"))
                return False
            self.snapshot(backup_save, remote_save, f"before_sync_{reason}")
            copy_atomic(backup_save, remote_save)
            self.log(f"{self.app.t('synced')}: {reason}")
            return True


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1280x780")
        self.minsize(1120, 680)
        self.configure(bg=SKY_BG)

        self.config_path = tool_dir() / CONFIG_NAME
        self.cfg = read_json(self.config_path, {})
        self.msgq: queue.Queue = queue.Queue()
        self.monitor_stop = threading.Event()
        self.monitor_thread: threading.Thread | None = None
        self.was_running = process_running()
        self.last_remote_hash: str | None = None
        self.last_backup_mtime_ns: int | None = None
        self.users: dict[str, dict[str, str]] = {}

        self._init_vars()
        self.guard = SaveGuard(self)
        self._setup_style()
        self._apply_icon()
        self._build_ui()
        self.after(200, self._pump)
        self.after(500, self.initial_autodetect)

    def t(self, key: str) -> str:
        return I18N.get(self.lang_var.get(), I18N["zh"]).get(key, I18N["zh"].get(key, key))

    def thread_log(self, msg: str):
        self.msgq.put(("log", msg))

    def _init_vars(self):
        steam_default = self.cfg.get("steam_root") or (str(steam_candidates()[0]) if steam_candidates() else "")
        self.lang_var = tk.StringVar(value=self.cfg.get("language", "zh"))
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

    def _setup_style(self):
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=SKY_BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("TLabel", background=SKY_BG, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT)
        style.configure("TButton", padding=(10, 5), foreground=TEXT)
        style.configure("Accent.TButton", padding=(12, 6), foreground="white", background=PRIMARY)
        style.map("Accent.TButton", background=[("active", PRIMARY_DARK)])
        style.configure("TCheckbutton", background=CARD_BG, foreground=TEXT)
        style.configure("TLabelframe", background=CARD_BG)
        style.configure("TLabelframe.Label", background=CARD_BG, foreground=TEXT)
        style.configure("TNotebook", background=SKY_BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 10), padding=(12, 5), background=PANEL_BG, foreground=TEXT)
        style.map("TNotebook.Tab", background=[("selected", CARD_BG)])
        style.configure("Treeview", font=("Microsoft YaHei UI", 10), rowheight=29, background="#FFFFFF", fieldbackground="#FFFFFF", foreground=TEXT)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), background=PANEL_BG, foreground=TEXT)
        self.title_font = tkfont.Font(family="Microsoft YaHei UI", size=23, weight="bold")
        self.mono_font = tkfont.Font(family="Consolas", size=10)

    def _apply_icon(self):
        icon = resource_path("assets/app_icon.ico")
        if icon.exists():
            try:
                self.iconbitmap(str(icon))
            except Exception:
                pass

    def save_config(self):
        data = {
            "language": self.lang_var.get(), "steam_root": self.steam_var.get(), "game_dir": self.game_var.get(), "backup_save": self.backup_var.get(), "remote_save": self.remote_var.get(), "account_id": self.account_var.get(), "poll": self.poll_var.get(), "snapshot_on_close": self.snapshot_on_close_var.get(), "sync_on_close": self.sync_on_close_var.get(), "rollback_guard": self.rollback_guard_var.get(), "sync_while_running": self.sync_while_running_var.get(), "online_profiles": self.online_profiles_var.get(),
        }
        write_json(self.config_path, data)
        self.log(f"{self.t('saved_config')}: {self.config_path}")

    def set_language(self, lang: str):
        if lang not in I18N:
            return
        self.lang_var.set(lang)
        self.save_config()
        for child in self.winfo_children():
            child.destroy()
        self._build_ui()
        self.scan_users(silent=True)
        self.refresh_status()

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=2)
        header.columnconfigure(2, weight=1)
        ttk.Label(header, text=APP_NAME, font=self.title_font, foreground=TEXT).grid(row=0, column=0, sticky="w")

        lang_panel = ttk.Frame(header, style="Card.TFrame", padding=(14, 8))
        lang_panel.grid(row=0, column=1, sticky="ew", padx=20)
        ttk.Label(lang_panel, text=self.t("language"), style="Card.TLabel", foreground=MUTED).pack(side="left", padx=(0, 10))
        for code, key in [("zh", "lang_zh"), ("en", "lang_en"), ("ja", "lang_ja")]:
            ttk.Radiobutton(lang_panel, text=self.t(key), value=code, variable=self.lang_var, command=lambda c=code: self.set_language(c)).pack(side="left", padx=4)

        self.monitor_label = ttk.Label(header, text=self.t("monitor_on") if self.monitor_thread and self.monitor_thread.is_alive() else self.t("monitor_off"), foreground=SUCCESS if self.monitor_thread and self.monitor_thread.is_alive() else DANGER)
        self.monitor_label.grid(row=0, column=2, sticky="e")

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, pady=(12, 0))
        self.tab_steam = ttk.Frame(self.tabs, padding=10, style="Card.TFrame")
        self.tab_user = ttk.Frame(self.tabs, padding=10, style="Card.TFrame")
        self.tab_guard = ttk.Frame(self.tabs, padding=10, style="Card.TFrame")
        self.tab_log = ttk.Frame(self.tabs, padding=10, style="Card.TFrame")
        self.tabs.add(self.tab_steam, text=self.t("tab_steam"))
        self.tabs.add(self.tab_user, text=self.t("tab_user"))
        self.tabs.add(self.tab_guard, text=self.t("tab_guard"))
        self.tabs.add(self.tab_log, text=self.t("tab_log"))
        self._build_steam_tab()
        self._build_user_tab()
        self._build_guard_tab()
        self._build_log_tab()

    def path_row(self, parent, row: int, label: str, var: tk.StringVar, command):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(parent, text=self.t("choose"), command=command).grid(row=row, column=2, pady=6)

    def _build_steam_tab(self):
        self.path_row(self.tab_steam, 0, self.t("steam_root"), self.steam_var, self.choose_steam)
        self.path_row(self.tab_steam, 1, self.t("game_dir"), self.game_var, self.choose_game)
        self.path_row(self.tab_steam, 2, self.t("backup_save"), self.backup_var, self.choose_backup)
        row = ttk.Frame(self.tab_steam, style="Card.TFrame")
        row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Button(row, text=self.t("auto_find"), style="Accent.TButton", command=self.find_game).pack(side="left", padx=(0, 8))
        ttk.Button(row, text=self.t("scan_userdata"), command=lambda: (self.scan_users(), self.tabs.select(self.tab_user))).pack(side="left", padx=(0, 8))
        ttk.Button(row, text=self.t("save_config"), command=self.save_config).pack(side="left", padx=(0, 8))
        ttk.Button(row, text=self.t("launch_game"), command=self.launch_game).pack(side="left", padx=(0, 8))
        ttk.Label(self.tab_steam, text=self.t("steam_help"), style="Card.TLabel", foreground=MUTED).grid(row=4, column=0, columnspan=3, sticky="w")

    def _build_user_tab(self):
        top = ttk.Frame(self.tab_user, style="Card.TFrame")
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text=self.t("scan_userdata"), style="Accent.TButton", command=self.scan_users).pack(side="left", padx=(0, 8))
        ttk.Button(top, text=self.t("refresh_profiles"), command=self.refresh_profiles).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(top, text=self.t("allow_online"), variable=self.online_profiles_var).pack(side="left")

        table_frame = ttk.Frame(self.tab_user, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True)
        cols = ("account", "steamid64", "name", "state", "has", "mtime", "path")
        self.user_tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=16)
        headings = [("account", self.t("account"), 115), ("steamid64", self.t("steamid64"), 165), ("name", self.t("steam_name"), 220), ("state", self.t("state"), 90), ("has", self.t("has_save"), 90), ("mtime", self.t("remote_info"), 230), ("path", self.t("remote_path"), 500)]
        for key, title, width in headings:
            self.user_tree.heading(key, text=title)
            self.user_tree.column(key, width=width, minwidth=width, stretch=False, anchor="w")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.user_tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.user_tree.xview)
        self.user_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.user_tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.user_tree.bind("<<TreeviewSelect>>", self.select_user)
        ttk.Label(self.tab_user, text=self.t("user_hint"), style="Card.TLabel", foreground=MUTED).pack(anchor="w", pady=(8, 0))

    def _build_guard_tab(self):
        self.path_row(self.tab_guard, 0, self.t("remote_save"), self.remote_var, self.choose_remote)
        opts = ttk.LabelFrame(self.tab_guard, text=self.t("options"), padding=10)
        opts.grid(row=1, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Checkbutton(opts, text=self.t("snap_close"), variable=self.snapshot_on_close_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts, text=self.t("sync_close"), variable=self.sync_on_close_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts, text=self.t("rollback"), variable=self.rollback_guard_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts, text=self.t("sync_running"), variable=self.sync_while_running_var).pack(anchor="w", pady=2)
        poll_row = ttk.Frame(opts, style="Card.TFrame")
        poll_row.pack(anchor="w", pady=(6, 0))
        ttk.Label(poll_row, text=self.t("poll"), style="Card.TLabel").pack(side="left")
        ttk.Spinbox(poll_row, from_=1, to=30, textvariable=self.poll_var, width=6).pack(side="left", padx=4)
        ttk.Label(poll_row, text=self.t("sec"), style="Card.TLabel").pack(side="left")
        buttons = ttk.Frame(self.tab_guard, style="Card.TFrame")
        buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Button(buttons, text=self.t("manual_snapshot"), command=self.manual_snapshot).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text=self.t("manual_sync"), style="Accent.TButton", command=self.manual_sync).pack(side="left", padx=(0, 8))
        self.monitor_button = ttk.Button(buttons, text=self.t("stop_monitor") if self.monitor_thread and self.monitor_thread.is_alive() else self.t("start_monitor"), command=self.toggle_monitor)
        self.monitor_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text=self.t("open_backups"), command=self.open_backups).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text=self.t("refresh_status"), command=self.refresh_status).pack(side="left", padx=(0, 8))
        box = ttk.LabelFrame(self.tab_guard, text=self.t("status"), padding=8)
        box.grid(row=3, column=0, columnspan=3, sticky="nsew")
        self.tab_guard.rowconfigure(3, weight=1)
        self.status_text = tk.Text(box, height=16, wrap="word", font=self.mono_font, bg="#FDFEFF", fg=TEXT, relief="flat")
        self.status_text.pack(fill="both", expand=True)
        self.status_text.configure(state="disabled")

    def _build_log_tab(self):
        row = ttk.Frame(self.tab_log, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 8))
        ttk.Button(row, text=self.t("clear_log"), command=lambda: self.log_text.delete("1.0", "end")).pack(side="left", padx=(0, 8))
        ttk.Button(row, text=self.t("open_tool_dir"), command=lambda: os.startfile(tool_dir())).pack(side="left")
        self.log_text = tk.Text(self.tab_log, wrap="word", font=("Microsoft YaHei UI", 10), bg="#FDFEFF", fg=TEXT, relief="flat")
        self.log_text.pack(fill="both", expand=True)
        self.log(f"{APP_NAME} v{APP_VERSION} {self.t('started')}: {tool_dir()}")

    def initial_autodetect(self):
        if self.steam_var.get() and not self.game_var.get():
            self.find_game(silent=True)
        if self.steam_var.get():
            self.scan_users(silent=True)
        self.refresh_status()

    def choose_steam(self):
        path = filedialog.askdirectory(title=self.t("steam_root"))
        if path:
            self.steam_var.set(path)
            self.find_game()
            self.scan_users()
            self.tabs.select(self.tab_user)

    def choose_game(self):
        path = filedialog.askdirectory(title=self.t("game_dir"))
        if path:
            self.game_var.set(path)
            self.backup_var.set(str(Path(path) / "savedata_backup" / "SAVEDATA1000"))
            self.refresh_status()

    def choose_backup(self):
        path = filedialog.askopenfilename(title=self.t("backup_save"))
        if path:
            self.backup_var.set(path)
            self.refresh_status()

    def choose_remote(self):
        path = filedialog.askopenfilename(title=self.t("remote_save"))
        if path:
            self.remote_var.set(path)
            self.refresh_status()

    def find_game(self, silent: bool = False):
        game = find_mhw(Path(self.steam_var.get()))
        if game:
            self.game_var.set(str(game))
            self.backup_var.set(str(game / "savedata_backup" / "SAVEDATA1000"))
            self.log(f"{self.t('found_mhw')}: {game}")
            self.save_config()
        elif not silent:
            messagebox.showwarning(APP_NAME, self.t("no_mhw"))
        self.refresh_status()

    def scan_users(self, silent: bool = False):
        root = Path(self.steam_var.get()) / "userdata"
        if not hasattr(self, "user_tree"):
            return
        self.user_tree.delete(*self.user_tree.get_children())
        self.users.clear()
        if not root.exists():
            if not silent:
                messagebox.showerror(APP_NAME, f"{self.t('no_steam')}: {root}")
            return
        for user_dir in sorted(root.iterdir(), key=lambda p: p.name):
            if not user_dir.is_dir() or not user_dir.name.isdigit():
                continue
            account = user_dir.name
            steamid64 = account_to_steamid64(account)
            remote = user_dir / APPID / "remote" / "SAVEDATA1000"
            has = remote.exists()
            info = file_table_brief(remote, self.t("missing")) if has else self.t("missing")
            self.users[account] = {"steamid64": steamid64, "remote": str(remote)}
            self.user_tree.insert("", "end", iid=account, values=(account, steamid64, self.t("not_loaded"), "", self.t("yes") if has else self.t("no"), info, str(remote)))
        self.log(f"{self.t('scanned_users')}: {len(self.users)}")

    def refresh_profiles(self):
        if not self.online_profiles_var.get():
            self.log(self.t("online_disabled"))
            return
        if not self.users:
            self.scan_users(silent=True)
        threading.Thread(target=self._profile_worker, daemon=True).start()

    def _profile_worker(self):
        self.msgq.put(("log", self.t("online_start")))
        for account, data in self.users.items():
            name, state = fetch_steam_profile(data["steamid64"])
            self.msgq.put(("profile", (account, name, state)))
        self.msgq.put(("log", self.t("online_done")))

    def select_user(self, _event=None):
        selection = self.user_tree.selection()
        if not selection:
            return
        account = selection[0]
        self.account_var.set(account)
        self.remote_var.set(self.users[account]["remote"])
        self.save_config()
        self.log(f"{self.t('chosen_user')}: {account}")
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
            messagebox.showinfo(APP_NAME, self.t("sync_done"))

    def toggle_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_stop.set()
            self.monitor_thread = None
            self.monitor_button.configure(text=self.t("start_monitor"))
            self.monitor_label.configure(text=self.t("monitor_off"), foreground=DANGER)
            self.log(self.t("monitor_stop_req"))
            return
        self.save_config()
        self.monitor_stop.clear()
        self.was_running = process_running()
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.monitor_button.configure(text=self.t("stop_monitor"))
        self.monitor_label.configure(text=self.t("monitor_on"), foreground=SUCCESS)
        self.log(self.t("monitor_started"))

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
                        self.msgq.put(("log", self.t("backup_changed")))
                        if self.sync_while_running_var.get():
                            self.guard.sync_backup_to_remote(backup, remote, "backup_changed_while_running")
                if self.was_running and not running:
                    self.msgq.put(("log", self.t("game_closed")))
                    if self.snapshot_on_close_var.get():
                        self.guard.snapshot(backup, remote, "game_closed")
                    if self.sync_on_close_var.get() and backup.exists():
                        if (not remote.exists()) or sha256(backup) != sha256(remote):
                            self.guard.sync_backup_to_remote(backup, remote, "game_closed")
                        else:
                            self.msgq.put(("log", self.t("backup_same")))
                    self.msgq.put(("status", None))
                self.was_running = running
                if (not running) and self.rollback_guard_var.get() and backup.exists() and remote.exists():
                    current_remote_hash = sha256(remote)
                    if self.last_remote_hash is None:
                        self.last_remote_hash = current_remote_hash
                    elif current_remote_hash != self.last_remote_hash:
                        self.last_remote_hash = current_remote_hash
                        self.msgq.put(("log", self.t("remote_changed")))
                        if sha256(backup) != sha256(remote):
                            self.guard.sync_backup_to_remote(backup, remote, "rollback_guard")
                        self.msgq.put(("status", None))
                time.sleep(max(1, int(self.poll_var.get())))
            except Exception as exc:
                self.msgq.put(("log", f"{self.t('error_monitor')}: {exc}"))
                time.sleep(3)
        self.msgq.put(("log", self.t("monitor_stopped")))

    def refresh_status(self):
        backup = Path(self.backup_var.get())
        remote = Path(self.remote_var.get())
        relation = self.t("unknown")
        if backup.exists() and remote.exists():
            relation = self.t("same") if sha256(backup) == sha256(remote) else self.t("different")
        data = {"Steam": self.steam_var.get(), "MHW": self.game_var.get(), "AccountID": self.account_var.get(), "backup": file_brief(backup).replace("missing", self.t("missing")), "remote": file_brief(remote).replace("missing", self.t("missing")), "backup_vs_remote": relation, "game_running": process_running(), "tool_backups": str(tool_dir() / "backups")}
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        self.status_text.configure(state="disabled")

    def launch_game(self):
        try:
            os.startfile(f"steam://rungameid/{APPID}")
            self.log(self.t("launch_requested"))
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
                    if hasattr(self, "user_tree") and self.user_tree.exists(account):
                        values = list(self.user_tree.item(account, "values"))
                        values[2] = name
                        values[3] = state
                        self.user_tree.item(account, values=values)
        except queue.Empty:
            pass
        self.after(150, self._pump)

    def log(self, msg: str):
        if hasattr(self, "log_text"):
            self.log_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            self.log_text.see("end")

    def close(self):
        self.save_config()
        self.monitor_stop.set()
        self.destroy()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.close)
    app.mainloop()


if __name__ == "__main__":
    main()
