# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('frontend', 'frontend'), ('sample_data', 'sample_data'), ('configs', 'configs'), ('generated_data', 'generated_data'), ('uploads', 'uploads')],
    hiddenimports=['uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'asyncua', 'paho', 'paho.mqtt', 'paho.mqtt.client', 'openpyxl'],
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
    name='IndustrialDualProtocolTagSimulator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    name='IndustrialDualProtocolTagSimulator',
)
