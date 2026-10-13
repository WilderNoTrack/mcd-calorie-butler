"""把 Skill 复制到 AI 客户端的技能目录。

python install.py --target workbuddy   → ~/.workbuddy/skills/mcd-calorie-butler
python install.py --target claude      → ~/.claude/skills/mcd-calorie-butler
python install.py --target D:/somewhere
"""
import argparse
import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parent / "skill" / "mcd-calorie-butler"
TARGETS = {"workbuddy": Path.home() / ".workbuddy" / "skills", "claude": Path.home() / ".claude" / "skills"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="workbuddy / claude / 任意目录")
    a = ap.parse_args()
    dest = TARGETS.get(a.target, Path(a.target).expanduser()) / SRC.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"已安装到 {dest}")
    print("还需要在客户端里连上麦当劳 MCP，参考 mcp-config.example.json。")


if __name__ == "__main__":
    main()
