# FitBooking — 后端查漏补缺与缺陷修复规范文档
## (Backend Gap & Improvement Specification for AI Agent)

> **文档性质**：实机测试发现问题集与待补全规范（供后端 AI Agent 直接修复实施）  
> **编写者**：前端与集成测试 AI Agent (Pair Programming Agent)  
> **测试工具**：Playwright MCP (`playwright-mcp`)、Chrome DevTools MCP (`chrome-devtools-mcp`)、PowerShell API Client  
> **测试日期**：2026-10-14  
> **服务环境**：FastAPI (`http://localhost:8000/api/v1`) + MySQL (Aiven Cloud / Local) + Next.js 14 前端 (`http://localhost:3000`)  
> **全量测试账号**（密码均为 `DemoPass123!`）：
> - **Member**：`alex.demo` (`user_id: 1`, `member_id: 1`)
> - **Trainer / Coach**：`tan.coach` (`user_id: 3`, `coach_id: 1`, `coach_no: "1001"`)
> - **Admin**：`admin.demo` (`user_id: 2`, `role: ADMIN`)

---

## 目录
1. [严重缺陷与崩溃项 (P0 / Critical Bugs)](#一严重缺陷与崩溃项-p0--critical-bugs)
2. [缺失接口项 (P1 / Missing Endpoints)](#二缺失接口项-p1--missing-endpoints)
3. [数据序列化与格式规范缺陷 (P1 / Data Format Inconsistencies)](#三数据序列化与格式规范缺陷-p1--data-format-inconsistencies)
4. [业务闭环与关联逻辑缺陷 (P2 / Business Logic Gaps)](#四业务闭环与关联逻辑缺陷-p2--business-logic-gaps)
5. [生产可用性与运维增强项 (P3 / Operational Readiness)](#五生产可用性与运维增强项-p3--operational-readiness)
6. [后端 AI Agent 实施步骤清单](#六后端-ai-agent-实施步骤清单)

---

## 一、严重缺陷与崩溃项 (P0 / Critical Bugs)

### 1. `POST /bookings` (学员预约创建) 报 422 及 500 严重崩溃

#### 问题 1.1：`BookingCreateRequest` 强行要求前端传递 `price` (报 422 Field required)
- **现象**：
  前端根据文档 `API_MEMBER.md` 构造预约请求发送至 `POST /api/v1/bookings`，后端返回：
  ```json
  {
    "success": false,
    "code": 422,
    "message": "Request validation failed",
    "errors": [
      {
        "field": "price",
        "code": "missing",
        "message": "Field required"
      }
    ]
  }
  ```
- **根本原因**：
  在 [`backend/app/schemas/booking.py`](file:///d:/workspace/idea/CMU/database/termProject/backend/app/schemas/booking.py) 第 21 行：
  ```python
  price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
  ```
  `price` 被定义为无默认值的必填字段。而在电商与预约安全规范中，前端不允许、也不应该决定课程价格。应由后端从 `courses.price_per_session` 结合 `member.level_id` 自动计算最终应收金额。
- **修复方案**：
  在 `BookingCreateRequest` 中将 `price` 改为可选：
  ```python
  price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
  ```
  在 `BookingService.create_booking` 中，若 `payload.price is None`，根据 `course_id` 查询课程单价，并结合 `member_id` 对应的会员折扣率 (`1 - discount_rate`) 自动计算 `price`。

---

#### 问题 1.2：`BookingResponse` 校验 `datetime.timedelta` 导致 500 崩溃
- **现象**：
  当补齐 `price` 重新提交 `POST /api/v1/bookings` 时，接口抛出未捕获异常，导致 `500 Internal server error`：
  ```json
  {
    "success": false,
    "code": 500,
    "message": "Internal server error",
    "errors": [{"field": "request", "code": "internal_server_error", "message": "An unexpected error occurred"}]
  }
  ```
- **复现与深层追踪**：
  通过 Python 脚本直调排查，真实报错栈如下：
  ```text
  pydantic_core._pydantic_core.ValidationError: 4 validation errors for BookingResponse
  start_time
    Input should be a valid time [type=time_type, input_value=datetime.timedelta(seconds=50400), input_type=timedelta]
  end_time
    Input should be a valid time [type=time_type, input_value=datetime.timedelta(seconds=54000), input_type=timedelta]
  ```
- **根本原因**：
  在 MySQL 中，`booking.start_time` 和 `end_time` 为 `TIME` 类型字段。通过 SQLAlchemy + `aiomysql` 读取出的底层 Python 类型是 `datetime.timedelta`。
  Pydantic v2 的 `BookingResponse` 中定义了：
  ```python
  start_time: time
  end_time: time
  ```
  Pydantic v2 默认**拒绝**将 `timedelta` 自动隐式转换为 `time`，直接抛出 `ValidationError`，导致控制器层未捕获该异常而向客户端返回 500。
- **修复方案**：
  在 `BookingResponse` 中加入字段前置验证器或序列化支持：
  ```python
  from datetime import time, timedelta
  from pydantic import field_validator

  class BookingResponse(BaseModel):
      ...
      start_time: time | str
      end_time: time | str

      @field_validator("start_time", "end_time", mode="before")
      @classmethod
      def parse_time_or_delta(cls, v):
          if isinstance(v, timedelta):
              total_seconds = int(v.total_seconds())
              hours = total_seconds // 3600
              minutes = (total_seconds % 3600) // 60
              seconds = total_seconds % 60
              return time(hour=hours, minute=minutes, second=seconds)
          return v
  ```

---

## 二、缺失接口项 (P1 / Missing Endpoints)

### 1. 教练端聊天消息接口缺失 (返回 404 Not Found)
- **缺失接口**：
  1. `GET /api/v1/coaches/me/messages?member_id={id}`
  2. `POST /api/v1/coaches/me/messages` (Payload: `{ "member_id": 1, "message_text": "..." }`)
- **现状**：
  [`backend/app/api/routes/member_features.py`](file:///d:/workspace/idea/CMU/database/termProject/backend/app/api/routes/member_features.py) 中实现了学员端的消息收发（`GET/POST /members/me/messages`），但 [`backend/app/api/routes/coaches.py`](file:///d:/workspace/idea/CMU/database/termProject/backend/app/api/routes/coaches.py) 完全没有实现教练端的消息接口，导致教练在 Trainer Space 发送消息时全部报 404。
- **待实现规范**：
  - **身份鉴权**：校验当前登录用户必须为 `role == "COACH"`，并获取对应的 `coach_id`。
  - **`GET /coaches/me/messages`**：
    - 查询与指定 `member_id`（若未传则返回所有最近互动学员列表）的聊天记录。
    - 自动将收到的学员消息更新标记为 `read_at = NOW()`。
  - **`POST /coaches/me/messages`**：
    - 写入数据库中的公共消息表（如 `coach_member_message` 或 `messages` 表）。
    - 写入字段：`coach_id`, `member_id`, `sender_role='COACH'`, `message_text`, `created_at=NOW()`。
    - 返回标准 `MessageResponse` 结构。

---

### 2. 教练课后对学员评价接口缺失 (`POST /coaches/me/member-reviews`)
- **缺失接口**：
  `POST /api/v1/coaches/me/member-reviews`
- **当前现状**：
  在 `API_COACH.md` 中有明确接口定义，但代码库中未挂载该路由（测试调用直接返回 404）。
- **待实现规范**：
  - **请求体**：
    ```json
    {
      "booking_id": 1,
      "completion_score": 5,
      "proficiency_score": 4,
      "training_area": "LOWER_BODY",
      "training_type": "STRENGTH",
      "coach_note": "Great hip hinge mechanics. Ready to increase squat load next week."
    }
    ```
  - **逻辑校验**：
    1. 校验 `booking.coach_id` 与当前教练一致。
    2. 校验 `booking.status == 'COMPLETED'`。
    3. 校验该 `booking_id` 是否已有教练评价，避免重复提交 (已有则返回 409)。
  - **数据写入**：写入 `review_member` 数据表。

---

### 3. 教练临时请假与指定槽位锁定接口 (`POST /coaches/me/schedule/block`)
- **业务缺口**：
  目前教练排期只有根据每周常规模板全量生成的逻辑（`POST /coaches/{coach_id}/schedule`）。当教练某天需要临时请假（例如某周五下午 14:00~16:00），目前系统无法锁定这部分槽位，容易被学员选走。
- **推荐接口规范**：
  `POST /api/v1/coaches/me/schedule/block`
  ```json
  {
    "date": "2026-10-23",
    "start_time": "14:00",
    "end_time": "16:00",
    "reason": "Personal medical appointment"
  }
  ```
- **处理逻辑**：
  检查动态排期表 `coach_schedule_<coach_id>` 中对应时间段内的 10 分钟槽位：
  - 若槽位已为 `BOOKED`：返回 `409 Conflict`（提示已有已支付预订，请先联系管理员或改签）。
  - 若槽位为 `AVAILABLE`：更新为 `status = 'BLOCKED', remark = :reason`。

---

## 三、数据序列化与格式规范缺陷 (P1 / Data Format Inconsistencies)

### 1. `GET /members/me/bookings` 时间输出为 ISO 持续时间格式 (`PT9H10M`)
- **现象**：
  调用 `GET /api/v1/members/me/bookings` 时，返回的 `start_time` 和 `end_time` 为：
  ```json
  {
    "booking_id": 2,
    "booking_date": "2026-10-13",
    "start_time": "PT9H10M",
    "end_time": "PT10H10M"
  }
  ```
- **根本原因**：
  FastAPI 的 Pydantic 模型在序列化 `datetime.timedelta` 对象时，默认采用了 ISO-8601 Duration 格式（`PT9H10M` 表示 9 小时 10 分钟）。
- **严重影响**：
  前端 JavaScript 的 `new Date("2026-10-13 " + start_time)` 无法解析该格式，直接返回 `Invalid Date`，导致时间卡片无法正常格式化。
- **修复方案**：
  在 Pydantic 响应模型中，显式将时间格式化为 `HH:MM:SS` 或 `HH:MM`：
  ```python
  @field_serializer("start_time", "end_time")
  def serialize_time_format(self, v: timedelta | time | str) -> str:
      if isinstance(v, timedelta):
          ts = int(v.total_seconds())
          return f"{ts // 3600:02d}:{(ts % 3600) // 60:02d}:{ts % 60:02d}"
      if isinstance(v, time):
          return v.strftime("%H:%M:%S")
      return str(v)
  ```

---

## 四、业务闭环与关联逻辑缺陷 (P2 / Business Logic Gaps)

### 1. 课时包购买未返回 `order_id` 与支付关联信息
- **现象**：
  调用 `POST /api/v1/members/me/packages/purchase` 返回：
  ```json
  {
    "package_id": 3,
    "member_id": 1,
    "package_type": "5+1",
    "total_sessions": 6,
    "remaining_sessions": 6,
    "price": "3400.00",
    "status": "ACTIVE"
  }
  ```
- **缺陷**：
  响应数据中没有包含 `order_id`。如果用户选择 PromptPay 或信用卡支付，前端无法拿到流水号进行对账或拉取支付二维码。
- **修复方案**：
  在购买课时包时，后端应在 `orders` 表中同步插入一条 `order_type = 'PACKAGE'` 的订单记录，并在响应中返回：
  ```json
  {
    "package_id": 3,
    "order_id": 204,
    "total_amount": "3400.00",
    "payment_method": "PROMPTPAY",
    "payment_status": "PAID",
    "expire_date": "2027-04-12"
  }
  ```

---

### 2. 评价提交后的教练均分与 KPI 统计联动滞后
- **现象**：
  当学员通过 `POST /members/me/reviews` 给教练评分后，`coach` 表中的 `average_rating` 和当月 `coach_kpi_record` 表中的数据没有自动联动更新，只有等管理员手动点击“Recalculate”时才会刷新。
- **修复方案**：
  在写入 `review_coach` 的事务中，自动执行以下更新：
  ```sql
  UPDATE coach
  SET average_rating = (
      SELECT ROUND(AVG((rating_professional + rating_communication + rating_punctuality + rating_effectiveness) / 4.0), 2)
      FROM review_coach rc
      JOIN booking b ON b.booking_id = rc.booking_id
      WHERE b.coach_id = :coach_id
  )
  WHERE coach_id = :coach_id;
  ```
  并更新该教练当月 `coach_kpi_record` 的 `avg_rating` 与 `is_achieved` 达标状态。

---

### 3. 课程超时自动完成定时任务 (Lifecycle Cron)
- **现状**：
  目前已确认上课（`CONFIRMED`）的预订，必须管理员在后台手动点击“Complete”才能变为 `COMPLETED`。
- **业务诉求**：
  应当配置后台轻量定时任务（例如使用 `APScheduler` 每 10 分钟扫描一次）：
  ```sql
  UPDATE booking
  SET status = 'COMPLETED', completed_at = NOW(), updated_at = NOW()
  WHERE status = 'CONFIRMED'
    AND TIMESTAMP(booking_date, end_time) < NOW() - INTERVAL 30 MINUTE;
  ```
  超时 30 分钟后自动转为已完成，并开放让学员在前端提交评价。

---

## 五、生产可用性与运维增强项 (P3 / Operational Readiness)

### 1. 审计日志高级多维度过滤接口 (`GET /admin/audit-log`)
- **现状**：`GET /admin/audit-log` 仅支持 `?limit=50`。
- **诉求**：管理端 UI 提供了精确检索功能，后端应支持如下 Query 参数：
  ```http
  GET /api/v1/admin/audit-log?entity_type=booking&action=UPDATE_BOOKING_STATUS&user_id=2&date_from=2026-10-01&date_to=2026-10-31&offset=0&limit=50
  ```

### 2. CSV 导出首部追加 UTF-8 BOM (`\xef\xbb\xbf`)
- **现状**：`GET /admin/reports/export` 导出的 CSV 流中包含泰文/中文（如地区名称 `นิมมาน`、场馆名称、学员姓名）。
- **缺陷**：Windows 平台的 Excel 打开没有 BOM 的 UTF-8 CSV 时会出现乱码。
- **修复方案**：在生成 CSV 字节流的第一帧写入 `codecs.BOM_UTF8` (`b'\xef\xbb\xbf'`)。

### 3. PromptPay EMVCo 字符串生成接口
- **诉求**：
  提供 `POST /api/v1/orders/{order_id}/promptpay-qr`，生成包含金额的泰国 PromptPay 标准 EMVCo 字符串供前端展示二维码，方便手机银行扫码付款。

---

## 六、后端 AI Agent 实施步骤清单

后端 AI Agent 可以按照如下优先级顺序逐步修复：

1. [ ] **【第一步·解阻塞】修复 `app/schemas/booking.py`**
   - 将 `price` 改为可选 (`Decimal | None = None`)。
   - 为 `BookingResponse` 的 `start_time` 和 `end_time` 增加对 `datetime.timedelta` 的自动转换器。
2. [ ] **【第二步·补接口】补齐 `app/api/routes/coaches.py` 中的消息与评价路由**
   - 实现 `GET /coaches/me/messages` 与 `POST /coaches/me/messages`。
   - 实现 `POST /coaches/me/member-reviews`。
   - 增加请假锁槽位接口 `POST /coaches/me/schedule/block`。
3. [ ] **【第三步·修格式】统一时间格式输出**
   - 在 `MemberBookingResponse` 中将 `start_time` / `end_time` 序列化为规范的 `HH:MM:SS` 字符串。
4. [ ] **【第四步·强化业务】关联订单与评价联动**
   - 课时包购买响应增加 `order_id` 及订单支付状态。
   - 提交学员评价后自动重算教练 `average_rating`。
5. [ ] **【第五步·报表与维护】**
   - 导出 CSV 增加 UTF-8 BOM。
   - 审计日志支持 `entity_type`、`action`、`date_from`、`date_to` 过滤参数。
