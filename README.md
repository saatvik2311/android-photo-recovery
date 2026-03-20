# Android File Recovery Tool

A simple, Python-based tool to recover deleted files (Photos, PDFs, Docs, etc.) from Android devices using ADB (Android Debug Bridge). It scans the device storage for multiple file types, filters them by date, and pulls them to your local computer.

## Features
- **Device Detection**: Automatically finds connected Android devices.
- **Broad File Support**: Recovers Images (`.jpg`, `.png`, `.heic`), Documents (`.pdf`, `.docx`, `.txt`), eBooks (`.epub`, `.mobi`), and more.
- **Filtering**:
    - **Timeline**: Search for files from the last N days (default: 7).
    - **Exclusions**: Automatically ignores `WAMR`, `DCIM`, and `Pictures` folders to protect existing gallery content.
- **Safety**:
    - **Read-Only Scan**: Does not modify device data during scan.
    - **Delete Check**: Optional feature to delete files from the phone *after* recovery, with double-confirmation prompts.
- **Clean Output**: Flattens the directory structure so all recovered files are in one place (`recovered_files`).

## Requirements
1.  **Python 3.x**: [Download Python](https://www.python.org/downloads/)
2.  **ADB (Android Debug Bridge)**:
    - **Windows**: Install [SDK Platform Tools](https://developer.android.com/studio/releases/platform-tools). Add `platform-tools` to your PATH.
    - **macOS**: `brew install android-platform-tools`
    - **Linux**: `sudo apt install adb`
3.  **USB Debugging**: Enabled on your Android phone.

## Usage

### Windows
Double-click `run_recovery.bat` or run from command line:
```cmd
run_recovery.bat
```

### macOS / Linux
Open your terminal and run:
```bash
./run_recovery.sh
```

## Interactive Options
The tool will ask you:
1.  **Timeline**: How many days back to search.
2.  **Download**: whether to save images to your computer (Y/n).
    - Select `n` for **Delete Only Mode** (cleans phone without saving).
3.  **Cleanup**: whether to clear previous results.
4.  **Remote Deletion**: optionally delete the specific files found from the phone.

## License
MIT
