# MCP_INTEGRATION

## 使用的 MCP Server

| 项目 | 值 |
|---|---|
| 服务 | 麦当劳中国 MCP Server（mcd-mcp） |
| 地址 | `https://mcp.mcd.cn` |
| 协议 | Streamable HTTP |
| 鉴权 | 请求头 `Authorization: Bearer ${MCD_MCP_TOKEN}`，Token 只放环境变量 |
| 限流 | 每个 Token 每分钟 600 次 |

配置示例见 [mcp-config.example.json](mcp-config.example.json)。

## 使用的 Tool

| Tool | 在本 Skill 里做什么 | 读 / 写 |
|---|---|---|
| `now-time-info` | 确认今天日期和当前餐段（早餐菜单不同） | 读 |
| `list-nutrition-foods` | 官方营养表（160 种餐品的热量、蛋白质等），所有麦当劳热量的唯一来源 | 读 |
| `query-nearby-stores` | 找附近能到店取餐的门店和可预约时段 | 读 |
| `query-meals` | 门店当前在售菜单与现价，拿到套餐编码 | 读 |
| `query-meal-detail` | 套餐每轮可换的餐品、换配差价、特调选项（去酸黄瓜、去冰） | 读 |
| `calculate-price` | 按排好的配法和特调官方核价（单位：分） | 读 |
| `create-order` | 用户明确说"下单"后提交订单，返回支付链接 | **写，需用户确认** |
| `query-order` | 用户付款后查订单状态 | 读 |
| `order-list` | （可选）从历史订单学口味、找"老样子" | 读 |

不调用：`auto-bind-coupons`、`draw-lottery`、`mall-create-order`、`cancel-order`、`delivery-create-address` 等其他写操作，除非用户明确要求。

## 调用流程

```
建档  ─ list-nutrition-foods → butler.py nutrition load
       ─ query-nearby-stores → 用户选店 → profile set --store-code
       ─ query-meals → 用户选老样子 → base set --code
记账  ─ 麦当劳：butler.py log add --source mcd（按官方营养表）
       ─ 其他：AI 估算 → butler.py log add --source other（标注"估算"）
排餐  ─ now-time-info → butler.py today（这一顿的预算）
       ─ query-meals ＋ query-meal-detail × 3～6 个候选套餐
       ─ butler.py plan（味热比打分，生成 calculate_price_items，含口味特调）
       ─ calculate-price（原样传 items）→ butler.py price（分 → 元）
       ─ 方案卡给用户
下单  ─ 用户说"下单" → create-order（加 takeWayCode）→ 给支付链接
       ─ 用户付款后 query-order → butler.py log add --source mcd
```

## 业务价值

- **对用户**：控制热量的人也能放心吃麦当劳。不用查热量表、不用每次重复口味要求，超了也不用硬饿，一句话拿到一顿"吃得下、吃得爽、价格确定"的麦当劳。
- **对麦当劳**：把"减脂期不敢吃麦当劳"的人留下来。方案优先保留用户的老样子和最爱的餐品，只在必要时换配，并且全部落在官方菜单与官方换配选项里，最后走官方下单。
- **对开发者**：[MCP 调用手册](skill/mcd-calorie-butler/references/mcp-playbook.md) 记录了实测参数、特调传法和错误码，计算脚本可单独复用。

## 实测记录（2026-10-12 至 13 日，上海福州路餐厅，到店取餐，预约 19:00）

| 调用 | 结果 |
|---|---|
| `list-nutrition-foods` | 160 行，解析出 158 个不重复餐品 |
| `query-meals` | 99 个在售餐品；套餐价为元，如巨无霸三件套 `"36.5"` |
| `query-meal-detail` × 5 | 巨无霸三件套、板烧鸡腿堡三件套、麦辣鸡腿汉堡三件套、麦香鱼中套餐、麦乐鸡经典中套餐 |
| `calculate-price` 巨无霸三件套（默认） | 3650 分，脚本估算 ¥36.5 ✓ |
| `calculate-price` 巨无霸三件套 + 小杯玉米杯 + 无糖可乐 | 3600 分 ✓ |
| `calculate-price` 板烧鸡腿堡三件套 + 小杯玉米杯 + 无糖可乐 | 3400 分 ✓ |
| `calculate-price` 麦乐鸡经典中套餐 + 小杯玉米杯 + 纯牛奶 | 2500 分，脚本估算 ¥25.0 ✓ |
| `calculate-price` 麦乐鸡经典中套餐 + 小杯玉米杯 + 无糖可乐（去冰） | 2450 分，脚本估算 ¥24.5 ✓ |
| `calculate-price` 巨无霸三件套 + 去酸黄瓜 + 可乐去冰 | 接受特调参数，正常返回 |
| `query-meals` 深夜不带预约时间 | `600057` 门店不在营业时间 → Skill 改用 `reservationDate` |
| `calculate-price` 不存在的编码 | `60006` 商品已售罄或不可售 |

这些返回（已去掉 traceId，不含任何账户数据）保存在 [tests/fixtures](tests/fixtures)，离线测试和演示页都用它们。重新录制：`python tools/record_fixtures.py --time "yyyy-MM-dd HH:mm"`（只调用只读工具）。

开发过程中没有调用 `create-order`，没有产生任何订单。
