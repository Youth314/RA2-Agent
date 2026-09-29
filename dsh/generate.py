"""由 DSH 的 `cordis` preset 生成 `cordis.patch.yml`。

preset 的 `plugins` 是一份完整清单，不能引用别的 preset，故 `ra2` 必须把 `cordis`
整份抄下来。抄写交给本脚本，免得 DSH 升级后漂移得不知不觉。

用法：`python3 dsh/generate.py`（在仓库根运行或任意位置均可）。
"""
import pathlib
import sys

#: DSH 里被抄的那份 preset。
SOURCE = pathlib.Path(
    '/home/youthz/deepseek-harness/packages/bundle/web-app/presets/cordis.patch.yml')
#: 生成物，与本脚本同目录。
TARGET = pathlib.Path(__file__).resolve().parent / 'cordis.patch.yml'

HEADER = """\
# Agent preset ra2: the shipped `cordis` preset plus the ra2 game tools, so one
# agent keeps its coding ability and can play. Generated from
# deepseek-harness packages/bundle/web-app/presets/cordis.patch.yml.
# The tactic skill needs no wiring: skill-filesystem discovers
# <project root>/.agents/skills, so it appears when the session cwd is in ra2-agent.
"""

DECLARATION = """\
        id: ra2
        name: RA2 对局
        description: 编码能力加红警 2 对局四工具（status / tactics / call / cancel）。
        order: 5
"""

#: 挂载红警四工具的那一条，插在 `skill-filesystem` 之前。
MCP_ROW = """\
          - id: mcp-ra2
            name: '@deepseek-ai/dsh-mcp-client'
            config:
              serverName: ra2
              transport: stdio
              command: python3
              args: ['-m', 'ra2agent.mcp']
              cwd: /home/youthz/ra2-agent
              env: {PYTHONPATH: /home/youthz/ra2-agent/src}
              failOnStartupError: true
"""


def replace(text, old, new):
    """按锚点替换，出现次数不是 1 就报错——上游改了结构要人来处理。"""
    found = text.count(old)
    if found != 1:
        raise SystemExit(f'锚点出现 {found} 次，期望 1 次：{old.splitlines()[0]!r}')
    return text.replace(old, new)


def generate():
    """读出上游 preset，改成本项目的 `ra2`，返回文本。"""
    text = SOURCE.read_text(encoding='utf-8')
    upstream_header = (
        '# Agent preset cordis: one `@deepseek-ai/dsh-agent-preset` declaration inserted\n'
        "# after the web patch. Edits saved from the Web editor override this row's\n"
        '# `config.plugins` by id from the profile patch.\n')
    text = replace(text, upstream_header, HEADER)
    text = replace(text, '    - id: preset-cordis\n', '    - id: preset-ra2\n')
    text = replace(text, '        id: cordis\n        order: 4\n', DECLARATION)
    text = replace(text, '          - id: skill-filesystem\n',
                   MCP_ROW + '          - id: skill-filesystem\n')
    return text


def main(argv):
    """写生成物；`--check` 只比对，不写。"""
    text = generate()
    if '--check' in argv:
        current = TARGET.read_text(encoding='utf-8') if TARGET.exists() else None
        if current != text:
            print(f'{TARGET} 与上游不同步，跑 python3 dsh/generate.py 重新生成')
            return 1
        print(f'{TARGET} 与上游同步')
        return 0
    TARGET.write_text(text, encoding='utf-8')
    print(f'写入 {TARGET}（{len(text.splitlines())} 行）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
