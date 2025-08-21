# Uproszczony spec – tryb onedir (szybszy start, łatwiejszy debug)
block_cipher = None

a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=[],
    datas=[('config/*.json', 'config')],
    hiddenimports=['PySide6', 'qdarktheme'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    name='Wydajnia',
    debug=False,
    strip=False,
    upx=False,
    console=False,  # zmień na True jeśli chcesz okno konsoli do logów
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    name='Wydajnia'
)
