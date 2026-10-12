# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['PIL._tkinter_finder', 'core.gmail_tool', 'OpenGL', 'OpenGL.GL', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFilter', 'PIL.ImageFont', 'PIL.ImageOps', 'PIL.ImageTk', 'PyPDF2', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtOpenGLWidgets', 'PyQt6.QtWidgets', 'ast', 'asyncio', 'atexit', 'base64', 'collections', 'colorsys', 'comtypes', 'concurrent.futures', 'cryptography.hazmat.primitives', 'cryptography.hazmat.primitives.ciphers', 'cryptography.hazmat.primitives.padding', 'ctypes', 'ctypes.wintypes', 'cv2', 'dataclasses', 'datetime', 'difflib', 'docx', 'docx.shared', 'duckduckgo_search', 'email.message', 'email.mime.text', 'fastapi', 'fastapi.responses', 'fnmatch', 'fractions', 'gc', 'google', 'google.auth.transport.requests', 'google.genai', 'google.genai.types', 'google.oauth2.credentials', 'google_auth_oauthlib.flow', 'googleapiclient.discovery', 'googleapiclient.http', 'hashlib', 'html', 'importlib.metadata', 'importlib.util', 'inspect', 'io', 'json', 'logging', 'math', 'matplotlib', 'matplotlib.pyplot', 'mediapipe', 'mss', 'mss.tools', 'numpy', 'openpyxl', 'openpyxl.styles', 'openwakeword', 'openwakeword.model', 'openwakeword.utils', 'operator', 'os', 'pathlib', 'platform', 'playwright.async_api', 'pptx', 'psutil', 'pyautogui', 'pycaw.pycaw', 'pygetwindow', 'pyperclip', 'pytesseract', 'pywinauto', 'pywinauto.findwindows', 'qrcode', 'queue', 'random', 're', 'requests', 'secrets', 'send2trash', 'serial', 'serial.tools', 'serial.tools.list_ports', 'shutil', 'socket', 'sounddevice', 'stat', 'statistics', 'string', 'subprocess', 'sys', 'tarfile', 'tempfile', 'threading', 'time', 'tkinter', 'tkinter.simpledialog', 'traceback', 'typing', 'urllib.parse', 'urllib.request', 'uvicorn', 'vosk', 'wave', 'webbrowser', 'win32com.client', 'winreg', 'wmi', 'youtube_transcript_api', 'zipfile', 'zoneinfo']
datas += collect_data_files('cv2')
hiddenimports += collect_submodules('email')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('OpenGL')
tmp_ret = collect_all('mediapipe')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=['D:/Jarvis'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='Jarvis',
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
    icon=['D:/Jarvis/config/jarvis.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Jarvis',
)
