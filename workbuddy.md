# workbuddy.md · 麦麦热量管家的 WorkBuddy 使用记录

> 本文件用于核验本项目是否符合「WorkBuddy 联动活动奖励」条件，整理自腾讯 WorkBuddy 本地对话记录
> （`~/.workbuddy/projects/d-Program-10_Others-麦当劳mcp/*.jsonl`），按时间顺序保留用户输入、WorkBuddy 的执行动作与结果。
> 已去掉与本项目无关的一段对话；麦当劳 MCP Token、个人身体数据、账户积分与券包明细已脱敏或略去。

| 项目 | 内容 |
|---|---|
| 项目 | 麦麦热量管家 · 味热比（mcd-calorie-butler） |
| 工具 | 腾讯 WorkBuddy（Windows 桌面版），工作区 `D:/Program/10_Others/麦当劳mcp` |
| 会话 | `2e8bd14c-…`（10-12 22:58 → 10-13 11:08）、`4e9aa0b1-…`（10-13 11:02 → 11:05） |
| WorkBuddy 承担的工作 | 赛事调研与选题分析；Skill 的离线验证、安装；配置 mcd-mcp 连接器并真机联调；用 Skill 正式建档 |
| 说明 | Skill 的主体代码在其他编码工具中完成。WorkBuddy 联调中发现的两个问题，已按它的结论修复（见文末） |

---

## 一、赛事调研（10-12 22:58）

**用户**
> https://github.com/M-China/mcd-developer-innovation-challenge 看看这个 看看我还有没有什么机会 看看其他人的star

**WorkBuddy 执行**
- 读取赛事 README、`activityGuidelines.md` 和 `RANKING.md`
- 通过 `commits?path=RANKING.md` 拿到排行榜每小时的提交记录，逐个取 10-09 至 10-12 的历史快照，做名次—星数趋势
- 统计报名 Issue 总数与上榜项目数，画趋势图，生成看板 `mcd-challenge-report.html`

**WorkBuddy 结论（节选）**
> 报名 Issue 554 个，真正上榜（Star > 0）112 个，当前上榜门槛 5 星。门槛一天涨 1 星、榜单总星数每天约 ×1.47，按当前节奏外推，定榜时守住前 100 大概率需要 25～70 星。

**用户**
> 给我看看前三个项目是什么呀

**WorkBuddy 执行**：从报名 Issue 反查打码的 owner，找到前三名仓库并读完 README，拆解写进看板。总结出三条共同规律：README 开头先说"我回答了别人没回答的问题"；强调数字来自 MCP 真实返回、查不到不编；都提供免 Token 的离线演示。

## 二、选题（10-12 23:28 → 23:47）

**用户**
> 你帮我想想我能做什么 你有什么好的创意想法

**WorkBuddy 执行**
- 拉取麦当劳 MCP 工具列表（35 个），按全部报名而不只是榜单统计各赛道拥挤度
- 自我修正：发现"榜单只显示 Star > 0 的项目"，用它当分母会把"还没推广"误判为"没人做"，改用全部 558 个报名重算
- 给出若干方向，并指出"开发者工具 / 评测"赛道几乎没人

**用户**
> 你这个是啥意思没听懂 / 还是不懂现在项目在干嘛 / 还是不懂 / 你重新自己想想法

**WorkBuddy 执行**：改用"一眼看懂、一句话说清、能截图发出去"的标准，重新给出三个想法（同一份餐哪家店最便宜、外卖还是自己下楼、一张图看完整个菜单）。

最终选题是在其他工具里继续讨论后定下的：热量管家 + 味热比。

## 三、实测 Skill：离线验证与安装（10-13 10:16）

用户让 WorkBuddy 阅读工作区里已写好的 `mcd-calorie-butler`，弄清楚怎么用，并实际用一遍。

**WorkBuddy 执行**
1. 读 `README.md`、`SKILL.md`、`install.py`；检查是否已配置 mcd-mcp 连接器、是否有 Token（当时都没有）
2. `python -m unittest discover -s tests -v` → **12 个离线测试全部通过**
3. 用 `MCD_BUTLER_HOME` 指向隔离目录 `.demo-butler`，按 README 跑完整流程：
   `nutrition load`（158 项）→ `profile set` → `base set` → `taste add 去酸黄瓜` → `log add`（非麦当劳午餐，标记估算）→ `plan --budget-kcal 448` → `price` → `love show`
   排餐结果与 README 示例完全一致：麦乐鸡经典中套餐 395 大卡 · 蛋白质 21g · ¥25.0
4. 遇到一次 `PermissionError: profile.tmp`：查明是前一条被沙箱拒绝的调用残留进程占用文件，重跑成功，并单独验证了原子写入逻辑
5. **发现一个行为问题**：只记午餐时，剩余 780 大卡被按早餐 / 晚餐各半分配（390 / 390），因为早餐还没记
6. `python install.py --target workbuddy` → 安装到 `~/.workbuddy/skills/mcd-calorie-butler`
7. 启动 `tools/demo_server.py`，演示页 HTTP 200

