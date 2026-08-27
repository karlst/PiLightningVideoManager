# VERIFIED LINUX VFA SPEC 2026-08-27
# Maintained source file: packaging/VfaLinux.spec
# Resolve application source from the repository root, one level above packaging/.
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

PACKAGING_DIRECTORY = Path(SPECPATH).resolve()
REPOSITORY_ROOT = PACKAGING_DIRECTORY.parent

a = Analysis(
    [str(REPOSITORY_ROOT / "video_analyzer" / "analyzer.py")],
    pathex=[str(REPOSITORY_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Vfa",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Vfa",
)
