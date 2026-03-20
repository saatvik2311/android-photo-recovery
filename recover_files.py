#!/usr/bin/env python3
"""
Android Image Recovery Tool
===========================
Detects a connected Android phone via ADB, finds the /Android folder
in internal storage, recursively scans every sub-folder, and pulls
all .png and .jpg/.jpeg files to a local output directory.

Requirements:
  - adb (Android Debug Bridge) installed and on PATH
  - USB Debugging enabled on the Android device
  - Device connected via USB and authorized
"""

import subprocess
import sys
import os
import time
from pathlib import Path
from datetime import datetime, timedelta


# ─── Configuration ───────────────────────────────────────────────────────────
# Configuration
ANDROID_BASE_DIR = "/sdcard"
TARGET_FOLDER = "Android"
# Expanded support for documents and images
FILE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".heic", ".webp",  # Images
    ".pdf", ".doc", ".docx", ".txt", ".rtf",    # Documents
    ".epub", ".mobi", ".azw3",                  # eBooks
    ".xlsx", ".xls", ".pptx", ".ppt", ".csv"    # Office
)
# Output directory (sibling to this script)
# Default to 'recovered_files' in the same directory as the script
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = SCRIPT_DIR / "recovered_files"


# ─── Helpers ─────────────────────────────────────────────────────────────────
def run_adb(*args: str) -> str:
    """Run an adb command and return stripped stdout. Raises on failure."""
    cmd = ["adb"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"adb command failed: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def run_adb_long(*args: str, timeout: int = 120) -> str:
    """Same as run_adb but with a longer timeout for heavy operations."""
    cmd = ["adb"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"adb command failed: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


# ─── Step 0: User Options ───────────────────────────────────────────────────
def get_user_options() -> tuple[int, bool, bool, bool]:
    """Prompt user for timeline, download, cleanup, and remote deletion."""
    print("\n📝  Recovery Options:")
    
    # 1. Timeline
    while True:
        raw = input("    How many days back do you want to search? [default: 7]: ").strip()
        if not raw:
            days = 7
            break
        try:
            days = int(raw)
            if days > 0:
                break
            print("    ❌  Please enter a positive number.")
        except ValueError:
            print("    ❌  Invalid number.")
    
    # 2. Download Preference
    should_download = True
    while True:
        raw = input("    Download images to computer? (Y/n) [default: Y]: ").strip().lower()
        if not raw or raw == 'y':
            should_download = True
            break
        if raw == 'n':
            should_download = False
            break
        print("    ❌  Please enter Y or n.")

    # 3. Cleanup Local (only if downloading)
    should_clear = False
    if should_download:
        while True:
            raw = input("    Clear existing recovered images (local)? (Y/n) [default: Y]: ").strip().lower()
            if not raw or raw == 'y':
                should_clear = True
                break
            if raw == 'n':
                should_clear = False
                break
            print("    ❌  Please enter Y or n.")

    # 4. Remote Deletion (Dangerous)
    should_delete_remote = False
    while True:
        raw = input("    DELETE these images from the phone after recovery? (WARNING: Irreversible!) [y/N]: ").strip().lower()
        if not raw or raw == 'n':
            should_delete_remote = False
            break
        if raw == 'y':
            should_delete_remote = True
            break
        print("    ❌  Please enter y or N.")

    print(f"    👉  Days: {days} | Download: {should_download} | Delete remote: {should_delete_remote}\n")
    return days, should_download, should_clear, should_delete_remote


# ─── Step 1: Detect phone ───────────────────────────────────────────────────
def detect_device() -> str:
    """Return the serial number of the first connected & authorized device."""
    print("🔍  Detecting connected Android device ...")
    output = run_adb("devices")
    lines = [l for l in output.splitlines()[1:] if l.strip()]

    if not lines:
        print("❌  No devices found.")
        print("    ➜  Make sure USB Debugging is ON")
        print("    ➜  Connect your phone and authorize this computer")
        sys.exit(1)

    for line in lines:
        parts = line.split("\t")
        if len(parts) == 2:
            serial, state = parts
            if state == "device":
                return serial
            elif state == "unauthorized":
                print(f"⚠️   Device {serial} is UNAUTHORIZED.")
                print("    ➜  Check your phone for the USB debugging prompt and tap 'Allow'")
                sys.exit(1)
            elif state == "offline":
                print(f"⚠️   Device {serial} is OFFLINE. Reconnect the cable.")
                sys.exit(1)

    print("❌  No authorized device found among attached devices.")
    sys.exit(1)


# ─── Step 2: Locate the Android folder ──────────────────────────────────────
def verify_android_folder() -> str:
    """Confirm /sdcard/Android exists and return its path."""
    android_path = f"{INTERNAL_STORAGE}/{TARGET_FOLDER}"
    print(f"📂  Looking for {android_path} ...")

    output = run_adb("shell", f"ls -d {android_path} 2>/dev/null || echo __MISSING__")
    if "__MISSING__" in output:
        print(f"❌  Folder not found: {android_path}")
        sys.exit(1)

    print(f"✅  Found: {android_path}")
    return android_path


def display_folder_sizes(android_path: str):
    """Show the size of top-level folders in Android directory."""
    print(f"📦  Calculating folder sizes in {android_path} (this may take a moment)...")
    try:
        # Use wildcards to get children. 2>/dev/null suppresses permission denied errors.
        cmd = f"du -sh {android_path}/* 2>/dev/null"
        # 30s timeout should be enough for just top level summary
        output = run_adb_long("shell", cmd, timeout=30)
        
        lines = output.splitlines()
        if not lines:
            print("    (No size info returned)")
            return

        for line in lines:
            if line.strip():
                print(f"    {line.strip()}")
        print()
    except Exception as e:
        print(f"    ⚠️  Could not calculate sizes: {e}\n")


# ─── Step 3: Scan & Filter Images ──────────────────────────────────────────
def extract_date_from_filename(filename: str) -> datetime | None:
    """
    Attempt to parse a date from the filename using common Android patterns.
    Supported patterns in filename:
      - YYYYMMDD (e.g. IMG_20260215_...)
      - YYYY-MM-DD (e.g. Screenshot_2026-02-15-...)
      - Unix Timestamp (e.g. 1771234567 — usually 10-13 digits, rare in filenames but possible)
    Returns a datetime object or None if no date found.
    """
    import re
    # Pattern 1: YYYYMMDD (most common, e.g. 20260215)
    match = re.search(r"(20[2-9]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", filename)
    if match:
        try:
            return datetime.strptime(match.group(0), "%Y%m%d")
        except ValueError:
            pass

    # Pattern 2: YYYY-MM-DD
    match = re.search(r"(20[2-9]\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", filename)
    if match:
        try:
            return datetime.strptime(match.group(0), "%Y-%m-%d")
        except ValueError:
            pass
            
    # Pattern 3: Unix Timestamp (seconds, starts with 17 or 18 for recent years)
    # e.g. 177... is year 2026. 170... is 2023.
    # Be conservative: 10 digits starting with 17/18
    match = re.search(r"(1[7-8]\d{8})", filename)
    if match:
        try:
            return datetime.fromtimestamp(int(match.group(0)))
        except (ValueError, OSError):
            pass

    return None


def scan_files(android_path: str, days_filter: int) -> list[tuple[str, datetime]]:
    """
    Scans the given path for matching files (images/docs) recursively.
    Filters by modification date (via filename) <= days_filter.
    Returns list of (full_path, date_obj).
    """
    print(f"🔎  Scanning for files inside {android_path} ...")
    
    # Calculate cutoff
    today = datetime.now()
    cutoff_date = today - timedelta(days=days_filter)
    print(f"📅  Filtering for files from {cutoff_date.date()} to {today.date()}")
    print(f"    (Filtering based on filename dates: YYYYMMDD or YYYY-MM-DD)")

    # Find all files with matching extensions
    # -L follows symlinks (usually safe on /sdcard/Android, but standard find is safer)
    # Using specific extensions to avoid scanning EVERYTHING
    # Construct -name arguments
    name_args = []
    for ext in FILE_EXTENSIONS:
        name_args.append(f"-name '*{ext}'")
        name_args.append(f"-name '*{ext.upper()}'") # Add uppercase check for ADB find
    
    find_cmd = f"find {android_path} -type f \\( {' -o '.join(name_args)} \\)"
    
    # Run find command
    # This might return A LOT of files.
    raw_output = run_adb_long("shell", find_cmd, timeout=120)
    raw_files = raw_output.splitlines()
    
    valid_files = []
    skipped_too_old = 0
    skipped_no_date = 0
    skipped_excluded = 0
    
    print(f"    (Analyzing {len(raw_files)} candidate files...)")

    for fpath in raw_files:
        fpath = fpath.strip()
        if not fpath:
            continue
            
        # 1. Safety Exclusions (WAMR, DCIM, Pictures)
        path_upper = fpath.upper()
        if "WAMR" in path_upper or "/DCIM/" in path_upper or "/PICTURES/" in path_upper:
            skipped_excluded += 1
            continue
        
        # 2. Date Filtering
        # Try to parse date from filename
        filename = os.path.basename(fpath)
        file_date = extract_date_from_filename(filename)
        
        if file_date:
            if file_date >= cutoff_date:
                valid_files.append((fpath, file_date))
            else:
                skipped_too_old += 1
        else:
            # If we can't get a date from filename, we skip it for safety/relevance
            # (Or we could check file metadata 'stat', but that's slow for thousands of files)
            skipped_no_date += 1

    print(f"📊  Scan Results:")
    print(f"    • Total candidates found: {len(raw_files)}")
    print(f"    • Skipped (Excluded): {skipped_excluded} (WAMR/DCIM/Pictures)")
    print(f"    • Skipped (Too Old):  {skipped_too_old}")
    print(f"    • Skipped (No Date):  {skipped_no_date}")
    print(f"    • Ready to recover:   {len(valid_files)}")
    print()
    
    return valid_files


# ─── Step 4: Pull images to local machine ───────────────────────────────────
def pull_files(file_list: list[tuple[str, datetime]], clear_output: bool = False) -> int:
    """
    Pulls the files in `file_list` from the device to OUTPUT_DIR.
    Handles filename collisions by appending a counter.
    """
    if not file_list:
        print("⚠️  No files to pull.")
        return 0

    print(f"⬇️  Recovering {len(file_list)} files to '{OUTPUT_DIR}' ...")
    
    if OUTPUT_DIR.exists() and clear_output:
        print("    ♻️  Clearing existing output directory...")
        import shutil
        shutil.rmtree(OUTPUT_DIR)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    success_count = 0
    
    for i, (remote_path, file_date) in enumerate(file_list, start=1):
        filename = os.path.basename(remote_path)
        local_path = OUTPUT_DIR / filename
        
        # Handle Collisions
        counter = 1
        stem = local_path.stem
        suffix = local_path.suffix
        while local_path.exists():
            local_path = OUTPUT_DIR / f"{stem}_{counter}{suffix}"
            counter += 1
            
        # Pull
        try:
            run_adb("pull", remote_path, str(local_path))
            
            if local_path.exists():
                success_count += 1
                # Optional: Set local file modification time to matched date
                # timestamp = file_date.timestamp()
                # os.utime(local_path, (timestamp, timestamp))
                
                # Print success indicator every 10 files or so to reduce spam
                if i % 10 == 0 or i == len(file_list):
                     sys.stdout.write(f"\r    ⏳  Progress: {i}/{len(file_list)}")
                     sys.stdout.flush()
        except Exception:
            print(f"\n    ❌  Failed to pull: {remote_path}")

    print(f"\n✅  Successfully recovered {success_count}/{len(file_list)} files.")
    return success_count


# ─── Step 5: Remote Deletion ────────────────────────────────────────────────
def delete_files_from_device(file_list: list[str]) -> None:
    """Bulk delete files from Android using a temporary file list."""
    if not file_list:
        return
    
    print("\n🗑️  Preparing to delete files from device ...")
    confirm = input("    ⚠️  Type 'DELETE' to confirm permanent deletion from phone: ").strip()
    if confirm != 'DELETE':
        print("    🛑  Deletion cancelled. Files remain on phone.")
        return

    # Create a local list file
    list_file = OUTPUT_DIR / "files_to_delete.txt"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(list_file, 'w') as f:
        # Quote names just in case, though ADB shell read line is tricky with quotes.
        # Safest for ADB shell while read is just the path if no crazy chars.
        # Better: use "rm \"$p\"" in the loop.
        for path in file_list:
            f.write(f"{path}\n")

    # Push list to device
    remote_list = "/sdcard/files_to_delete.txt"
    print(f"    📤  Pushing deletion list to {remote_list} ...")
    run_adb("push", str(list_file), remote_list)
    
    # Run batch delete
    print(f"    🔥  Deleting {len(file_list)} files from device ... (this may take time)")
    # 'tr' handles potential widows CRLF issues if pushed from windows, but we are on mac.
    # The command reads each line and runs rm.
    cmd = (
        f"while read p; do rm \"$p\" && echo \"Deleted: $p\"; done < {remote_list} "
        f"&& rm {remote_list}"
    )
    
    try:
        # Long timeout for bulk delete
        run_adb_long("shell", cmd, timeout=600)
        print("    ✅  Deletion complete.")
    except Exception as e:
        print(f"    ❌  Deletion failed or timed out: {e}")
    finally:
        if list_file.exists():
            list_file.unlink()


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  📱  Android Image Recovery Tool")
    print("=" * 60)
    
    # 0. User Options
    days, should_download, should_clear, should_delete_remote = get_user_options()
    
    start = time.time()

    # 1. Detect
    serial = detect_device()
    model = run_adb("shell", "getprop ro.product.model").strip()
    brand = run_adb("shell", "getprop ro.product.brand").strip()
    print(f"✅  Connected: {brand} {model}  (serial: {serial})\n")

    # 2. Locate Android folder
    android_path = verify_android_folder()
    
    # Show sizes
    display_folder_sizes(android_path)

    # 3. Scan
    # 3. Scan
    files = scan_files(android_path, days_filter=days)
    
    if not files:
        print("❌  No matching files found based on your criteria.")
        sys.exit(0)

    # Print sample files if any are found
    print(f"  Found {len(files)} files matching criteria.")
    if files and should_download:
        print("  Sample files:")
        for fpath, _ in files[:10]: # files is now list of (path, date) tuples
            print(f"    • {fpath}")
        if len(files) > 10:
            print(f"    ... and {len(files) - 10} more\n")
        print()
    elif files and not should_download:
        print(f"  Files identified: {len(files)} (Download skipped)")
        print() # Add a newline for better formatting

    # 4. Pull (Download) if requested
    recovered = 0 # Keep recovered count for final message
    if should_download:
        recovered = pull_files(files, clear_output=should_clear)
    else:
        print("  ⏩  Skipping download (Delete Only Mode)\n") # Added newline

    # 5. Remote Deletion (Optional)
    if should_delete_remote:
        # We need the list of remote paths. 
        # 'files' is a list of (path, date) tuples.
        remote_paths = [f[0] for f in files]
        delete_files_from_device(remote_paths)

    elapsed = time.time() - start
    print(f"=" * 60)
    if should_download:
        print(f"  ✨  Done!  {recovered} file(s) processed in {elapsed:.1f}s")
        print(f"  📁  Output: {OUTPUT_DIR.resolve()}")
        print(f"\n🎉  Recovery complete! Check the '{OUTPUT_DIR.name}' folder.")
    else:
        print(f"  ✨  Done!  Phone cleanup tasks finished in {elapsed:.1f}s")
        print(f"\n🎉  Operation complete!")
    print(f"=" * 60)


if __name__ == "__main__":
    main()
