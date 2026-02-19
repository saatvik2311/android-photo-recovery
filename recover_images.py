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
INTERNAL_STORAGE = "/sdcard"
TARGET_FOLDER = "Android"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")
# Output directory (sibling to this script)
OUTPUT_DIR = Path(__file__).parent / "recovered_images"


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


def scan_images(android_path: str, days_filter: int) -> list[str]:
    """Recursively find images, filtering by WAMR exclusion and date (last N days)."""
    print(f"🔎  Scanning for images inside {android_path} ...")
    
    # Calculate cutoff date
    now = datetime.now()
    cutoff_date = now.replace(hour=0, minute=0, second=0, microsecond=0) \
                  - timedelta(days=days_filter)
    print(f"📅  Filtering for images from {cutoff_date.date()} to {now.date()}")
    print("    (Filtering based on filename dates: YYYYMMDD or YYYY-MM-DD)")

    # Use `find` on the device
    ext_args = " -o ".join(
        [f'-iname "*.{ext.lstrip(".")}"' for ext in IMAGE_EXTENSIONS]
    )
    # Exclude WAMR directories at the find level to speed it up is tricky with standard find,
    # so we'll filter in Python.
    find_cmd = f'find {android_path} -type f \\( {ext_args} \\) 2>/dev/null'
    output = run_adb_long("shell", find_cmd, timeout=180)
    
    raw_files = [f.strip() for f in output.splitlines() if f.strip()]
    valid_files = []
    
    skipped_wamr = 0
    skipped_date = 0
    skipped_undated = 0

    for fpath in raw_files:
        filename = fpath.split("/")[-1]
        
        # 1. Safety Exclusions (WAMR, DCIM, Pictures)
        # Check if "WAMR", "DCIM", or "Pictures" is in the path
        # Note: Standard DCIM/Pictures are outside /sdcard/Android, but this protects against
        # apps that might create similarly named folders inside Android/data.
        path_upper = fpath.upper()
        if "WAMR" in path_upper or "/DCIM/" in path_upper or "/PICTURES/" in path_upper:
            skipped_wamr += 1
            continue
            
        # 2. Date Filtering
        dt = extract_date_from_filename(filename)
        if not dt:
            # If we can't find a date in the filename, strictly we should skip it 
            # based on "only recover the images in the last week... using naming convention"
            skipped_undated += 1
            continue
        
        if dt < cutoff_date:
            skipped_date += 1
            continue
            
        valid_files.append(fpath)

    print(f"📊  Scan Results:")
    print(f"    • Total images found: {len(raw_files)}")
    print(f"    • Skipped (Excluded): {skipped_wamr} (WAMR/DCIM/Pictures)")
    print(f"    • Skipped (Too Old):  {skipped_date}")
    print(f"    • Skipped (No Date):  {skipped_undated}")
    print(f"    • Ready to recover:   {len(valid_files)}\n")
    
    return valid_files


# ─── Step 4: Pull images to local machine ───────────────────────────────────
def pull_images(file_list: list[str], clear_output: bool) -> int:
    """Pull files to a flattened output directory."""
    if not file_list:
        print("⚠️   Nothing to recover.")
        return 0

    # Clean output directory first if requested
    if clear_output and OUTPUT_DIR.exists():
        print(f"🧹  Cleaning output directory: {OUTPUT_DIR.resolve()}")
        import shutil
        shutil.rmtree(OUTPUT_DIR)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"💾  Saving images to: {OUTPUT_DIR.resolve()}\n")

    success = 0
    errors = 0
    seen_filenames = {}

    for idx, remote_path in enumerate(file_list, 1):
        original_name = remote_path.split("/")[-1]
        
        # Handle duplicate filenames in flattened structure
        name_part, ext_part = os.path.splitext(original_name)
        if original_name in seen_filenames:
            seen_filenames[original_name] += 1
            count = seen_filenames[original_name]
            local_filename = f"{name_part}_{count}{ext_part}"
        else:
            seen_filenames[original_name] = 0
            local_filename = original_name

        local_path = OUTPUT_DIR / local_filename
        tag = f"[{idx}/{len(file_list)}]"
        
        try:
            # Use -p to preserve timestamps if possible, though adb pull usually does
            run_adb("pull", "-p", remote_path, str(local_path))
            
            # Verify it arrived
            if local_path.exists():
                size_kb = local_path.stat().st_size / 1024
                print(f"  ✅ {tag}  {local_filename}  ({size_kb:.1f} KB)")
                success += 1
            else:
                print(f"  ❌ {tag}  {local_filename}  — Download failed silently")
                errors += 1
        except Exception as e:
            print(f"  ❌ {tag}  {local_filename}  — {e}")
            errors += 1

    return success


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
    images = scan_images(android_path, days_filter=days)
    if images and should_download:
        print("  Sample files:")
        for f in images[:10]:
            print(f"    • {f}")
        if len(images) > 10:
            print(f"    ... and {len(images) - 10} more\n")
        print()
    elif images and not should_download:
        print(f"  Files identified: {len(images)} (Download skipped)")

    # 4. Pull (Optional)
    recovered = 0
    if should_download:
        recovered = pull_images(images, clear_output=should_clear)
    else:
        print("  ⏩  Skipping download (Delete Only Mode)")
    
    # 5. Remote Deletion (Optional)
    if should_delete_remote and images:
        delete_files_from_device(images)

    elapsed = time.time() - start
    print()
    print("=" * 60)
    if should_download:
        print(f"  ✨  Done!  {recovered} image(s) processed in {elapsed:.1f}s")
        print(f"  📁  Output: {OUTPUT_DIR.resolve()}")
    else:
        print(f"  ✨  Done!  Phone cleanup tasks finished in {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
