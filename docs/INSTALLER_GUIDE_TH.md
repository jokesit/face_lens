# คู่มือสร้างตัวติดตั้ง FaceLens สำหรับ Windows

## เป้าหมาย

ไฟล์ติดตั้งควรให้ร้านขายยาใช้งานได้ง่ายที่สุด:

```text
1. ดับเบิลคลิก Setup.exe
2. กด Next / Install
3. เปิดจากไอคอน FaceLens บน Desktop
```

## ขั้นตอน build

เปิด PowerShell ที่ project root และ activate venv ก่อน จากนั้นรัน:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\build_installer_windows.ps1
```

ผลลัพธ์:

```text
release\FaceLens_0.16_Setup.exe
```

## Path หลังติดตั้ง

โปรแกรม:

```text
C:\Program Files\FaceLens
```

ข้อมูลร้าน:

```text
C:\ProgramData\FaceLens
```

## ทำไมต้องแยกข้อมูลออกจาก Program Files

`C:\Program Files` เป็นโฟลเดอร์ที่ Windows ป้องกันไว้ หากโปรแกรมพยายามเขียนฐานข้อมูล/log/backup ลงในนั้น อาจเกิดปัญหาเปิดโปรแกรมไม่ได้หรือสำรองข้อมูลไม่ได้

ดังนั้น FaceLens installed mode จะเก็บข้อมูลที่ `C:\ProgramData\FaceLens` แทน

## ก่อนส่งให้ร้านจริง

ตรวจ checklist:

```text
[ ] ติดตั้งบนเครื่องทดสอบสะอาดได้
[ ] Desktop icon เปิดโปรแกรมได้
[ ] กล้องเปิดได้
[ ] เพิ่มลูกค้าทดสอบได้
[ ] backup ได้
[ ] log ถูกเขียนใน C:\ProgramData\FaceLens\logs
[ ] uninstall แล้วข้อมูลร้านไม่ถูกลบอัตโนมัติ
```
