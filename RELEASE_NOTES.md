# FaceLens Release Notes

## 0.16 - Windows Installer Readiness

### Added

- เพิ่ม Windows installer ด้วย Inno Setup
- ติดตั้งโปรแกรมไปที่ `C:\Program Files\FaceLens`
- สร้างไอคอนบน Desktop และ Start Menu อัตโนมัติ
- เพิ่มโหมด installed runtime โดยแยกข้อมูลร้านไปที่ `C:\ProgramData\FaceLens`
- เพิ่ม script `scripts/build_installer_windows.ps1`
- เพิ่ม helper `scripts/create_desktop_shortcut.ps1` สำหรับ portable ZIP
- ปรับเอกสาร build/release ภาษาไทยให้รองรับ installer mode

### Changed

- version เป็น `0.16`
- portable ZIP เปลี่ยนชื่อเป็น `FaceLens_0.16_Portable_PharmacyStandalone.zip`
- runtime logs ของ installed build ย้ายไปที่ `C:\ProgramData\FaceLens\logs`
- DeepFace model weights ของ installed build ย้ายไปที่ `C:\ProgramData\FaceLens\.deepface`

### Important

Installed build จะไม่เก็บฐานข้อมูลใน `C:\Program Files` เพื่อหลีกเลี่ยงปัญหา permission ของ Windows และทำให้ backup/support เป็นระบบมากขึ้น
