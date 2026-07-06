#!/usr/bin/env python
"""
translate-book-parallel — dependency setup script.

Verifies and installs all prerequisites for the skill.
Run: python scripts/setup.py
"""

import subprocess, sys, os, platform

def check_ram():
    """Check available RAM — warn if below safe threshold for parallel translation."""
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
        ok = ram_gb >= 8
        print(f"{'  ✅' if ok else '  ⚠️'} RAM: {ram_gb:.0f} GB {'(OK)' if ok else '(менее 8GB — используйте concurrency=1)'}")
        return ok
    except:
        print(f"  ➖ RAM: не удалось проверить (по умолчанию concurrency=1)")
        return False

PASS = "  ✅"
FAIL = "  ❌"
SKIP = "  ➖"

def sh(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip().split('\n')[0]
    except Exception as e:
        return False, str(e)

def check_python():
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 8
    print(f"{PASS if ok else FAIL} Python {v.major}.{v.minor}.{v.micro} (need >=3.8)")
    return ok

def check_calibre():
    ok, ver = sh("ebook-convert --version")
    if ok:
        ver_num = 0
        try:
            # Extract version number from "ebook-convert.exe (calibre 9.11.0)"
            import re
            m = re.search(r'(\d+)\.(\d+)', ver)
            if m:
                ver_num = int(m.group(1)) * 100 + int(m.group(2))
        except:
            pass
        if ver_num >= 900:
            print(f"{PASS} Calibre: {ver} (≥ 9.x — OK)")
        else:
            print(f"{FAIL} Calibre: {ver} (< 9.x — merge_and_build may hang)")
            print(f"       Upgrade: winget upgrade calibre.calibre")
            return False
    else:
        print(f"{FAIL} Calibre (ebook-convert) not found — install from https://calibre-ebook.com/")
    return ok

def check_pandoc():
    ok, ver = sh("pandoc --version | head -1")
    if ok:
        print(f"{PASS} Pandoc: {ver}")
    else:
        print(f"{FAIL} Pandoc not found — run: winget install JohnMacFarlane.Pandoc")
    return ok

def check_pip_module(name):
    ok, _ = sh(f"python -c \"import {name}; print({name}.__version__)\"")
    if ok:
        ver = eval(f"__import__('{name}').__version__")
        print(f"{PASS} {name} {ver}")
    else:
        print(f"{FAIL} {name} not installed — run: pip install {name}")
    return ok

def install_pip(name):
    print(f"  → Installing {name}...", end=" ")
    ok, out = sh(f"pip install {name}")
    print("OK" if ok else f"FAIL: {out}")
    return ok

def main():
    print("\n" + "=" * 55)
    print(" translate-book-parallel — Setup & Verification")
    print("=" * 55 + "\n")

    print("\n[1/5] Python")
    py_ok = check_python()
    ram_ok = check_ram()

    print("\n[2/5] System tools")
    cal_ok = check_calibre()
    pan_ok = check_pandoc()

    print("\n[3/5] Python packages")
    pypa_ok = check_pip_module("pypandoc")
    bs4_ok = check_pip_module("bs4")

    print("\n[4/5] Auto-install missing pip packages")
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
    print("      cp -r translate-book-parallel ${HERMES_HOME:-$HOME/.hermes}/skills/")
    print("   2. /reload-skills in chat")
    print("   3. Say: переведи D:\\\\book.epub на русский")
    if not ram_ok:
        print("")
        print("   ⚠️ Low memory detected. Concurrency limited to 1 chank.")
        print("   Set 'concurrency: 1' in SKILL.md before translating.")
    print("=" * 55 + "\n")

if __name__ == "__main__":
    main()
