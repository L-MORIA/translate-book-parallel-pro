#!/usr/bin/env python
"""
translate-book-parallel — dependency setup script.

Verifies and installs all prerequisites for the skill.
Run: python scripts/setup.py
"""

import re
import subprocess
import sys
import os
import platform

def check_ram():
    """Check available RAM — warn if below safe threshold for PRO parallel translation."""
    try:
        if platform.system() == "Windows":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            mem = ctypes.c_ulonglong()
            kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(mem))
            ram_gb = mem.value / (1024 * 1024)
        else:
            with open("/proc/meminfo") as f:
                for line in f:
                    if "MemTotal" in line:
                        ram_gb = int(line.split()[1]) / (1024 * 1024)
                        break
        ok = ram_gb >= 32
        print(f"  {'✅' if ok else '⚠️'} RAM: {ram_gb:.0f} GB {'(OK)' if ok else '(менее 32GB — уменьшите concurrency до 8-12)'}")
        return ok
    except (OSError, AttributeError, ValueError):
        print("  ➖ RAM: не удалось проверить (по умолчанию concurrency=24)")
        return True

def check_cpu():
    """Check CPU core count — warn if below recommended threshold."""
    try:
        cores = os.cpu_count() or 0
        ok = cores >= 8
        print(f"  {'✅' if ok else '⚠️'} CPU: {cores} ядер {'(OK)' if ok else '(менее 8 — уменьшите concurrency до 4-8)'}")
        return ok
    except (OSError, ValueError):
        print("  ➖ CPU: не удалось проверить")
        return True

PASS = "  ✅"
FAIL = "  ❌"
SKIP = "  ➖"

def sh(cmd, timeout=30):
    """Run a command given as a list of args (no shell=True — avoids shell injection).

    Returns (ok, first_line_of_stdout).
    """
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        first_line = r.stdout.strip().split('\n')[0] if r.stdout.strip() else ''
        return r.returncode == 0, first_line
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)

def check_python():
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 8
    print(f"{PASS if ok else FAIL} Python {v.major}.{v.minor}.{v.micro} (need >=3.8)")
    return ok

def check_calibre():
    ok, ver = sh(["ebook-convert", "--version"])
    if ok:
        ver_num = 0
        try:
            # Extract version number from "ebook-convert.exe (calibre 9.11.0)"
            m = re.search(r'(\d+)\.(\d+)', ver)
            if m:
                ver_num = int(m.group(1)) * 100 + int(m.group(2))
        except (ValueError, AttributeError):
            pass
        if ver_num >= 900:
            print(f"{PASS} Calibre: {ver} (≥ 9.x — OK)")
        else:
            print(f"{FAIL} Calibre: {ver} (< 9.x — merge_and_build may hang)")
            print("       Upgrade: winget upgrade calibre.calibre")
            return False
    else:
        print(f"{FAIL} Calibre (ebook-convert) not found — install from https://calibre-ebook.com/")
    return ok

def check_pandoc():
    ok, ver = sh(["pandoc", "--version"])
    if ok:
        print(f"{PASS} Pandoc: {ver}")
    else:
        print(f"{FAIL} Pandoc not found — run: winget install JohnMacFarlane.Pandoc")
    return ok

def check_pip_module(name):
    # Use sys.executable so this checks the same interpreter running setup.py,
    # not whatever "python" happens to resolve to on PATH.
    code = f"import {name}; print(getattr({name}, '__version__', 'unknown'))"
    ok, ver = sh([sys.executable, "-c", code])
    if ok:
        print(f"{PASS} {name} {ver}")
    else:
        print(f"{FAIL} {name} not installed — run: pip install {name}")
    return ok

def install_pip(name):
    print(f"  → Installing {name}...", end=" ")
    # --break-system-packages is required on PEP 668 "externally managed"
    # Python installs (Debian/Ubuntu 23.04+, current Homebrew Python, etc.);
    # it's a no-op / unrecognized-but-harmless on older pip versions.
    ok, out = sh([sys.executable, "-m", "pip", "install", "--break-system-packages", name])
    if not ok:
        # Fallback for pip versions that reject the unknown flag outright.
        ok, out = sh([sys.executable, "-m", "pip", "install", name])
    print("OK" if ok else f"FAIL: {out}")
    return ok

def main():
    print("\n" + "=" * 55)
    print(" translate-book-parallel-pro — Setup & Verification")
    print("=" * 55 + "\n")

    print("\n[1/4] Python + Hardware")
    py_ok = check_python()
    ram_ok = check_ram()
    cpu_ok = check_cpu()

    print("\n[2/4] System tools")
    cal_ok = check_calibre()
    pan_ok = check_pandoc()

    print("\n[3/4] Python packages")
    pypa_ok = check_pip_module("pypandoc")
    bs4_ok = check_pip_module("bs4")

    print("\n[4/4] Auto-install missing pip packages")
    if not pypa_ok:
        pypa_ok = install_pip("pypandoc")
    if not bs4_ok:
        bs4_ok = install_pip("beautifulsoup4")

    print("\n[5/5] Final verification")
    all_ok = all([py_ok, cal_ok, pan_ok, pypa_ok, bs4_ok])
    if all_ok:
        print(f"{PASS} All dependencies satisfied — skill ready to use")
    else:
        print(f"{FAIL} Some dependencies missing — see above")
        sys.exit(1)

    print("\n" + "=" * 55)
    print(" Quick start:")
    print("   1. Install skill in Hermes:")
    print("      cp -r translate-book-parallel-pro ${HERMES_HOME:-$HOME/.hermes}/skills/")
    print("   2. /reload-skills in chat")
    print("   3. Say: переведи /path/to/book.epub на русский (concurrency=24, chunk_size=15000)")
    if not ram_ok:
        print("")
        print("   ⚠️ Low memory detected. Set 'concurrency: 8-12' before translating.")
    if not cpu_ok:
        print("")
        print("   ⚠️ Low core count. Set 'concurrency: 4-8' before translating.")
    print("=" * 55 + "\n")

if __name__ == "__main__":
    main()
