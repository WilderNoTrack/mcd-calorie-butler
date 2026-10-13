# 麦当劳 MCP 调用手册（实测）

以下参数和返回都在 2026-10-12 至 13 日用真实 Token 调用过。服务地址 `https://mcp.mcd.cn`，Streamable HTTP，`Authorization: Bearer <MCP Token>`，每分钟最多 600 次。

## 本 Skill 用到的工具

| 工具 | 什么时候用 | 关键参数 | 注意 |
|---|---|---|---|
| `now-time-info` | 每次排餐前 | 无 | 用它的日期，不用模型自己以为的日期 |
| `list-nutrition-foods` | 建档时、每天第一次排餐前 | 无 | `data` 是紧凑表格：`[160]{productName,...,energyKcal,protein,...}:` 加逐行 CSV，交给 `nutrition load` 解析 |
| `query-nearby-stores` | 找门店 | `beType`=1（到店）、`searchType`=2（按位置）、`city`、`keyword` | 不传 `searchType` 默认查收藏门店；`businessStatus` 为 false 表示此刻没营业 |
| `query-meals` | 查菜单和现价 | `storeCode`、`orderType`=1、`beType`=1；未来时间加 `reservationDate`（`yyyy-MM-dd HH:mm`） | 价格是**元**的字符串，如 `"36.5"` |
| `query-meal-detail` | 查套餐里能换什么、差价、特调 | 同上 + `code` | `diffPrice` 形如 `"- ¥0.5"`；特调在 `choices[].modification` |
| `calculate-price` | 核价 | 同上 + `items` | 返回金额单位是**分**：3400 = ¥34.0。到店自取不要传 `beCode` |
| `create-order` | 用户确认后下单 | 与核价相同 + `takeWayCode` | `takeWayCode` 来自核价返回的 `takeWayList`：`eat-in` 堂食、`take-in-store` 外带 |
| `query-order` | 用户付款后查状态 | `orderId` | |
| `order-list` | 学口味（可选） | 无 | 只返回近期到店/外送订单，可能为空，空就用大众默认值 |

## 套餐的 items 怎么传

脚本的 `plan.calculate_price_items` 已经拼好，直接用。格式：

```json
[{"productCode": "9900005462", "quantity": 1, "roundList": [
  {"round": "1", "comboItemList": [{"code": "1406", "quantity": 1}]},
  {"round": "2", "comboItemList": [{"code": "4437", "quantity": 1}]},
  {"round": "3", "comboItemList": [{"code": "3071", "quantity": 1}]}
]}]
```

实测：板烧鸡腿堡三件套 + 小杯玉米杯 + 无糖可乐 → `"price":3400`。

## 特调（口味）怎么传

`query-meal-detail` 里每个可特调的餐品有 `modification.items[].values[]`。两种组：

- **可去掉的配料**（巨无霸的酱、吉士、生菜、酸黄瓜、洋葱）：每项都有 `selectedKey`（`0-1`）和 `unselectedKey`（`0-0`）。去掉一样时，**同组所有配料都要传**：去掉的用 `unselectedKey`、数量 0，其余用 `selectedKey`、数量 1。
- **单选项**（饮料的标准/去冰/多冰/少冰）：只有 `selectedKey`，传选中的那一个，数量 1。去冰的 key 是 `0-0`。

实测：巨无霸三件套 + 去酸黄瓜 + 可乐去冰，`calculate-price` 正常返回 ¥36.0（小食换了小杯玉米杯）。脚本的 `apply_tastes` 就是按这个规则拼的。

## 实测踩过的坑

- **门店不营业**：`query-meals` 返回 `code 600057`，"门店可能已关闭或不在营业时间"。即使门店写着 00:00–23:59，深夜也可能返回这个。改用 `reservationDate` 预约，或换门店。
- **编码不对或售罄**：`calculate-price` 返回 `code 60006`，"商品已售罄或不可售"。重新查菜单，别换个编码硬试。
- **早餐菜单**：早餐时段（约 10:30 前）菜单和正餐不同，按取餐时间传 `reservationDate`。
- **名字对不上营养表**：套餐详情里叫"纯牛奶"，营养表里叫"纯牛奶（盒装）"；新品（如"月下相思扭扭薯"）营养表里还没有。脚本会做别名和去括号匹配，仍查不到就标"无官方营养数据"，不会拿去排进热量方案。
- **返回格式**：大多数工具把 JSON 放在一段 Markdown 字段说明后面，以 `{"success":...}` 开头。原样存文件交给脚本即可，脚本会自己抠出来。
