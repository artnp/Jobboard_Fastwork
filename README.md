# Fastwork Job Monitor & Auto-Responder Bot 🤖

บอทตรวจจับงานใหม่จาก [Fastwork Jobboard](https://jobboard.fastwork.co/jobs) ที่ตรงกับคีย์เวิร์ดความชำนาญของคุณโดยอัตโนมัติ 
เน้นความเบา **กิน RAM เพียง ~25MB** รันแบบซ่อนหน้าต่าง CMD ใน Background พร้อม **System Tray Icon (รูปตัว F)** บน Windows Taskbar

---

## 📁 ไฟล์ที่จำเป็นทั้งหมดในโปรเจกต์ (Clean Structure)

| ไฟล์ | หน้าที่ |
| :--- | :--- |
| **[`start_bot.vbs`](file:///c:/Users/artwh/Desktop/job/start_bot.vbs)** | **ปุ่มเปิดใช้งานหลัก:** ดับเบิลคลิกเพื่อรันบอทใน Background (ซ่อนหน้าต่าง CMD ดำ) |
| **[`fastwork_bot.py`](file:///c:/Users/artwh/Desktop/job/fastwork_bot.py)** | **สคริปต์หลัก:** รวมระบบตรวจจับงาน, แจ้งเตือน, และ System Tray Menu ไว้ในไฟล์เดียว |
| **[`config.json`](file:///c:/Users/artwh/Desktop/job/config.json)** | **ไฟล์ตั้งค่า:** คีย์เวิร์ดทั้ง 24 คำ, เวลาเช็ค (วินาที), โหมดการทำงาน, และการแจ้งเตือน |
| **[`icon.png`](file:///c:/Users/artwh/Desktop/job/icon.png)** | **ไอคอน:** โลโก้ตัว **F** สีน้ำเงินบน Windows System Tray |
| **[`seen_jobs.json`](file:///c:/Users/artwh/Desktop/job/seen_jobs.json)** | **ฐานข้อมูล:** บันทึก ID งานที่เคยตรวจเจอแล้ว เพื่อป้องกันการแจ้งเตือนซ้ำ |
| **[`README.md`](file:///c:/Users/artwh/Desktop/job/README.md)** | **คู่มือการใช้งาน:** วิธีตั้งค่าและเมนูสั่งงาน |

---

## 🚀 วิธีใช้งาน

### 1. วิธีเริ่มรันบอท (Background Run)
ดับเบิลคลิกที่ไฟล์ **`start_bot.vbs`** 
* จะไม่มีหน้าต่าง CMD ขึ้นมากวนใจ
* ไอคอนโลโก้ **`F`** สีน้ำเงินจะไปปรากฏที่ **System Tray (มุมขวาล่างข้างนาฬิกา)**

### 2. เมนูใน System Tray (คลิกขวาที่ไอคอนตัว F)
- 🟢 **Status Info**: แสดงสถานะการเช็คล่าสุด
- 🔍 **ตรวจหางานทันที (Check Now)**: สั่งเช็คงานใหม่ทันทีโดยไม่ต้องรอให้ครบ 5 นาที
- ⚙️ **แก้ไขไฟล์ตั้งค่า (config.json)**: เปิดไฟล์ตั้งค่าขึ้นมาแก้ไข
- 📄 **ดูประวัติ Log (bot.log)**: เปิดดูประวัติการทำงาน
- 📁 **เปิดโฟลเดอร์โปรแกรม**: เปิดโฟลเดอร์ทำงาน
- ❌ **ปิดโปรแกรม (Exit)**: ปิดการทำงานของบอท

---

## ⚙️ การตั้งค่าใน `config.json`

```json
{
  "keywords": [
    "แก้ไขข้อความ", "แก้ไขภาพ", "แก้ไขรูป", "ตัดต่อรูป", "ตัดต่อภาพ",
    "แก้ไขเอกสาร", "ตัดต่อเอกสาร", "photoshop", "โฟโต้ชอป", "retouch",
    "รีทัช", "แก้ไขตัวหนังสือ", "ตัดต่อตัวหนังสือ", "ตัดต่อข้อความ",
    "หาฟอนต์", "หา font", "แก้ไขฟอนต์", "แก้ไข font", "ตัดต่อฟอนต์",
    "ตัดต่อ font", "แปลงข้อความ", "แปลงภาพ", "แปลงรูป", "ตัดต่อหน้า"
  ],
  "exclude_keywords": [],
  "check_interval_seconds": 300,
  "mode": "auto_offer",
  "desktop_notification": true,
  "auto_open_browser": true,
  "access_token": "YOUR_ACCESS_TOKEN",
  "auto_offer_config": {
    "price": 10,
    "deliver_in_days": 1,
    "message": "สวัสดีครับ สนใจรับงานแก้ไขภาพ/เอกสาร/รีทัชครับ งานไว ละเอียด พร้อมเริ่มงานทันทีครับ"
  }
}
```
