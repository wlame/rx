# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# Collect all rx module files
datas, binaries, hiddenimports = collect_all('rx')

a = Analysis(
    ['src/rx/cli/main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'rx',
        'rx.web',
        'rx.parse',
        'rx.parse_json',
        'rx.cli',
        'rx.cli.main',
        'rx.cli.search',
        'rx.cli.analyse',
        'rx.cli.check',
        'rx.cli.serve',
        'rx.cli.prometheus',
        'rx.utils',
        'rx.models',
        'rx.analyse',
        'rx.regex',
        'rx.rg_json',
        'rx.prometheus',
        'rx.scheduler',
    ],
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
    a.binaries,
    a.datas,
    [],
    name='rx',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
