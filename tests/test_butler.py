"""离线回归测试：用 tests/fixtures 里录制的真实麦当劳 MCP 返回，不需要 Token、不联网。

运行：python -m unittest discover -s tests -v
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "skill" / "mcd-calorie-butler" / "scripts"))
import butler  # noqa: E402

DETAILS = sorted(str(p) for p in FIX.glob("detail_*.txt"))


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = butler.main(list(argv))
    return code, json.loads(buf.getvalue())


class ButlerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["MCD_BUTLER_HOME"] = self.tmp.name
        code, _ = run("nutrition", "load", str(FIX / "nutrition.txt"))
        self.assertEqual(code, 0)
        run("profile", "set", "--goal-kcal", "1800", "--protein", "90")
        run("base", "set", "--code", "9900005466", "--name", "巨无霸三件套")

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, budget):
        code, out = run("plan", "--meal", "dinner", "--meals", str(FIX / "meals.txt"), "--details", *DETAILS,
                        "--budget-kcal", str(budget))
        self.assertEqual(code, 0, out)
        return out

    def test_nutrition_table_is_official(self):
        nut, _ = butler.load_nutrition()
        self.assertEqual(nut.get("巨无霸")[1]["kcal"], 513)
        self.assertEqual(nut.get("纯牛奶")[0], "纯牛奶（盒装）")          # 别名
        self.assertEqual(nut.get("纯牛奶(盒装)")[0], "纯牛奶（盒装）")     # 半角括号
        self.assertIsNone(nut.get("煎饼果子")[0])                        # 查不到就是查不到

    def test_mcd_meal_logged_from_official_data(self):
        code, out = run("log", "add", "--meal", "breakfast", "--source", "mcd", "--items", '["猪柳蛋麦满分","小杯鲜萃咖啡"]')
        self.assertEqual(code, 0)
        self.assertEqual(out["summary"]["eaten_kcal"], 387 + 15)

    def test_unknown_mcd_item_is_rejected_not_guessed(self):
        code, out = run("log", "add", "--meal", "lunch", "--source", "mcd", "--items", '["煎饼果子"]')
        self.assertEqual(code, 2)
        self.assertIn("查不到", out["error"])

    def test_budget_splits_across_open_meals(self):
        run("log", "add", "--meal", "breakfast", "--source", "other", "--items", '[{"name":"包子","kcal":400,"protein":12}]')
        _, out = run("today")
        self.assertEqual(out["remaining_kcal"], 1400)
        self.assertEqual(out["meal_budgets"], {"lunch": 800, "dinner": 600})

    def test_usual_order_kept_when_it_fits(self):
        out = self.plan(1100)
        self.assertEqual(out["plan"]["combo_name"], "巨无霸三件套")
        self.assertEqual(out["steps"], [])

    def test_tight_budget_explained_cheapest_cost_first(self):
        out = self.plan(488)
        self.assertLessEqual(out["plan"]["kcal"], 488)
        costs = [s["cost"] for s in out["steps"] if s["cost"] is not None]
        self.assertEqual(costs, sorted(costs))
        self.assertTrue(out["options"])

    def test_engine_price_matches_official_quote(self):
        # 板烧鸡腿堡三件套 + 小杯玉米杯 + 无糖可乐：calculate-price 实测 3400 分
        _, quote = run("price", str(FIX / "price_bs_corn_zero.txt"))
        self.assertEqual(quote["price_yuan"], 34.0)
        meals = butler.load_meals(str(FIX / "meals.txt"))
        details = butler.load_details([str(FIX / "detail_9900005462.txt")])
        nut, _ = butler.load_nutrition()
        combo = butler.Combo(details["9900005462"], meals["9900005462"]["price"], nut, butler.Loves(butler.load_profile()))
        pick = []
        for r in combo.rounds:
            want = {"板烧鸡腿堡", "小杯玉米杯", "无糖可口可乐中杯"}
            pick.append(next(j for j, o in enumerate(r["options"]) if o["name"] in want))
        self.assertEqual(combo.summarize(tuple(pick))["price"], quote["price_yuan"])

    def test_tastes_become_official_modifications(self):
        run("taste", "add", "去酸黄瓜")
        run("taste", "add", "可乐去冰")
        out = self.plan(1100)
        rounds = out["plan"]["calculate_price_items"][0]["roundList"]
        burger = rounds[0]["comboItemList"][0]["modification"]["values"]
        pickle = next(v for v in burger if v["code"] == "100202")      # 酸黄瓜
        self.assertEqual((pickle["key"], pickle["quantity"]), ("0-0", 0))
        self.assertEqual(len(burger), 5)                                 # 同组其他配料也要一并传
        drink = rounds[2]["comboItemList"][0]["modification"]["values"]
        self.assertEqual(drink, [{"code": "200002", "key": "0-0", "quantity": 1}])

    def test_tiny_budget_suggests_singles_and_no_starving(self):
        out = self.plan(150)
        self.assertNotIn("plan", out)
        self.assertTrue(all(s["kcal"] <= 150 for s in out["singles"]))
        self.assertTrue(any("不建议靠饿" in n for n in out["notes"]))

    def test_goal_below_floor_is_raised(self):
        _, out = run("profile", "set", "--goal-kcal", "800")
        self.assertEqual(out["profile"]["goal_kcal"], out["profile"]["floor_kcal"])

    def test_user_love_overrides_public_default(self):
        run("love", "set", "板烧鸡腿堡", "10")
        _, out = run("love", "show", "--known-only")
        row = next(r for r in out["items"] if r["name"] == "板烧鸡腿堡")
        self.assertEqual((row["love"], row["source"]), (10.0, "你设置的"))

    def test_disliked_item_never_planned(self):
        run("love", "set", "麦乐鸡5块", "0")
        out = self.plan(488)
        names = [i["name"] for i in out["plan"]["items"]]
        self.assertNotIn("麦乐鸡5块", names)


if __name__ == "__main__":
    unittest.main()
