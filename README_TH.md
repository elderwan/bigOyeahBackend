# FitBooking Backend

## ภาพรวม

โฟลเดอร์นี้เป็นโครงสร้างพื้นฐานของ backend สำหรับระบบจองเทรนเนอร์ส่วนตัว FitBooking โดยยึด `schema.sql`, `triggers.sql` และเอกสารเทคนิค MySQL เป็นแหล่งข้อมูลหลัก

เทคโนโลยีที่ใช้:

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x AsyncSession
- AsyncEngine แยกสำหรับ dynamic DDL
- MySQL 8.0.16+
- aiomysql
- Pydantic Settings

## หลักการฐานข้อมูล

1. `schema.sql` สร้างฐานข้อมูลและ 19 ตารางถาวร
2. `triggers.sql` ติดตั้ง trigger 12 ตัวที่บังคับใช้กฎข้ามตารางและสถานะการจอง
3. ตาราง `coach_schedule_<coach_no>` ไม่อยู่ใน `schema.sql`
4. backend สร้าง dynamic schedule table หลังจากมีข้อมูล `coach` แล้ว
5. ชื่อ table ต้องสร้างจาก `coach.coach_no` ที่อ่านจากฐานข้อมูลเท่านั้น
6. ค่า business ทั้งหมดใช้ SQLAlchemy bound parameters
7. MySQL DDL มี implicit commit จึงต้องแยก transaction ของ DML และ DDL

## การติดตั้ง

สร้าง virtual environment:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

หากติดตั้ง Python ผ่าน Python Launcher บน Windows:

