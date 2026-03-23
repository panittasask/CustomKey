# CustomKey

Python app สำหรับอัปโหลดไฟล์ i18n JSON แล้วค้นหา/เลือก key ที่ต้องการ จากนั้นสร้างไฟล์ใหม่ชื่อ `ชื่อไฟล์เดิม+custom.json` โดยคงโครงสร้าง parent เดิมไว้

## Features
- Upload ไฟล์ i18n `.json`
- Search/filter ตาม path ของ key หรือ value
- เลือก key ได้หลายรายการ
- โหมดเลือก `Leaf keys` หรือ `Parent nodes` (เลือก parent แล้วดึงลูกทั้งหมด)
- ปุ่ม `Select all matched` และ `Clear selection`
- Convert เป็น JSON ใหม่ที่มีเฉพาะ key ที่เลือก พร้อม parent path
- Download ไฟล์ผลลัพธ์ชื่อ `file+custom.json`

## Run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

แล้วเปิด URL ที่ Streamlit แสดงใน terminal
