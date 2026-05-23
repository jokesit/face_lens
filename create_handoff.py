import os
import zipfile
from datetime import datetime

def create_project_handoff(project_dir='.', output_dir='handoff', project_name='project_handoff'):
    # 1. สร้างโฟลเดอร์ handoff หากยังไม่มี
    os.makedirs(output_dir, exist_ok=True)

    # 2. ตั้งชื่อไฟล์ zip พร้อมประทับเวลา (Timestamp) เพื่อไม่ให้ไฟล์เขียนทับกัน
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_filename = f"{project_name}_{timestamp}.zip"
    zip_filepath = os.path.join(output_dir, zip_filename)

    # 3. กำหนดโฟลเดอร์และนามสกุลไฟล์ที่ไม่ต้องการรวมเข้าไปใน Zip
    exclude_dirs = {
        '.git', '__pycache__', 'venv', 'env', 'build' , 'dist' , '__pycache__' , 'assets' , 'temp_files' ,
        '.idea', '.vscode', 'node_modules', output_dir , 'DPOS_installer/DPOS' , 'DPOS_installer/Output' , 'handoff'
    }
    exclude_exts = {'.pyc', '.pyo', '.pyd', '.env' , '.exe'} # แนะนำให้ข้าม .env เพื่อความปลอดภัย

    print(f"กำลังรวบรวมไฟล์เพื่อสร้าง: {zip_filename} ...")

    # 4. เริ่มต้นกระบวนการบีบอัดไฟล์
    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(project_dir):
            # กรองโฟลเดอร์ที่ไม่ต้องการออกจากการค้นหา (modifying dirs in-place)
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                # ข้ามไฟล์ที่มีนามสกุลตรงกับที่กำหนดไว้
                if any(file.endswith(ext) for ext in exclude_exts):
                    continue

                file_path = os.path.join(root, file)
                
                # หา path สัมพัทธ์ (Relative path) เพื่อให้โครงสร้างโฟลเดอร์ใน zip เหมือนต้นฉบับ
                arcname = os.path.relpath(file_path, project_dir)
                zipf.write(file_path, arcname)

    print(f"✅ บีบอัดไฟล์เสร็จสิ้น! บันทึกไว้ที่: {zip_filepath}")

if __name__ == "__main__":
    # สามารถเปลี่ยน project_name เป็นชื่อโปรเจกต์ของคุณได้เลย
    create_project_handoff(project_name="my_python_project")