```powershell
cd C:\Users\Lenovo\Desktop\bigOyeahBackend\bigOyeahBackend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

ตรวจสอบ environment:

```powershell
python --version
pytest -q
ruff check app tests
```

คัดลอก environment file:

```powershell
Copy-Item .env.example .env
```

แก้ไขค่าเชื่อมต่อให้ตรงกับผู้ใช้ MySQL:

```env
DATABASE_URL=mysql+aiomysql://fitbooking_app:change_me@127.0.0.1:3306/fitbooking?charset=utf8mb4
DDL_DATABASE_URL=mysql+aiomysql://fitbooking_ddl:change_me@127.0.0.1:3306/fitbooking?charset=utf8mb4
```

สำหรับ Aiven MySQL ให้ดาวน์โหลด `ca.pem` จากหน้า Overview ของ service ใน Aiven Console
แล้วกำหนดค่าการตรวจสอบ TLS โดยห้ามปิดการตรวจสอบ certificate หรือ hostname:

```env
DATABASE_SSL_REQUIRED=true
DATABASE_SSL_CA=C:\path\to\aiven-ca.pem
```

เมื่อเปิดใช้ SSL แล้ว backend จะไม่เริ่มทำงานหากไม่พบไฟล์ CA เพื่อป้องกันการ
เชื่อมต่อโดยใช้ certificate ที่ไม่ได้รับการตรวจสอบ

ควรแยกสิทธิ์ database user:

- `fitbooking_app`: SELECT, INSERT, UPDATE และสิทธิ์ที่จำเป็นต่อการใช้งานปกติ
- `fitbooking_ddl`: ใช้ CREATE และ REFERENCES เฉพาะการสร้าง dynamic schedule table

## การเตรียมฐานข้อมูล

รัน `schema.sql` ก่อน จากนั้นติดตั้ง trigger ด้วย script mode:

```bash
mysql -u root -p < ..\schema.sql
mysql -u root -p < ..\triggers.sql
```

`triggers.sql` มีคำสั่ง `DELIMITER` จึงไม่ควรส่งผ่าน JDBC statement แบบปกติใน DataGrip

backend นี้ไม่เรียก `Base.metadata.create_all()` เพราะโครงสร้างฐานข้อมูลต้องตรงกับ SQL ที่จัดทำไว้แล้ว

## Unified API response

ทุก JSON response จะถูกห่อด้วย envelope เดียวกัน:

```json
{
  "success": true,
  "code": 200,
  "message": "Success",
  "data": {},
  "errors": null,
  "meta": null,
  "requestId": "request-id",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

ระบบรองรับ `X-Request-ID` จาก client หรือสร้าง UUID ใหม่ให้เอง และส่งค่าเดิมกลับ
ใน response header พร้อมเก็บไว้ใน `request.state` และ `ContextVar`
สำหรับใช้ใน service/logging. ตัวอย่าง endpoint สำหรับตรวจสอบ envelope:

- `GET /api/v1/response-demo`
- `POST /api/v1/response-demo`
- `GET /api/v1/response-demo/http-error`
- `GET /api/v1/response-demo/server-error`

## การรัน API

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

เอกสาร API:

- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `GET http://localhost:8000/api/v1/health`

## Endpoint พื้นฐาน

### ตรวจสอบระบบ

```http
GET /api/v1/health
```

### อ่านข้อมูลโค้ช

```http
GET /api/v1/coaches/{coach_id}
```

### สร้าง dynamic schedule table

```http
POST /api/v1/coaches/{coach_id}/schedule
```

request นี้รับเฉพาะ `coach_id` ไม่รับ `table_name` หรือ `coach_no` จาก frontend

ลำดับการทำงาน:

1. อ่าน `coach_no` จากตาราง `coach`
2. ตรวจสอบด้วย regex `^[0-9]{4,8}$`
3. สร้างชื่อ `coach_schedule_<coach_no>`
4. commit transaction ปกติก่อนทำ DDL
5. ใช้ `DDL_DATABASE_URL` ผ่าน `AsyncEngine` แยก
6. สร้างตารางที่มี slot ทุก 10 นาที
7. บันทึกชื่อ table ลง `schedule_registry`
8. หากการบันทึก `schedule_registry` ล้มเหลวและเป็นตารางที่เพิ่งสร้าง ระบบจะลบ dynamic table ที่สร้างค้างไว้

### อ่าน schedule slots

```http
GET /api/v1/coaches/{coach_id}/schedule/slots?start_at=2026-10-12T09:00:00&end_at=2026-10-12T10:20:00
```

service จะอ่านชื่อ table จาก `schedule_registry` และตรวจสอบชื่อซ้ำก่อนนำไปใช้เป็น SQL identifier

### สร้าง booking

```http
POST /api/v1/bookings
```

ตัวอย่าง body:

```json
{
  "member_id": 31,
  "coach_id": 1,
  "course_id": 1,
  "gym_id": 1,
  "package_id": null,
  "booking_date": "2026-10-13",
  "start_time": "09:00:00",
  "duration_minutes": 60,
  "break_minutes": 10,
  "service_mode": "GYM",
  "service_district": null,
  "service_address": null,
  "price": "1200.00"
}
```

booking service จะ lock schedule slots ด้วย `FOR UPDATE`, ตรวจสอบว่า slot ทุก 10 นาทีว่างครบ, สร้าง booking เป็น `PENDING`, และเปลี่ยน slot เป็น `BOOKED` หรือ `BREAK`

## ชื่อ field และ enum

API ต้องใช้ชื่อ field แบบ `snake_case` ให้ตรงกับ SQL เช่น `coach_id`, `booking_date`, `start_time`, `duration_minutes`, `service_mode`, `payment_status`

ห้ามเปลี่ยนเป็น camelCase ใน request หรือ response หลัก

enum สำคัญ:

- `users.role`: `MEMBER`, `COACH`, `ADMIN`
- `coach.coach_level`: `BEGINNER`, `INTERMEDIATE`, `ADVANCED`, `MASTER`
- `booking.status`: `PENDING`, `CONFIRMED`, `CANCELLED`, `COMPLETED`, `NO_SHOW`
- `booking.service_mode`: `GYM`, `HOME`
- `orders.payment_status`: `UNPAID`, `PAID`, `CANCELLED`, `REFUNDED`
- schedule slot `status`: `AVAILABLE`, `BOOKED`, `BREAK`, `BLOCKED`

## Validation ที่ backend ต้องรักษา

- `coach_no` ต้องเป็นตัวเลข 4-8 หลัก
- `start_time` ต้องอยู่บน grid ทุก 10 นาที
- `duration_minutes` ต้องหารด้วย 10 ลงตัว
- `break_minutes` ต้องเป็น 10, 20 หรือ 30
- `GYM` ต้องมี `gym_id` และไม่มี home-service fields
- `HOME` ต้องมี `service_district`, `service_address` และไม่มี `gym_id`
- ห้ามรับ dynamic table name หรือ raw SQL จาก frontend
- ห้ามเปิดเผย `password_hash` ใน response
- ห้ามลบ booking หรือ orders แบบ physical delete

## งานตามเวลา

งานต่อไปควรแยกเป็น scheduler process หรือ external scheduler ไม่ควรเริ่มซ้ำในทุก Uvicorn worker:

- ยกเลิก booking ที่ `status = 'PENDING'` และ `expires_at` หมดอายุ
- คืน slot ที่ถูกจอง
- สร้าง slot ล่วงหน้าอย่างน้อย 60 วันจาก `coach_weekly_template`
- คำนวณ `coach_kpi_record` ทุกวันที่ 1 เวลา 00:30
- อัปเดต `fitness_profile` จาก `review_member`

## โครงสร้างโค้ด

```text
backend/
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── schemas/
│   └── services/
├── tests/
├── .env.example
├── requirements.txt
└── pyproject.toml
```

โค้ดชุดนี้เป็น scaffold ที่พร้อมต่อยอด authentication, payment service, package service, review service, KPI job และ scheduler โดยไม่ย้าย dynamic DDL กลับเข้า `schema.sql`
