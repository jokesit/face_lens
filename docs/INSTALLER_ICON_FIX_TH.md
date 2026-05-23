# FaceLens Installer Icon Fix

ถ้า shortcut บน Desktop เป็น icon สีขาว ให้ build installer ใหม่ด้วยไฟล์ `installer/FaceLens_Installer.iss` เวอร์ชันนี้

สาเหตุที่พบบ่อยคือ shortcut ชี้ไปที่ `{app}\assets\logo.ico` แต่ใน PyInstaller onedir ไฟล์ assets อาจอยู่ใต้ `_internal` ทำให้ Windows หา icon ไม่เจอ

เวอร์ชันนี้ copy `assets/logo.ico` ไปเป็นไฟล์คงที่:

```text
C:\Program Files\FaceLens\FaceLens.ico
```

และ shortcut ทุกตัวจะชี้ไปที่ไฟล์นี้แทน

หลังติดตั้งใหม่ ถ้า Windows ยังแสดง icon ขาว ให้ refresh icon cache หรือ restart Windows หนึ่งครั้ง เพราะ Windows อาจ cache shortcut icon เก่าไว้
