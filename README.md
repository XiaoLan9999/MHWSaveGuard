# MHWSaveGuard

**MHWSaveGuard** is a Windows GUI utility for *Monster Hunter: World* players who hit the weird “Failed to save game” problem where:

- `Monster Hunter World\savedata_backup\SAVEDATA1000` updates correctly.
- `Steam\userdata\<AccountID>\582010\remote\SAVEDATA1000` does **not** update.
- Replacing the Steam `remote` save with the game-folder backup keeps the progress.

This tool protects that workflow with a safer GUI, automatic snapshots, and rollback protection.

## Features

- Full GUI workflow, no `1/2/3/4` console menu.
- Choose Steam root and auto-detect *Monster Hunter: World*.
- Scan `Steam\userdata` and select the correct user.
- Optional online lookup of public Steam name/status through Steam Community XML.
- Shows cautious MHW character-name candidates scanned from printable strings in `SAVEDATA1000`.
- Monitor `MonsterHunterWorld.exe`.
- **Every time the game closes**, create a timestamped backup under the tool directory:
  - `backups/<timestamp>_game_closed/SAVEDATA1000_from_game_savedata_backup`
  - `backups/<timestamp>_game_closed/SAVEDATA1000_from_steam_remote`
  - `manifest.json` with file sizes, paths, timestamps, and SHA-256.
- After game close, automatically copy:
  - from `savedata_backup\SAVEDATA1000`
  - to `userdata\<AccountID>\582010\remote\SAVEDATA1000`
- Rollback guard:
  - If Steam later rewrites `remote\SAVEDATA1000` while the game is not running, and it no longer matches the trusted backup, the tool snapshots the scene first and then restores from the game backup.

## Why this exists

This is a workaround for a specific MHW/Steam save issue. It does not modify game memory and it is not a gameplay mod. It simply copies save files after creating backups.

## Quick start

### Run from source

1. Install Python 3.10+.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run:

```powershell
python mhw_save_guard.py
```

Or double-click:

```text
run_gui.bat
```

### Build EXE locally

Double-click:

```text
build_exe.bat
```

The executable will appear at:

```text
dist\MHW_Save_Guard.exe
```

## Recommended usage

1. Open the tool.
2. Select your Steam folder, for example:

```text
D:\Steam
```

3. Let it auto-detect *Monster Hunter: World*.
4. Scan `userdata`.
5. Select your Steam user.
6. Go to **保护与同步**.
7. Enable:
   - Create snapshot after game closes.
   - Sync backup to remote after game closes.
   - Rollback guard.
8. Start monitoring before playing.

When you close the game, the tool creates a local backup under `backups` and syncs the newest game-folder backup to Steam remote save.

## Notes about “character info”

MHW’s `SAVEDATA1000` is a binary save. This tool shows cautious “character name candidates” scanned from printable strings, but it does **not** rely on them for automatic selection. Select by Steam name/status, AccountID, and save modified time.

## Safety

Before every overwrite, the tool creates a snapshot. If something goes wrong, check:

```text
<tool folder>\backups
```

Each snapshot has a `manifest.json`.

## Disclaimer

Use at your own risk. Always keep separate backups before editing or replacing MHW save files.
