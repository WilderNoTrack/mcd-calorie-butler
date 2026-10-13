# 一起吃（DLC）

两个人（或几个人）一起点，各有各的口味和目标，还是一张单、一次下单。

## 每个人一份档案

用环境变量 `MCD_BUTLER_HOME` 区分。自己用默认目录，其他人放到 `people/` 下：

```
MCD_BUTLER_HOME=~/.mcd-calorie-butler/people/对象 python scripts/butler.py profile set --goal-kcal 2200 --mode keep
MCD_BUTLER_HOME=~/.mcd-calorie-butler/people/对象 python scripts/butler.py taste add 不要生菜
MCD_BUTLER_HOME=~/.mcd-calorie-butler/people/对象 python scripts/butler.py nutrition load nutrition.txt
```

对方的档案只问必要的：这顿想控制热量吗，有什么不吃的、固定口味。不控制热量的人，`--budget-kcal` 传一个宽松的数（比如 1200），只按口味排。

## 流程

1. 同一家门店、同一个时间，只查一次 `query-meals` 和候选套餐的 `query-meal-detail`，两个人共用这些文件。
2. 分别运行 `plan`（各用各的 `MCD_BUTLER_HOME`）。
3. 把两份 `plan.calculate_price_items` 合并成一个数组，一次 `calculate-price` 核价。
4. 方案卡分人写：每人吃什么、多少大卡、各自的口味特调；最后写合计价格。用户要分账时，按各自套餐的估算价比例分摊核价总额，精确到分。
5. 用户确认后一次 `create-order`。之后只把自己那份记进自己的日记；对方愿意的话，也记进对方的档案。

## 方案卡示例

```
你 · 减脂中，今晚剩 448 大卡
  板烧鸡腿堡三件套（小杯玉米杯 + 无糖可乐，去冰 · 你说过一次）444 大卡
对象 · 不控制，最爱麦辣
  麦辣鸡腿汉堡三件套（不要生菜 · TA 说过一次）

合计 ¥xx.x（官方核价）· 福州路餐厅 19:00 到店取
回复「下单」我就一起提交。
```
