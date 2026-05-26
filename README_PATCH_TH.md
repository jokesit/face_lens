# FaceLens pilot hardening patch

ไฟล์ใน patch นี้เน้นแก้จุดเสี่ยงก่อนต่อยอดฟีเจอร์:

- `core/database.py`
  - เพิ่ม `find_nearest_customers_by_embedding()`
  - เพิ่ม `find_possible_duplicate_customers()`
  - เพิ่ม `_deactivate_old_embeddings_for_customer()`
  - จำกัด active face embeddings ต่อคนตาม `RECOMMENDED_MAX_EMBEDDINGS_PER_CUSTOMER`

- `requirements.txt`
  - แปลงเป็น UTF-8 ปกติ เพื่อให้ `pip install -r requirements.txt` เสถียรกว่าเดิม

- `create_handoff.py`
  - รวม source/docs/scripts/installer/assets ได้
  - ไม่รวม runtime data, database, backup, logs, build output, model weights, exe, zip

## ตรวจหลังรวม patch

```powershell
python -m compileall -q .
python scripts\health_check.py
```

ทดสอบใน Windows จริง:

1. เพิ่มลูกค้าใหม่
2. เพิ่มลูกค้าคนเดิมซ้ำ
3. เพิ่มใบหน้าคล้ายคนเดิมแต่คนละชื่อ
4. กด “ตรวจรายชื่อซ้ำ”
5. build exe + installer
6. install ทับ version เดิม และตรวจว่า `C:\ProgramData\FaceLens` ยังอยู่

หมายเหตุ: patch นี้ไม่รวมไฟล์ font ตามหลักการไม่ส่งต่อ font file ผ่าน zip patch ให้คัดลอก `tahoma.ttf` เข้า `assets/` ในเครื่อง build ของลูกพี่เอง
