# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# 获取当前脚本目录
base_dir = os.path.dirname(os.path.abspath(SPEC))

# 添加数据文件
a = Analysis(
    ['gui_main.py'],
    pathex=[base_dir],
    binaries=[],
    datas=[
        ('ebird_reference.sqlite', '.'),
        ('bird_tracker_unified.py', '.'),
        ('bird_region_query.py', '.'),
        ('main.py', '.'),
    ],
    hiddenimports=[
        'geocoder',
        'geopy',
        'pypinyin',
        'requests',
        'sqlite3',
        'json',
        'datetime',
        'subprocess',
        'warnings',
        'urllib3',
        'geopy.geocoders',
        'geopy.distance',
        'geocoder.arcgis',
        'geocoder.osm',
        'geocoder.google',
        'geocoder.bing',
        'geocoder.yahoo',
        'geocoder.mapquest',
        'geocoder.mapbox',
        'geocoder.here',
        'requests.adapters',
        'requests.auth',
        'requests.cookies',
        'requests.models',
        'requests.sessions',
        'urllib3.util',
        'urllib3.util.retry',
        'urllib3.util.ssl_',
        'urllib3.poolmanager',
        'certifi',
        'charset_normalizer',
        'idna',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy', 
        'pandas',
        'PIL',
        'tkinter',
        'rumps',
        'PyQt5',
        'PyQt6',
        'wx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='eBirdTracker',
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='eBirdTracker',
)

app = BUNDLE(
    coll,
    name='eBirdTracker.app',
    icon='eBirdTracker.icns' if os.path.exists('eBirdTracker.icns') else None,
    bundle_identifier='com.tuibird.tracker',
    version='0.4.1',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'CFBundleDisplayName': 'eBird追踪器',
        'CFBundleName': 'eBirdTracker',
        'CFBundleShortVersionString': '2.3.0',
        'CFBundleVersion': '2.3.0',
        'CFBundlePackageType': 'APPL',
        'CFBundleIdentifier': 'com.tuibird.tracker',
        'LSMinimumSystemVersion': '10.14',
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.utilities',
        'NSRequiresAquaSystemAppearance': False,
        'LSBackgroundOnly': False,
    },
)