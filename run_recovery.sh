#!/bin/bash
# ============================================================
#  Android Image Recovery — Runner Script
# ============================================================
#  Usage:  ./run_recovery.sh
#
#  Prerequisites:
#    1. adb installed  (brew install android-platform-tools)
#    2. USB Debugging enabled on your Android phone
#    3. Phone connected via USB & authorized
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RECOVERY_SCRIPT="$SCRIPT_DIR/recover_images.py"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📱  Android Image Recovery Tool"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check for adb
if ! command -v adb &> /dev/null; then
    echo "❌  adb not found!"
    echo "   Install it with:  brew install android-platform-tools"
    exit 1
fi

# Check for python3
if ! command -v python3 &> /dev/null; then
    echo "❌  python3 not found!"
    exit 1
fi

# Quick device check
echo "🔌  Checking for connected devices ..."
DEVICES=$(adb devices 2>/dev/null | grep -w "device$" | wc -l | tr -d ' ')

if [ "$DEVICES" -eq 0 ]; then
    echo ""
    echo "⚠️   No authorized Android device detected."
    echo ""
    echo "  Checklist:"
    echo "    1. Connect your phone via USB cable"
    echo "    2. Enable USB Debugging (Settings → Developer Options → USB Debugging)"
    echo "    3. When prompted on phone, tap 'Allow' to authorize this computer"
    echo "    4. Re-run this script"
    echo ""
    exit 1
fi

echo "✅  Device detected! Starting recovery ..."
echo ""

# Run the Python script (unbuffered output)
python3 -u "$SCRIPT_DIR/recover_files.py"

echo ""
echo "🎉  Recovery complete! Check the 'recovered_images' folder."
echo ""
