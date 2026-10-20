"""`scripts/*.ps1` 只许 ASCII——这条规矩的由来是 2026-10-17 实测的一个静默失效。

Windows PowerShell 5.1 读**没有 BOM** 的 .ps1 时按 ANSI 代码页（本机 cp936）解码。往
`scripts/eval-quality.ps1` 的注释和 `Write-Host` 里写中文之后：文件实际 79 行，而
`Get-Content` 只报 73 行，少的正好是那 6 行中文注释——**后面的语句被并进了上一行注释里**。
后果是 `$env:LLM_PROVIDER = "mock"` 那两行再也不执行，而脚本照样解析通过、照样往下跑，
一路跑到 provider 闸把它们拦成 exit 2。改成纯 ASCII 之后：文件 85 行 = `Get-Content` 85 行，
`provider pinned to mock` 打出来了，子进程读到 `LLM_PROVIDER=mock`。

所以这不是"注释好看一点"的问题：**在这个仓库里，往 .ps1 里写中文会让紧邻其后的代码不执行，
而不报任何错。** Python 文件不受影响（CPython 按 UTF-8 源码读），bash 脚本不受影响（按字节跑）。

两条腿：一条判规矩本身，一条判这把尺不是摆设（把一份含非 ASCII 的样张喂给同一个函数，必须被点名）。
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def _non_ascii_lines(name: str, raw: bytes) -> list[str]:
    """按 UTF-8 解一遍，逐行点出含非 ASCII 字符的行（行号 1-based）。"""
    offenders: list[str] = []
    for lineno, line in enumerate(raw.decode("utf-8", errors="replace").split("\n"), 1):
        bad = [ch for ch in line if ord(ch) > 127]
        if bad:
            offenders.append(f"{name}:{lineno} 有 {len(bad)} 个非 ASCII 字符")
    return offenders


def test_scripts_dir_has_ps1_files() -> None:
    assert sorted(SCRIPTS.glob("*.ps1")), f"{SCRIPTS} 下找不到 .ps1，这条门失去意义"


def test_ps1_scripts_are_ascii_only() -> None:
    offenders: list[str] = []
    for path in sorted(SCRIPTS.glob("*.ps1")):
        offenders.extend(_non_ascii_lines(path.name, path.read_bytes()))
    assert not offenders, (
        "PowerShell 脚本里出现了非 ASCII 字符。Windows PowerShell 5.1 按 ANSI 代码页读无 BOM 的 "
        ".ps1，中文行尾会把紧随其后的代码并进上一行注释里（实测：79 行的文件 Get-Content 只报 73 行，"
        "被并进注释的赋值语句静默失效）。请把注释和字符串改成 ASCII 英文，或另存为带 BOM 的 UTF-8。"
        f" 违规：{offenders}"
    )


def test_ascii_scanner_is_not_vacuous() -> None:
    """反向证据：同一个函数必须点出人造的脏样张，否则上面那条门是空转。"""
    dirty = ("# comment " + "中" + "\n$env:X = 1\n").encode("utf-8")
    assert _non_ascii_lines("sample.ps1", dirty) == ["sample.ps1:1 有 1 个非 ASCII 字符"]
    assert _non_ascii_lines("clean.ps1", b"# comment\n$env:X = 1\n") == []


def test_eval_quality_prefers_repo_venv_when_present() -> None:
    source = (SCRIPTS / "eval-quality.ps1").read_text(encoding="ascii")

    assert '$venvPython = Join-Path $backendRoot ".venv\\Scripts\\python.exe"' in source
    assert "& $python scripts\\eval_rag.py" in source
    assert "& $python scripts\\eval_agent.py" in source