## 四、真机联调（10-13 10:20）

**用户**：提供麦当劳 MCP Token（此处略）

**WorkBuddy 执行**
1. 用项目自带的 `tools/mcp_client.py` 直连 `https://mcp.mcd.cn` 验证 Token：`tools/list` 返回 **35 个工具**；读取账户积分、券包验证权限（明细略）
2. 把 mcd-mcp 写进 `~/.workbuddy/mcp.json`，与已有连接器合并，没有覆盖
3. 写探针脚本把真实数据落盘：`query-nearby-stores`（上海 · 人民广场，5 家门店，选福州路餐厅）→ `query-meals`（119 个餐品）→ `query-meal-detail`（4 个套餐）
4. 建档：目标 1800 大卡、蛋白质 90g，老样子 **麦辣鸡腿汉堡三件套**，口味去酸黄瓜
5. 记早餐（麦当劳，官方营养 387 大卡）＋ 午餐（非麦当劳，估算 1020 大卡）→ 晚餐剩 393 大卡、蛋白质差 30g
6. `plan` → 老样子 921 大卡放不下，三步替换：可乐 → 无糖可乐（代价 0）、麦辣鸡腿汉堡 → 麦香鱼（代价 1.31）、中薯条 → 小杯玉米杯（代价 1.36）→ **麦香鱼中套餐 378 大卡 · 蛋白质 18g · 估算 ¥33.0**
7. 把 `plan.calculate_price_items` 交给 `calculate-price` 官方核价 → **¥33.0，与脚本估算一致**（只核价，未下单）

## 五、在 WorkBuddy 里装上麦当劳 MCP 连接器（10-13 10:33 → 10:56）

**用户**
> 帮我安装麦当劳mcp

**用户**：发来截图，连接器列表里没有 mcd-mcp

**WorkBuddy 执行**
- 排除配置写法问题：确认 `type: "streamablehttp"` 会被归一成 http，且 HTTP 类型只看 `url`
- 查进程：WorkBuddy 主进程从 10-12 08:00 起没重启过，而 `mcp.json` 只在启动时读一次，所以新条目一直没加载
- 用已有连接器的信任记录反推出信任表的 key 格式 `sha256(origin)::serverName`，预写 mcd-mcp 的信任记录
- 找到免重启的办法：在「配置 MCP」页拨一下任意已有连接器的开关，会触发重新读盘

**用户**
> 没有 →（按建议拨开关后）出现了

**WorkBuddy 执行**：确认 `mcp-tool-list.json` 新增一条 35 个工具的缓存，信任记录被程序接受并重新落盘，连接成功。

## 六、用 Skill 正式建档（新会话，10-13 11:02）

**用户**
> @skill:"C:\\Users\\32390\\.workbuddy\\skills\\mcd-calorie-butler\\SKILL.md" 帮帮我

**WorkBuddy（加载 Skill 后）**
> 来了，我是你的热量管家。……麦当劳的，我用官方营养数据；不是麦当劳的，你说一句「中午吃了黄焖鸡」，我按份量估算记上……想吃麦当劳时，我按「味热比」在你剩下的额度里排好一顿、官方核价，等你一句「下单」我才提交。

随后按 SKILL.md 的建档流程，询问性别、年龄、身高、体重、活动量，以及口味、常去的店、老样子。

**用户**：提供身体数据（已脱敏）

**WorkBuddy 执行**
- `profile set` → 按 Mifflin-St Jeor 公式算出每日目标和蛋白质，设置安全下限（不低于基础代谢）
- `list-nutrition-foods` → `nutrition load`（158 项）
- `order-list` 为空（没有历史订单），口味改为询问用户
- 为方便落盘，写了一个直连 MCP 的小工具 `mcdcall.py`：营养表、菜单这类长返回直接写文件，不再手抄

**WorkBuddy 回复（节选）**
> 三餐我按 早 630 / 午 840 / 晚 630 分。……还差三项：口味、常去的店、老样子。

---

## WorkBuddy 发现的问题与后续修改

| WorkBuddy 的发现 | 修改 |
|---|---|
| 早餐没记录时，会一直占用剩余热量的 30%：只记午餐时晚餐只分到一半；11 点建档时仍按「早 630 / 午 840 / 晚 630」分 | `butler.py` 按当前时间判断：早餐 10:30、午餐 14:30 后还没记的一餐不再留预算，并提示"吃了请补记"。新增 `--now` 参数和 2 个测试 |
| 营养表、菜单返回动辄几万字，让模型手抄进文件既慢又容易错，所以它自己写了 `mcdcall.py` 直连落盘 | 新增 `scripts/mcd_fetch.py`：只允许只读工具，Token 从环境变量或 WorkBuddy 的 mcd-mcp 配置读取，不打印。SKILL.md 改为推荐用它取数 |
| Windows 上一次瞬时的 `PermissionError: profile.tmp`（文件被残留进程占用） | 写入时遇到文件被占用会短暂重试 |

整个过程只调用了只读工具和 `calculate-price` 核价，没有调用 `create-order`，没有产生订单。
