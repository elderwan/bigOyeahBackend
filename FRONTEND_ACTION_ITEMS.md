# FitBooking — 前端后续实施动作清单 (Frontend Action Items)

> **目标受众**: 前端开发工程师 / 全栈开发人员  
> **文档目的**: 指导前端团队在后端完成所有 P0/P1/P2/P3 缺陷修复与接口补齐后，系统性地完成前端联调接入与体验优化。  
> **接口标准**: FastAPI (`http://localhost:8000/api/v1`) + 统一响应外壳 `{ success, code, message, data, errors, meta, requestId, timestamp }`  
> **更新时间**: 2026-10-14  

---

## 目录
1. [学员端 (Member Space) 接入清单](#1-学员端-member-space-接入清单)
2. [教练端 (Trainer Space) 接入清单](#2-教练端-trainer-space-接入清单)
3. [管理端 (Admin Space) 接入清单](#3-管理端-admin-space-接入清单)
4. [公共与基础设施优化](#4-公共与基础设施优化)
5. [前后端接口联调自测检查表 (Checklist)](#5-前后端接口联调自测检查表-checklist)

---

## 1. 学员端 (Member Space) 接入清单

### 1.1 课程预约创建表单 (`POST /api/v1/bookings`)
- **改动动作**：
  - **移除价格伪造**：在提交预约表单的 Payload 中，彻底移除前端自算的 `price` 字段（或显式设为 `null`）。
  - **后端自动计价**：后端已接入 `coach_course.price_per_session * (1 - member.discount_rate)` 自动结算逻辑，并同步创建对应未支付的 `orders` 流水。
- **时间格式处理**：
  - 发送请求时 `start_time` 保持格式 `"10:00"`，必须严格对其 10 分钟网格 (`:00`, `:10`, `:20`, `:30`, `:40`, `:50`)。
  - `duration_minutes` 必须为 10 的倍数（如 60）。

### 1.2 预约列表与日程卡片渲染 (`GET /api/v1/members/me/bookings`, `/dashboard`)
- **改动动作**：
  - **移除 ISO Duration 兼容补丁**：后端底层已修复 `aiomysql` `timedelta` 序列化问题，返回的 `start_time` 和 `end_time` 现统一为标准字符串（例如 `"09:10:00"`）。
  - **时间格式化解绑**：前端代码中无需再使用正则匹配 `PT9H10M`，可直接使用标准 JavaScript 处理：
    ```typescript
    const sessionDate = new Date(`${item.booking_date}T${item.start_time}`);
    ```

### 1.3 课时包购买与 PromptPay 二维码核销 (`POST /api/v1/packages/purchase`)
- **改动动作**：
  - **获取订单关联信息**：调用购买接口后，后端响应的 `data` 已新增返回 `order_id`、`total_amount`、`payment_status`。
  - **扫码支付弹窗**：
    - 若学员勾选 `PROMPTPAY` 支付方式，弹窗中携带 `order_id` 调用 `POST /api/v1/orders/{order_id}/promptpay-qr`。
    - 取得返回的 `promptpay_payload` 字段后，使用前端已有的 `qrcode.react` (`QRCodeSVG`) 渲染 PromptPay 二维码。
    - **开发/演示环境支付模拟**：弹窗下方提供快捷测试按钮【模拟手机银行付款完成】，点击后调用新增接口 `POST /api/v1/orders/{order_id}/mock-pay`，订单自动流转为 `PAID`，弹窗自动关闭并刷新学员课时包余额。

### 1.4 会员等级进度条与升级差额 (`GET /api/v1/members/me`)
- **改动动作**：
  - 接口已补充下级升级目标信息：
    - `next_tier_code` (如 `"SILVER"`)
    - `next_tier_name` (如 `"Silver Member"`)
    - `next_tier_threshold` (如 `5000.00`)
    - `amount_to_next_tier` (如 `1600.00`，若已是顶级则为 `0`)
  - **UI 绑定**：个人中心等级卡片直接绑定 `amount_to_next_tier`，展示如：“还需消费 ฿1,600 即可升级至银牌会员”。无需前端硬编码阈值。

---

## 2. 教练端 (Trainer Space) 接入清单

### 2.1 教练即时通讯聊天面板 (`GET/POST /api/v1/coaches/me/messages`)
- **改动动作**：
  - **会话历史拉取**：教练点击左侧某学员后，发起 `GET /api/v1/coaches/me/messages?member_id={id}` 拉取对话列表。后端会自动将该学员发送给教练的未读消息置为已读。
  - **教练回复发送**：在输入框点击发送时，调用 `POST /api/v1/coaches/me/messages`：
    ```json
    {
      "member_id": 1,
      "message_text": "Looking forward to our session tomorrow."
    }
    ```
  - **会话聚合列表**：切换或加载聊天主页时，调用 `GET /api/v1/coaches/me/conversations` 一次性获取活跃学员列表、最后一条消息与未读气泡计数。

### 2.2 课后评价学员弹窗 (`POST /api/v1/coaches/me/member-reviews`)
- **改动动作**：
  - **触发入口**：在教练工作台的“已完成课程”或“预约详情”卡片上，展示【评价学员】(Review Trainee) 按钮。
  - **查询已评价状态**：调用 `GET /api/v1/coaches/me/member-reviews?booking_id={id}`：
    - 若已有评价，展示只读评分与评语，按钮置灰为【已完成评价】。
    - 若未评价，点击弹出评价模态框。
  - **表单提交**：
    ```json
    {
      "booking_id": 101,
      "completion_score": 5,
      "proficiency_score": 4,
      "training_area": "LOWER_BODY",
      "training_type": "STRENGTH",
      "coach_note": "Great hip hinge mechanics. Ready to increase squat load next week."
    }
    ```
  - **防刷提示**：若偶发重复提交收到 `409 Conflict`，Toast 友好提示“该课程已被评价过”。

### 2.3 日程槽位请假与锁定 (`POST /api/v1/coaches/me/schedule/block` & `unblock`)
- **改动动作**：
  - **请假申请按钮**：在教练日历界面头部增加【申请请假 / 锁定槽位】按钮。
  - **锁定提交**：
    ```json
    {
      "block_date": "2026-10-23",
      "start_time": "14:00",
      "end_time": "16:00",
      "reason": "Personal medical appointment"
    }
    ```
    *(注：`reason` 为选填，默认值为 "Personal leave")*
  - **冲突处理**：若该时间段内已有已支付预约，后端返回 `409 Conflict`，前端弹窗提示：“该时段已有学员预订，请先联系管理员或协调改签”。
  - **解除锁定**：在已锁定的红色槽位上提供【解除锁定】(Unblock) 按钮，调用 `POST /api/v1/coaches/me/schedule/unblock` 恢复为空闲开放状态。

---

## 3. 管理端 (Admin Space) 接入清单

### 3.1 审计日志分页表格 (`GET /api/v1/admin/audit-log`)
- **改动动作**：
  - 接口已支持 `limit` 和 `offset`，以及 `items` + `total` 响应外壳。
  - **翻页交互**：当用户在表格分页器切换到第 N 页时，传递参数：
    ```http
    GET /api/v1/admin/audit-log?limit=10&offset=${(page - 1) * 10}
    ```
  - 表格底部展示准确的总记录数 `total` 和总页数。

### 3.2 报表 CSV 导出下载 (`GET /api/v1/admin/reports/export`)
- **改动动作**：
  - 后端已为导出的 CSV 字节流头部写入了 UTF-8 BOM (`\xef\xbb\xbf`)。
  - 前端使用 `window.open(exportUrl)` 或 `blob` 下载后，在 Windows 系统原生 Excel 打开时中文与泰文（如清迈场馆名）将直接正常渲染，不再有任何乱码。

---

## 4. 公共与基础设施优化

### 4.1 Mock 支付确认工具函数封装
为了让前后端联调以及导师演示更加顺畅，建议在前端 API 客户端 (`src/lib/api/...`) 中封装支付确认函数：
```typescript
export async function mockConfirmPayment(orderId: number) {
  const res = await apiClient.post(`/orders/${orderId}/mock-pay`);
  return res.data;
}
```
当测试学员在前端点击“扫码已支付”或倒计时模拟完成时自动触发该函数，系统即可即时完成从 `UNPAID` 到 `PAID` 的闭环推进。

---

## 5. 前后端接口联调自测检查表 (Checklist)

| 序号 | 测试场景 | 预期前端交互与后端响应 | 状态 |
| :---: | :--- | :--- | :---: |
| 1 | 学员创建私教预约 | 不传 price，成功返回 201，start_time 为 "10:00:00" | [ ] |
| 2 | 查看学员预约日程 | 时间正常显示（如 10:00 - 11:00），无 Invalid Date 报错 | [ ] |
| 3 | 学员购买 5+1 课时包 | 返回中拿到 order_id，调 promptpay-qr 弹窗展示二维码 | [ ] |
| 4 | 触发 mock-pay | 课时包变为激活状态，剩余可用课时加 6 | [ ] |
| 5 | 教练查看学员会话 | GET /coaches/me/conversations 返回学员列表及未读数 | [ ] |
| 6 | 教练发送消息给学员 | POST /coaches/me/messages 成功，实时追加至聊天窗口 | [ ] |
| 7 | 教练评价已完成课程 | 提交 completion_score 等，成功扣入并在卡片显示已评 | [ ] |
| 8 | 教练请假锁定时段 | 空闲时段锁定成功变灰/红；有预订时段提交被阻止并弹 409 提醒 | [ ] |
| 9 | 教练解除时段锁定 | 点击已锁定槽位可成功 unblock 恢复为空闲 | [ ] |
| 10 | 管理员查看审计日志 | 翻页后表格数据准确切片，总页数准确显示 | [ ] |
