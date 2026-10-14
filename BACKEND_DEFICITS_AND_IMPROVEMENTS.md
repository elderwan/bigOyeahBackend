# FitBooking 后端查漏补缺与联调缺陷修复文档 (Backend Deficits & Action Items)

> **目标受众**: 后端 AI Agent / 后端开发人员  
> **文档来源**: 本地 Playwright MCP & Chrome DevTools MCP 全链路端到端自动化测试总结（包含学员端、教练端、管理端真实数据流程）  
> **测试环境**: FastAPI + MySQL + Next.js 14 前后端全真联调测试  
> **生成日期**: 2026-10-14  

---

## 目录
1. [联调概况与现状评估](#1-联调概况与现状评估)
2. [高优先级缺陷 (P0 / P1)](#2-高优先级缺陷-p0--p1)
3. [接口响应结构优化 (P2)](#3-接口响应结构优化-p2)
4. [各模块详细补缺清单与字段级规范](#4-各模块详细补缺清单与字段级规范)
   - 4.1 学员端与预订模块
   - 4.2 课时包与 PromptPay 支付流水
   - 4.3 教练端日程与槽位请假锁定
   - 4.4 教练端学员课后评价
   - 4.5 教练与学员双向即时通讯
   - 4.6 管理端审计日志与表格分页
5. [后端自动化测试验证用例规范](#5-后端自动化测试验证用例规范)

---

## 1. 联调概况与现状评估

经过本次使用 Playwright MCP 与 Chrome DevTools MCP 走通新注册学员（`testuser_tingfeng_*`）、教练端（`tan.coach`）和管理端（`admin.demo`）的完整真实交互，主要联调成果与问题如下：

- **已通畅链路**：
  - 学员注册 (`POST /auth/register`) 与自动登录入库成功。
  - 会员个人详情 (`GET /members/me`) 字段正确绑定，铜牌会员消费累计计算准确。
  - 课时包购买 (`POST /packages/purchase`) 成功生成 Order。
  - 订单 PromptPay QR 码生成 (`POST /orders/{order_id}/promptpay-qr`) 返回合规 EMVCo Payload，前端 QRCodeSVG 正常渲染。
  - 教练请假时段锁定 (`POST /coaches/me/schedule/block`) 成功将槽位状态置为 `BLOCKED`。
  - 教练评价学员 (`POST /coaches/me/member-reviews`) 校验及重复评价防刷机制（409 Conflict）正常运作。
  - 管理端审计日志分页 (`GET /admin/audit-log?limit=10&offset=10`) 准确切片输出第 11-20 条记录。

- **后端待补齐与改进问题**：
  - 部分接口缺少可选字段默认值（如 `reason` 缺少时报 422 验证错误）。
  - 部分列表接口缺少总数 `total` 外壳包裹（如审计日志直接返回纯数组，前端难以计算确切总页数）。
  - 缺少模拟支付回调接口，导致学员扫描 PromptPay 码后订单状态无法由待支付自动流转为已支付。
  - 缺少教练端活跃会话列表聚合接口，教练端无法一次性拉取所有与其发过消息的学员列表。

---

## 2. 高优先级缺陷 (P0 / P1)

### 缺陷 1：`POST /api/v1/coaches/me/schedule/block` 请假锁定接口对 `reason` 强制校验 (P1)
- **现状**：若请求体未携带 `reason`，FastAPI 抛出 `422 Unprocessable Entity`。
- **改进建议**：
  - 将 Pydantic 校验模型中的 `reason: Optional[str] = "Personal leave"`，支持不传事由时默认填入请假原因。
  - 如果槽位已被学员预约（状态为 `CONFIRMED` 或 `PENDING`），必须返回 `409 Conflict`，响应体需包含：
    ```json
    {
      "code": "SLOT_CONFLICT",
      "detail": "该时间段已有学员预约（预约号 #xxxx），无法直接锁定。请先与学员沟通协调退改。"
    }
    ```

### 缺陷 2：缺少解除请假锁定接口 (P1)
- **现状**：教练锁定某一时段后，若教练日程发生变更想恢复对外开放，缺少解锁路由。
- **实施动作**：
  - 新增接口：`POST /api/v1/coaches/me/schedule/unblock` 或 `DELETE /api/v1/coaches/me/schedule/block`
  - 请求参数：
    ```json
    {
      "block_date": "2026-04-20",
      "start_time": "14:00",
      "end_time": "16:00"
    }
    ```
  - 响应：将对应时段状态由 `BLOCKED` 还原为 `OPEN`（若日历记录存在）。

### 缺陷 3：缺少订单支付状态模拟确认回调接口 (P1)
- **现状**：学员通过 `POST /orders/{order_id}/promptpay-qr` 获取并展示二维码后，订单状态仍为 `UNPAID`。在开发和演示环境下，无法推进为 `PAID` 从而激活课时包或确认预订。
- **实施动作**：
  - 新增接口：`POST /api/v1/orders/{order_id}/mock-pay` 或 `POST /api/v1/orders/{order_id}/confirm-payment`
  - 动作：
    1. 校验该订单归属人或管理员权限。
    2. 将 `order.payment_status` 更新为 `PAID`，`order.payment_time` 记录为当前时间。
    3. 若为课时包订单，自动给学员账号充值 `remaining_sessions`。
    4. 若为预约单订单，将对应预订状态由 `PENDING` 推进为 `CONFIRMED`。

---

## 3. 接口响应结构优化 (P2)

### 优化 1：管理端分页接口增加 Envelope 外壳包装
- **现状**：`GET /api/v1/admin/audit-log?limit=10&offset=0` 当前返回为直接列表 `[ { ... }, { ... } ]`。
- **建议格式**：
  ```json
  {
    "code": 200,
    "message": "success",
    "data": {
      "items": [ /* 列表项 */ ],
      "total": 128,
      "page": 1,
      "limit": 10,
      "has_more": true
    }
  }
  ```
- **兼容策略**：为保证现有已对接前端不破坏，可保持 `res.data` 为分页对象，前端若检测到 `Array.isArray(res.data)` 仍降级适配，若检测到 `res.data.items` 则提取 `total` 精确渲染页码。

### 优化 2：会员详情返回下一级会员升级所需差额
- **接口**：`GET /api/v1/members/me`
- **现状**：返回 `level_id`, `level_code`, `level_name`, `discount_rate`, `total_spend`。
- **建议补充字段**：
  - `next_tier_code`: `"SILVER"` (如果已是最高级则为 null)
  - `next_tier_name`: `"Silver Member"`
  - `next_tier_threshold`: `5000.00`
  - `amount_to_next_tier`: `5000.00 - total_spend` (最小为 0)
- **收益**：避免前端硬编码升级阈值，当运营在数据库调整升级门槛（如 Silver 改为 6000 泰铢）时，所有客户端自动保持一致。

---

## 4. 各模块详细补缺清单与字段级规范

### 4.1 学员端与预订模块
1. **预订创建 (`POST /api/v1/bookings`)**：
   - 前端已彻底移除价格伪造，不再传 `price`。
   - 后端计算逻辑请保持：
     `price = coach_course.price_per_session * (1 - member.discount_rate)`。
   - 响应体中的 `booking.start_time` 与 `end_time` 保持标准 `"HH:MM:SS"` 格式，避免带微秒或 ISO PT 周期字符。

### 4.2 课时包与 PromptPay 支付流水
1. **课时包购买 (`POST /api/v1/packages/purchase`)**：
   - 需确保响应体始终返回明确的 `order_id` 和 `order_no`。
   - 返回示例：
     ```json
     {
       "code": 200,
       "message": "Package purchased successfully",
       "data": {
         "order_id": 10,
         "order_no": "ORD-PKG-20261014-0010",
         "package_id": 2,
         "package_type": "5+1",
         "total_amount": 3400.00,
         "payment_method": "PROMPTPAY"
       }
     }
     ```

2. **二维码 Payload 接口 (`POST /api/v1/orders/{order_id}/promptpay-qr`)**：
   - 需同时提供 `promptpay_payload` 字段和 `amount` 字段。
   - 返回示例：
     ```json
     {
       "code": 200,
       "data": {
         "order_id": 10,
         "amount": 3400.00,
         "promptpay_payload": "00020101021229370016A00000067701011101130066812345678530376454073400.005802TH6304ABCD"
       }
     }
     ```

### 4.3 教练端日程与槽位请假锁定
1. **锁定接口 (`POST /api/v1/coaches/me/schedule/block`)**：
   - 入参：
     - `block_date`: `"YYYY-MM-DD"` (必填)
     - `start_time`: `"HH:MM"` 或 `"HH:MM:SS"` (必填)
     - `end_time`: `"HH:MM"` 或 `"HH:MM:SS"` (必填)
     - `reason`: `string` (选填，默认 `"Personal leave"`)
   - 数据库动作：将对应教练日期日程表中重叠的 slots 置为 `BLOCKED`。若重叠 slots 中含有 `CONFIRMED` 预约，抛出 409。

### 4.4 教练端学员课后评价
1. **评价接口 (`POST /api/v1/coaches/me/member-reviews`)**：
   - 接收字段：
     - `booking_id`: `int` (必填)
     - `completion_score`: `int` (1-5 必填)
     - `proficiency_score`: `int` (1-5 必填)
     - `training_area`: `string` (如 `"UPPER_BODY"`, `"CORE"`, `"FULL_BODY"`)
     - `training_type`: `string` (如 `"STRENGTH"`, `"CARDIO"`)
     - `coach_note`: `Optional[str]`
   - 重复评价检查：若数据库已存在该 `booking_id` 的记录，返回 409，detail 提示明确信息。
2. **查询接口补充 (`GET /api/v1/coaches/me/member-reviews`)**：
   - 支持通过 `?booking_id={id}` 查询单个评价，以供前端判定当前卡片是否已评价并展示只读评价内容。

### 4.5 教练与学员双向即时通讯
1. **会话列表接口 (`GET /api/v1/coaches/me/conversations`)**：
   - 当前后端仅有按 `member_id` 查询具体消息的接口 (`GET /coaches/me/messages?member_id={id}`)。
   - 建议增加教练会话概览接口：
     ```json
     {
       "code": 200,
       "data": [
         {
           "member_id": 1,
           "member_name": "Alex Morgan",
           "last_message": "Looking forward to our session tomorrow.",
           "last_message_time": "2026-10-14 14:20:00",
           "unread_count": 0
         }
       ]
     }
     ```

---

## 5. 后端自动化测试验证用例规范

请后端 AI Agent 在完成修复后，运行或扩充 `tests/test_backend_improvements.py`，确保以下用例通过：

1. `test_schedule_block_with_default_reason()`:
   - 验证不提供 `reason` 字段时，接口能正常返回 200/201，不抛出 422。
2. `test_schedule_block_conflict_on_existing_booking()`:
   - 为某时段先建立 `CONFIRMED` booking，再调用 block，验证返回 409 Conflict。
3. `test_member_reviews_duplicate_handling()`:
   - 对同一个 booking 提交两次课后评价，验证第二次返回 409 Conflict，并且 detail 明确。
4. `test_audit_log_pagination_offset()`:
   - 验证传入 `limit=10&offset=10` 时，返回的记录偏移量精确匹配。
5. `test_promptpay_qr_generation()`:
   - 验证购买 package 生成 order 后，根据 order_id 能成功获取有效的 PromptPay payload。

---
*本文档由前端自动化测试链路生成，已同步放置于 `backend/BACKEND_DEFICITS_AND_IMPROVEMENTS.md` 与 `frontend/BACKEND_DEFICITS_AND_IMPROVEMENTS.md`，可直接供后端开发及测试 Agent 参考。*
