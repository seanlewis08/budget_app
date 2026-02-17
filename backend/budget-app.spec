# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for the Budget App backend.
Bundles the FastAPI app into a single executable.
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['run_app.py'],
    pathex=[str(Path.cwd().parent)],
    binaries=[],
    datas=[
        (str(Path.cwd().parent / 'frontend' / 'dist'), 'frontend_dist'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'sqlalchemy.dialects.sqlite',
        # Routers
        'backend.routers.transactions',
        'backend.routers.categories',
        'backend.routers.budgets',
        'backend.routers.import_csv',
        'backend.routers.notifications',
        'backend.routers.accounts',
        'backend.routers.archive',
        'backend.routers.investments',
        'backend.routers.insights',
        # Services
        'backend.services.categorize',
        'backend.services.seed_data',
        'backend.services.plaid_service',
        'backend.services.sync_scheduler',
        'backend.services.financial_advisor',
        'backend.services.price_fetcher',
        'backend.services.archive_importer',
        # CSV parsers
        'backend.services.csv_parsers.discover',
        'backend.services.csv_parsers.sofi',
        'backend.services.csv_parsers.wellsfargo',
        # Infrastructure
        'backend.investments_database',
        'backend.models_investments',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='budget-app-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for logging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
