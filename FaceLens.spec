# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

block_cipher = None

# --- 💡 (แก้ไข) เปลี่ยนจาก 'models' เป็น 'weights' ให้ตรงกับเครื่องของคุณ ---
deepface_weights_path = str(Path.home() / '.deepface' / 'weights')
# ---------------------------------------------------------------------

a = Analysis(['main.py'],
             pathex=[],
             binaries=[], # ปล่อยว่างไว้เหมือนเดิม
             datas=[
                 ('assets', 'assets'),
                 ('data', 'data'),
                 (deepface_weights_path, '.deepface/weights'),
                 ('venv\\Lib\\site-packages\\faiss_cpu.libs', 'faiss_cpu.libs'),
                 ('venv\\Lib\\site-packages\\mediapipe', 'mediapipe')
             ],
             hiddenimports=[
                 'sklearn.neighbors._typedefs', 
                 'sklearn.utils._cython_blas', 
                 'pandas._libs.tslibs.base'
             ],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.datas,
          [],
          name='FaceLens',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None,
          icon='assets\\logo.ico'
          )