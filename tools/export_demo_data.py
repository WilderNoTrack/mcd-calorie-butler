"""把录制的真实 MCP 数据导出成演示页用的 docs/demo-data.json。

演示页的排餐算法与 scripts/butler.py 相同（同一套打分），数据也来自同一批录制文件，
这样网页上点出来的结果和真实引擎一致。

用法：python tools/export_demo_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "skill" / "mcd-calorie-butler" / "scripts"))
import butler  # noqa: E402

BASE = "9900005466"   # 演示里的老样子：巨无霸三件套
RATIO_ROWS = ["圆筒冰淇淋", "麦乐鸡5块", "麦辣鸡翅-2块", "奥利奥麦旋风", "中薯条", "巨无霸", "麦辣鸡腿汉堡",
              "板烧鸡腿堡", "麦香鱼", "小杯玉米杯", "可乐中杯", "纯牛奶（盒装）"]


def main() -> None:
    nut = butler.Nutrition(butler.parse_nutrition((FIX / "nutrition.txt").read_text(encoding="utf-8")))
    loves = butler.Loves({"loves": {}, "learned": {}})
    meals = butler.load_meals(str(FIX / "meals.txt"))
    details = butler.load_details(sorted(str(p) for p in FIX.glob("detail_*.txt")))
    combos = []
    for code, d in details.items():
        c = butler.Combo(d, meals[code]["price"], nut, loves)
        combos.append({"code": c.code, "name": c.name, "price": c.price, "rounds": [
            {"id": r["id"], "name": r["name"], "options": [
                {"code": o["code"], "name": o["name"], "key": o["nutrition_name"], "kcal": o["kcal"],
                 "protein": o["protein"], "diff": o["diff"], "default": o["default"]}
                for o in r["options"]]} for r in c.rounds]})
    combo_codes = set(details)
    singles = []
    for code, m in meals.items():
        key, n = nut.get(m["name"])
        if code in combo_codes or not n or n["kcal"] <= 0:
            continue
        singles.append({"code": code, "name": m["name"], "key": key, "kcal": n["kcal"], "protein": n["protein"], "price": m["price"]})
    names = set(RATIO_ROWS)
    for c in combos:
        for r in c["rounds"]:
            names.update(o["key"] for o in r["options"] if o["key"])
    names.update(s["key"] for s in singles)
    love_table = {}
    for k in sorted(names):
        love, src = loves.of(k)
        love_table[k] = {"love": love, "src": "大众口味" if src == "大众口味" else "暂无数据",
                         "kcal": nut.table[k]["kcal"], "protein": nut.table[k]["protein"]}
    meta = json.loads((FIX / "meta.json").read_text(encoding="utf-8"))
    out = {"store": meta["store"], "reservationDate": meta["reservationDate"], "base": BASE, "combos": combos,
           "singles": singles, "loves": love_table, "ratioRows": RATIO_ROWS}
    dest = ROOT / "docs" / "demo-data.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"已导出 {dest}：{len(combos)} 个套餐，{len(singles)} 个单点，{len(love_table)} 个餐品的爱吃程度")


if __name__ == "__main__":
    main()
