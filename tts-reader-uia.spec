# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

import os
import uiautomation

uia_bin_dir = os.path.join(os.path.dirname(uiautomation.__file__), 'bin')
binaries = [
    (os.path.join(uia_bin_dir, 'UIAutomationClient_VC140_X64.dll'), 'uiautomation\\bin'),
    (os.path.join(uia_bin_dir, 'UIAutomationClient_VC140_X86.dll'), 'uiautomation\\bin')
]
hiddenimports = ['uiautomation']
tmp_ret = collect_all('uiautomation')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['src\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['email', 'xml', 'html', 'http', 'unittest', 'urllib', 'numpy', 'sqlite3', 'ssl', '_ssl', 'hashlib', 'multiprocessing', 'bz2', 'lzma', 'csv', 'tarfile', 'zipfile', 'optparse', 'argparse', 'calendar', 'datetime', 'doctest', 'difflib', 'pydoc', 'socket', 'ftplib', 'poplib', 'imaplib', 'nntplib', 'smtplib', 'telnetlib', 'xmlrpc', 'logging.handlers', 'tty', 'pty', 'distutils', 'venv', 'site', 'pkg_resources', 'pydoc_data', 'pip'],
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
    name='tts-reader-uia',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
