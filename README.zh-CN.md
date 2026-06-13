# MHWSaveGuard

[English](README.md) | 简体中文

**MHWSaveGuard** 是一个面向 Windows 的《怪物猎人：世界》存档保护 GUI 工具，用来临时解决一种比较诡异的保存失败问题：

- `Monster Hunter World\savedata_backup\SAVEDATA1000` 会正常更新。
- `Steam\userdata\<AccountID>\582010\remote\SAVEDATA1000` 不会正常更新。
- 手动把游戏目录里的 backup 存档替换到 Steam remote 主存档后，进度可以保住。

这个工具会用更安全的方式自动完成这个流程：创建快照、同步存档，并在 Steam 意外回档时尝试保护进度。

## 功能特点

- 完整 GUI 操作界面，不再是 `1/2/3/4` 控制台菜单。
- 选择 Steam 根目录后自动查找《怪物猎人：世界》安装目录。
- 扫描 `Steam\userdata`，方便选择正确的 Steam 用户目录。
- 可选联网读取公开 Steam 昵称 / 状态，方便区分多个 userdata。
- 从 `SAVEDATA1000` 中谨慎扫描可能的角色名候选，但不会把它作为绝对判断依据。
- 监控 `MonsterHunterWorld.exe` 是否正在运行。
- **每次检测到游戏关闭后**，在工具目录下创建带时间戳的备份快照：
  - `backups/<时间戳>_game_closed/SAVEDATA1000_from_game_savedata_backup`
  - `backups/<时间戳>_game_closed/SAVEDATA1000_from_steam_remote`
  - `manifest.json`，记录路径、文件大小、时间和 SHA-256。
- 游戏关闭后自动复制：
  - 从 `savedata_backup\SAVEDATA1000`
  - 到 `userdata\<AccountID>\582010\remote\SAVEDATA1000`
- 回档保护：
  - 如果游戏未运行时 Steam 改写了 `remote\SAVEDATA1000`，并且它和可信的游戏 backup 不一致，工具会先创建现场快照，再用游戏 backup 恢复 remote。

## 为什么需要这个工具

这是针对某些 MHW / Steam 存档链路异常的临时解决方案。它不是游戏 Mod，不修改游戏内存，也不会改变玩法。它只是在创建备份后复制存档文件。

## 快速开始

### 从源码运行

1. 安装 Python 3.10 或更新版本。
2. 安装依赖：

```powershell
pip install -r requirements.txt
```

3. 运行：

```powershell
python mhw_save_guard.py
```

也可以直接双击：

```text
run_gui.bat
```

### 本地打包 EXE

双击：

```text
build_exe.bat
```

生成的可执行文件会出现在：

```text
dist\MHW_Save_Guard.exe
```

## 推荐使用方式

1. 打开工具。
2. 选择 Steam 文件夹，例如：

```text
D:\Steam
```

3. 让工具自动查找《怪物猎人：世界》。
4. 扫描 `userdata`。
5. 选择你的 Steam 用户目录。
6. 切换到 **保护与同步**。
7. 建议开启：
   - 游戏关闭后创建快照。
   - 游戏关闭后同步 backup 到 remote。
   - 回档保护。
8. 玩游戏前启动监控。

当你关闭游戏后，工具会在 `backups` 下创建本地备份，并把最新的游戏目录 backup 同步到 Steam remote 主存档。

## 关于“角色信息”

MHW 的 `SAVEDATA1000` 是二进制存档文件。工具会尝试从可打印字符串中扫描“角色名候选”，但这不一定准确，也不会作为自动选择依据。建议结合 Steam 昵称 / 状态、AccountID、存档修改时间和文件大小来判断。

## 安全设计

每次覆盖 remote 主存档前，工具都会先创建快照。如果出现问题，可以去这里找回旧文件：

```text
<工具目录>\backups
```

每个快照文件夹里都有一个 `manifest.json`，记录来源路径、文件大小和 SHA-256。

## 注意事项

- 这个工具是 workaround，不保证能修复游戏里“保存失败”的弹窗。
- 它的目标是尽量保住实际写入到 `savedata_backup` 的进度。
- 如果你启用了 Steam 云同步，Steam 仍可能在某些情况下覆盖本地文件。遇到回档风险时，优先检查工具目录下的 `backups`。
- 在使用存档编辑器、Mod 或手动替换存档前，建议额外复制一份独立备份。

## 免责声明

请自行承担使用风险。修改、替换或同步存档文件前，请始终保留额外备份。
