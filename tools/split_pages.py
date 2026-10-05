# -*- coding: utf-8 -*-
"""把 app.py / admin.py 从「单文件 + if/elif 分页」拆成「页面渲染函数 + main()」,
供统一入口 frontend/main.py 复用(一个应用、一套导航、按角色显示页面)。

- 页面正文原样保留(缩进已是 4 空格), 只是把 `if page == "X":` 换成 `def render_x():`
- st.set_page_config / apply_theme / login_gate 三个模块级副作用移进 main(),
  这样被 import 时不会重复执行(Streamlit 的 set_page_config 只能调一次)
- AUTH_USER 改成模块级占位, main() 里用 global 写入; 统一入口会直接把登录用户赋给它

用法: python tools/split_pages.py [--dry]
幂等: 文件里已有 `def render_` 就跳过。
"""
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRY = "--dry" in sys.argv

SLUG = {
    "首页概览": "home", "联赛数据": "leagues", "球队分析": "teams", "球员分析": "players",
    "比赛详情": "match", "比赛预测": "predict", "AI智能分析": "agent", "实时比分": "live",
    "数据概览": "overview", "数据浏览": "browse", "API接口测试": "api",
    "数据库管理": "database", "数据更新控制": "update", "模型管理": "models",
}


def split(path: Path) -> None:
    text = io.open(path, encoding="utf-8").read()
    if "def render_" in text:
        print("  跳过(已拆分):", path.name)
        return
    src = text.splitlines()

    def first(pred, what):
        for i, ln in enumerate(src):
            if pred(ln):
                return i
        raise SystemExit(f"[{path.name}] 找不到锚点: {what}")

    i_cfg = first(lambda l: l.startswith("st.set_page_config("), "set_page_config")
    depth, j = 0, i_cfg
    while True:                                    # 括号配平找调用结束行
        depth += src[j].count("(") - src[j].count(")")
        if depth <= 0:
            break
        j += 1
    i_apply = first(lambda l: l == "apply_theme()", "apply_theme()")
    i_gate = first(lambda l: l.startswith("AUTH_USER = login_gate("), "AUTH_USER = login_gate")
    gate_args = src[i_gate].split("login_gate(", 1)[1].rsplit(")", 1)[0].strip()
    if gate_args == "admin_only=True":             # 统一入口不再按端分app; 角色在导航层过滤
        gate_args = ""
    i_side = first(lambda l: l.startswith("with st.sidebar:"), "with st.sidebar:")
    i_chain = first(lambda l: re.match(r'^if page == "', l), 'if page == "')

    removed = set(range(i_cfg, j + 1)) | {i_apply, i_gate}
    # 注意: 侧栏整段(with st.sidebar: ...)也要从模块级摘掉 —— 它会被缩进搬进 main(),
    # 否则同一段会既在模块级执行(未登录时 AUTH_USER 还不存在 -> NameError)、又在 main() 里执行。
    head = [l for k, l in enumerate(src[:i_side]) if k not in removed]
    head += ["", "# 登录后由 main() 写入(统一入口会直接把已登录用户赋给它)",
             'AUTH_USER = {}']

    # ---- 拆链条 ----
    # 页面之间用顶格注释横幅分隔(如 "# ====\n# 联赛数据\n# ===="), 它们归属下一个页面;
    # 顶格的**代码**行才意味着链条结束(admin.py 末尾的公共页脚)。
    blocks, tail, in_tail = [], [], False
    name, body, banner, pending = None, None, [], []
    for ln in src[i_chain:]:
        if in_tail:
            tail.append(ln)
            continue
        m = re.match(r'^(?:if|elif) page == "([^"]+)":\s*$', ln)
        if m:
            if name:
                blocks.append((name, body, banner))
            name, body, banner = m.group(1), [], pending
            pending = []
            continue
        if ln and not ln.startswith(" "):
            if ln.lstrip().startswith("#"):          # 横幅注释 -> 归属下一个页面
                pending.append(ln)
                continue
            if name:                                 # 顶格代码 -> 公共尾部开始
                blocks.append((name, body, banner))
                name, body = None, None
            in_tail = True
            tail.extend(pending)
            pending = []
            tail.append(ln)
            continue
        if name is not None:
            body.append(ln)
    if name:
        blocks.append((name, body, banner))
    if not blocks:
        raise SystemExit(f"[{path.name}] 没拆出任何页面")

    out = head + ["", "", "# ============ 页面渲染函数(统一入口 frontend/main.py 调用) ============"]
    for nm, bd, ban in blocks:
        slug = SLUG.get(nm) or re.sub(r"\W+", "_", nm)
        while bd and not bd[-1].strip():
            bd.pop()
        out += [""]
        out += list(ban)
        banner = list(ban)
        out += ["", f"def render_{slug}():", f'    """{nm}"""'] + bd

    out += ["", "", "def main():", "    # 单独运行本文件(streamlit run frontend/xxx.py)时的完整流程"]
    out += ["    " + l if l.strip() else "" for l in src[i_cfg:j + 1]]
    out.append("    apply_theme()")
    out.append("    global AUTH_USER")
    out.append(f"    AUTH_USER = login_gate({gate_args})")
    out += ["    " + l if l.strip() else "" for l in src[i_side:i_chain]]
    for idx, (nm, _bd, _ban) in enumerate(blocks):
        slug = SLUG.get(nm) or re.sub(r"\W+", "_", nm)
        out.append(f'    {"if" if idx == 0 else "elif"} page == "{nm}":')
        out.append(f"        render_{slug}()")
    out += ["    else:",
            '        st.warning("未知页面: " + str(page))']
    if tail:
        out += ["    " + l if l.strip() else "" for l in tail]
    out += ["", "", 'if __name__ == "__main__":', "    main()", ""]

    new = "\n".join(out) + "\n"
    print(f"  {path.name}: {len(src)} 行 -> {len(out)} 行, 页面 {len(blocks)} 个 "
          f"({', '.join(SLUG.get(n, n) for n, _b, _ban in blocks)})")
    if not DRY:
        bak = ROOT / "logs" / "backup_split"
        bak.mkdir(parents=True, exist_ok=True)
        io.open(bak / path.name, "w", encoding="utf-8").write(text)
        io.open(path, "w", encoding="utf-8").write(new)
        print("     备份:", (bak / path.name).relative_to(ROOT))


if __name__ == "__main__":
    for f in ("frontend/app.py", "frontend/admin.py"):
        print("==>", f)
        split(ROOT / f)
