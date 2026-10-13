# 麦麦热量管家 · 味热比

**减脂不是少吃你爱的，是先换掉不值这口热量的。**

一个装进 AI 里的麦当劳 Skill。你告诉它今天吃了什么，麦当劳的按官方营养数据记，别的饭说一句就行；它算出这一顿还能吃多少，按你的口味和「味热比」排好一顿麦当劳，用官方接口核完价，等你说一句「下单」。

**[打开在线演示](https://wildernotrack.github.io/mcd-calorie-butler/)**：不用 Token，直接看它怎么调用麦当劳 MCP、怎么按味热比排一顿。

> 非麦当劳官方产品，由参赛者独立开发。内容仅供参考，不构成营养或医疗建议。

## 它干了什么

```
你：中午吃了食堂黄焖鸡米饭，还喝了杯半糖奶茶。晚上想吃麦当劳，帮我安排一下

管家：（调用麦当劳 MCP：now-time-info → list-nutrition-foods → query-nearby-stores
       → query-meals → query-meal-detail → calculate-price）

今天目标 1800 大卡：早餐 402（麦当劳，已记录），午餐约 950（估算），晚餐还剩 448 大卡。
你的老样子巨无霸三件套（949 大卡）放不下，我按味热比代价从小到大换：
· 可乐 → 纯牛奶：少 18 大卡，多 7g 蛋白质
· 巨无霸 → 麦乐鸡 5 块：少 300 大卡，代价 0.17
· 中薯条 → 小杯玉米杯：少 236 大卡，代价 1.36

麦乐鸡经典中套餐（小杯玉米杯 + 纯牛奶）
395 大卡 · 蛋白质 21g · ¥25.0（官方核价）· 福州路餐厅 19:00 到店取
也可以：板烧鸡腿堡三件套（玉米杯 + 无糖可乐，去冰 · 你说过一次）444 大卡 · ¥34.0

回复「下单」我就提交，付款在麦当劳官方页面完成。
```

上面每个数字都来自真实调用：热量来自 `list-nutrition-foods`，价格 ¥25.0 是 `calculate-price` 返回的 `"price":2500`（单位是分）。

## 和常见做法有什么不同

| | 常见的减脂点餐工具 | 麦麦热量管家 |
|---|---|---|
| 一天三顿 | 默认三顿都吃麦当劳 | 麦当劳只是其中一顿，别的饭说一句、AI 估算（标注"估算"） |
| 热量超了 | 推荐热量最低的 | 按**味热比**换：先换不值这口热量的，最爱的最后才动 |
| 口味 | 每次重新说 | **说一次就记住**：去酸黄瓜、可乐去冰，自动写进官方特调参数 |
| 老样子 | 不管 | 放得下就原样保留，放不下才改，每处改动都讲清楚为什么 |
| 数字 | 模型估或算 | 计算脚本算，`calculate-price` 核价；实测估算与官方核价一致 |
| 吃超了 | 建议下一顿少吃 | 不惩罚、不劝饿，给出最轻的选项和"明天再调整" |

## 味热比

**味热比 = 爱吃程度 ÷ 每百大卡热量。**

热量超了要换东西时，比的是**换掉它的代价**：少掉的爱吃程度 ÷ 少掉的热量。代价小的先换。所以可乐换无糖可乐（代价 0）最先，薯条换玉米杯（代价 1.36）最后——薯条是大众最爱，换掉最心疼。

爱吃程度先用大众口味作默认值（来源：[麦购网「麦当劳十大最受欢迎产品」综合指数](https://www.maigoo.com/top/424487.html)，汇总了大众点评、美团、饿了么的评价与热销情况），榜单外的餐品给中间值 6.0；用户可以随时改，常点的会自动加分。

按大众口味算，**圆筒冰淇淋是麦当劳最值这口热量的（8.9），麦辣鸡腿汉堡和巨无霸最不值（约 1.7）**。

详见 [味热比](skill/mcd-calorie-butler/references/weirebi.md)。

## 怎么用

### 1. 申请麦当劳 MCP Token

在 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 登录后申请。把 Token 放进环境变量，**不要**写进任何文件或发给别人：

```bash
export MCD_MCP_TOKEN="你的 Token"          # PowerShell：$env:MCD_MCP_TOKEN="你的 Token"
```

### 2. 在 AI 客户端里连上麦当劳 MCP

参考 [mcp-config.example.json](mcp-config.example.json)。WorkBuddy：左侧【专家·技能·连接器】→【连接器】→【自定义连接器】→【配置MCP】，填入配置并把 `${MCD_MCP_TOKEN}` 换成你的 Token。Claude Code、Cursor、Cherry Studio 同理。

### 3. 安装 Skill

```bash
python install.py --target workbuddy     # 复制到 ~/.workbuddy/skills/mcd-calorie-butler
python install.py --target claude        # 复制到 ~/.claude/skills/mcd-calorie-butler
```

也可以在 WorkBuddy 的技能页上传 `skill/mcd-calorie-butler` 文件夹。需要 Python 3.9+，无第三方依赖。

### 4. 开始

对 AI 说"我在减脂，帮我建个档"，它会问目标、口味、常去的店和老样子。之后每天说"中午吃了……""晚上吃什么麦当劳"就行。

## 不用 Token 先看看

```bash
python -m unittest discover -s tests -v   # 12 个离线测试，用录制的真实 MCP 返回
python tools/demo_server.py               # 打开 http://127.0.0.1:8765 看交互演示
```

演示页的排餐算法与 Skill 的计算脚本是同一套，数据是录制的真实菜单与营养表。本机配置了 `DEEPSEEK_API_KEY` 时，演示页的午饭可以随便输入，由大模型估算；Key 只在本地服务端读取。

也可以直接跑计算脚本：

```bash
cd skill/mcd-calorie-butler
python scripts/butler.py nutrition load ../../tests/fixtures/nutrition.txt
python scripts/butler.py profile set --goal-kcal 1800 --protein 90
python scripts/butler.py base set --code 9900005466 --name 巨无霸三件套
python scripts/butler.py taste add 去酸黄瓜
python scripts/butler.py plan --meal dinner --budget-kcal 448 --meals ../../tests/fixtures/meals.txt --details ../../tests/fixtures/detail_*.txt
python scripts/butler.py love show --known-only --top 10
```

## 它怎么工作

```
你 ──说话──▶ AI（WorkBuddy / Claude / Cursor）
              ├─ 读 Skill：流程、规则、方案卡格式（SKILL.md + references/）
              ├─ 调麦当劳 MCP：营养表、门店、菜单、套餐换配、计价、下单
              └─ 跑计算脚本：记账、剩余热量、味热比、排餐、口味特调、分↔元
```

- **麦当劳 MCP** 只负责取数和下单，详见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。
- **计算脚本** `scripts/butler.py` 负责所有数字，模型不心算。
- **AI** 负责听懂你、估算非麦当劳食物、把结果讲清楚。

## 适合谁

- 在减脂、控卡或增肌，但不想和麦当劳绝交的人
- 想吃得心里有数、又懒得每顿查热量表的上班族和学生
- 想和对象/朋友一起点，但各自目标不同的人（[一起吃](skill/mcd-calorie-butler/references/together.md)）

## 健康与隐私

- 每日目标不低于基础代谢（女性不低于 1200、男性不低于 1500 大卡），设得更低会被提到下限。
- 吃超了照实记，不劝饿、不评价身材；提到疾病、孕期等情况会建议咨询医生或营养师。详见 [健康边界](skill/mcd-calorie-butler/references/health.md)。
- 饮食日记、口味、爱吃程度只存在本机 `~/.mcd-calorie-butler/`。仓库里没有任何 Token 或个人信息。
- 只有你明确说"下单"才会调用 `create-order`；不会自动领券、抽奖、兑换或取消订单。

## 目录

```
skill/mcd-calorie-butler/      Skill 本体（装进 AI 客户端的就是这个文件夹）
  SKILL.md                     主流程
  references/                  味热比、MCP 调用手册、估算规范、健康边界、一起吃
  scripts/butler.py            计算脚本（纯标准库）
  data/public_love.json        大众口味默认值及来源
tests/                         离线测试 + 录制的真实 MCP 返回（tests/fixtures）
tools/                         录制数据、导出演示数据、本地演示服务
docs/                          交互演示页
```

## 许可

MIT。参赛声明见 [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md)。
