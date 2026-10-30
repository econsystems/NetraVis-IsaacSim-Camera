#!/usr/bin/env python3
"""Add (or remove) an e-con extension as a dependency of Isaac Sim's Full .kit apps.

The .kit files are read on every launch, so a [dependencies] entry there auto-loads the
extension.

Usage:
    patch_kit.py <isaac_apps_dir> <ext_name> [--uninstall]

Idempotent. Install keeps a one-time backup of each .kit (.netravis.bak) for manual recovery.
Uninstall removes only this extension's line, so other e-con packages patched into the
same .kit files are left alone.
"""
import glob
import os
import sys

MARKER = "# e-con NetraVis6L_USB"


def kit_files(appdir: str) -> list:
    return sorted(glob.glob(os.path.join(appdir, "isaacsim.exp.full*.kit")))


def install(appdir: str, ext: str) -> int:
    kits = kit_files(appdir)
    if not kits:
        print(f"[WARN] no isaacsim.exp.full*.kit found in {appdir}")
        return 1
    for kit in kits:
        s = open(kit).read()
        if any(ln.strip().startswith(f'"{ext}"') for ln in s.splitlines()):
            print(f"[INFO] already enabled in {os.path.basename(kit)}")
            continue
        if not os.path.exists(kit + ".netravis.bak"):
            open(kit + ".netravis.bak", "w").write(s)
        out, done = [], False
        for line in s.splitlines(keepends=True):
            out.append(line)
            if not done and line.strip() == "[dependencies]":
                out.append(f'"{ext}" = {{}}  {MARKER} camera menu\n')
                done = True
        if done:
            open(kit, "w").write("".join(out))
            print(f"[INFO] enabled in {os.path.basename(kit)} (autoload on every launch)")
        else:
            print(f"[WARN] no [dependencies] section in {os.path.basename(kit)} — skipped")
    return 0


def uninstall(appdir: str, ext: str) -> int:
    for kit in kit_files(appdir):
        lines = open(kit).read().splitlines(keepends=True)
        kept = [ln for ln in lines if not ln.strip().startswith(f'"{ext}"')]
        if len(kept) != len(lines):
            open(kit, "w").write("".join(kept))
            print(f"[INFO] removed {ext} from {os.path.basename(kit)}")
        else:
            print(f"[INFO] {ext} was not enabled in {os.path.basename(kit)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    appdir, ext = os.path.expanduser(sys.argv[1]), sys.argv[2]
    sys.exit(uninstall(appdir, ext) if "--uninstall" in sys.argv[3:] else install(appdir, ext))
