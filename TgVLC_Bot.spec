# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py', 'config.py', 'vlc_player.py', 'file_browser.py', 'logger.py', 'session.py', 'handlers\\__init__.py', 'handlers\\base.py', 'handlers\\callbacks.py', 'handlers\\file_browse.py', 'handlers\\keyboards.py', 'handlers\\navigation.py', 'handlers\\playback.py', 'handlers\\settings.py', 'handlers\\subtitle.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'socksio',
        'httpcore',
        'httpcore._async',
        'httpcore._sync',
        'h11',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        'sniffio',
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
    [],
    exclude_binaries=True,
    name='TgVLC_Bot',
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
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TgVLC_Bot',
)
