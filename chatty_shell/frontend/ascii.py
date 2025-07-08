import shutil
import textwrap
import re
from typing import List, Tuple


def get_width() -> int:
    return shutil.get_terminal_size().columns


def wrap_preserve_newlines(text: str, width: int) -> List[str]:
    """
    Split text on '\n', wrap each paragraph at `width`, and preserve blank lines.
    Returns a flat list of lines.
    """
    lines: List[str] = []
    for para in text.split("\n"):
        if para:
            wrapped = textwrap.wrap(para, width=width) or [""]
            lines.extend(wrapped)
        else:
            lines.append("")
    return lines


def wrap_message(message: str, panel_w: int, type: str) -> List[Tuple[str, bool]]:
    """
    Returns a list of (ascii_line, is_code) for the chat bubble.
    - Preserves your old ╭─…│…│╰─…╯ framing with 🤓 / 🤖
    - If there's a ```lang\n…``` block, strips the backticks,
      inserts a “[lang]” line immediately above the code,
      and flags only the code lines (not the lang header) as is_code=True.
    """

    # 1) compute wrapping widths
    max_total = int(panel_w * 3 / 4)
    max_inner = max_total - 4

    # 2) detect a single code‐fence
    fence_re = re.compile(r"```(\w+)?\n([\s\S]*?)```")
    m = fence_re.search(message)

    parts: List[Tuple[str, bool]] = []

    if m:
        lang = m.group(1)  # e.g. "python" or None
        code_body = m.group(2)
        before = message[: m.start()]
        after = message[m.end() :]

        # text before
        parts += [(ln, False) for ln in wrap_preserve_newlines(before, max_inner)]
        # lang header
        if lang:
            parts.append((f"[{lang}]", False))
        # code lines (raw, unwrapped)
        for code_line in code_body.splitlines():
            parts.append((code_line, True))
        # text after
        parts += [(ln, False) for ln in wrap_preserve_newlines(after, max_inner)]
    else:
        # no fence: treat entire message as plain text
        parts += [(ln, False) for ln in wrap_preserve_newlines(message, max_inner)]

    # 3) wrap non‐code segments to max_inner
    wrapped: List[Tuple[str, bool]] = []
    for seg, is_code in parts:
        if is_code:
            # leave code lines as‐is
            wrapped.append((seg, True))
        else:
            for ln in textwrap.wrap(seg, width=max_inner) or [""]:
                wrapped.append((ln, False))

    # 4) measure the widest line
    actual_inner = max((len(ln) for ln, _ in wrapped), default=0)

    # 5) build the bubble
    bubble: List[Tuple[str, bool]] = []

    # top border
    if type == "human":
        bubble.append(("╭" + "─" * (actual_inner + 2) + "╮", False))
        # bubble.append(("╭" + "─" * (actual_inner + 1) + "🤓", False))
    elif type == "ai":
        bubble.append(("🤖" + "─" * (actual_inner + 1) + "╮", False))
    else:
        raise ValueError("Type must be 'human' or 'ai'")

    # interior lines
    for ln, is_code in wrapped:
        bubble.append(("│ " + ln.ljust(actual_inner) + " │", is_code))

    # bottom border
    bubble.append(("╰" + "─" * (actual_inner + 2) + "╯", False))

    return bubble


ASCII_ART_SPLASH_SCREEN = r"""

 ░▒▓██████▓▒░░▒▓█▓▒░░▒▓█▓▒░░▒▓██████▓▒░▒▓████████▓▒░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░       ░▒▓███████▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░▒▓█▓▒░      ░▒▓█▓▒░        
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ ░▒▓█▓▒░      ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░        
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ ░▒▓█▓▒░      ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░        
░▒▓█▓▒░      ░▒▓████████▓▒░▒▓████████▓▒░ ░▒▓█▓▒░      ░▒▓█▓▒░    ░▒▓██████▓▒░        ░▒▓██████▓▒░░▒▓████████▓▒░▒▓██████▓▒░ ░▒▓█▓▒░      ░▒▓█▓▒░        
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ ░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░                 ░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░        
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ ░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░                 ░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░        
 ░▒▓██████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ ░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░          ░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░▒▓████████▓▒░▒▓████████▓▒░ 
                                                                                                                                                       
                                                                                                                                                       

"""
