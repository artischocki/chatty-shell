import shutil
import textwrap
import sys


def get_width():
    return shutil.get_terminal_size().columns


def wrap_preserve_newlines(text: str, width: int):
    """
    Split text on '\n', wrap each paragraph at `width`, and preserve blank lines.
    Returns a flat list of lines.
    """
    lines = []
    for para in text.split("\n"):
        if para:
            wrapped = textwrap.wrap(para, width=width) or [""]
            lines.extend(wrapped)
        else:
            # explicit blank line
            lines.append("")
    return lines


def print_user_bubble(text: str):
    term_w = get_width()
    max_total = int(term_w * 3 / 4)
    max_inner = max_total - 4

    # preserve newlines, then wrap
    lines = wrap_preserve_newlines(text, max_inner)
    actual_inner = max(len(line) for line in lines)
    bubble_w = actual_inner + 4
    indent = term_w - bubble_w

    print(" " * indent + "╭" + "─" * (actual_inner) + "🤓" + "╮")
    for line in lines:
        print(" " * indent + "│ " + line.ljust(actual_inner) + " │")
    print(" " * indent + "╰" + "─" * (actual_inner + 2) + "╯")


def print_ai_bubble(text: str):
    term_w = get_width()
    max_total = int(term_w * 3 / 4)
    max_inner = max_total - 4

    lines = wrap_preserve_newlines(text, max_inner)
    actual_inner = max(len(line) for line in lines)

    print("╭" + "🤖" + "─" * (actual_inner) + "╮")
    for line in lines:
        print("│ " + line.ljust(actual_inner) + " │")
    print("╰" + "─" * (actual_inner + 2) + "╯")


def print_tool_bubble(command: str, response: str):
    term_w = get_width()
    max_total = int(term_w * 3 / 4)
    max_inner = max_total - 4  # account for borders/padding

    # prepare lines
    cmd_lines = wrap_preserve_newlines(command, max_inner)
    resp_lines = wrap_preserve_newlines(response, max_inner)

    # find longest line among both
    actual_inner = max(
        max((len(l) for l in cmd_lines), default=0),
        max((len(l) for l in resp_lines), default=0),
    )

    # bubble width and indent (left-aligned here)
    bubble_w = actual_inner + 4
    indent = 0

    # top border
    print(" " * indent + "╭" + "🛠️" + "─" * (actual_inner) + "╮")

    # command section
    for line in cmd_lines:
        print(" " * indent + "│ " + line.ljust(actual_inner) + " │")

    # separator
    print(" " * indent + "├" + "─" * (actual_inner + 2) + "┤")

    # response section
    for line in resp_lines:
        print(" " * indent + "│ " + line.ljust(actual_inner) + " │")

    # bottom border
    print(" " * indent + "╰" + "─" * (actual_inner + 2) + "╯")


def print_banner():
    width = get_width()
    line = "━" * width
    print(line)
    print("🧠 OpenAI Chat Agent — type 'exit' to quit".center(width))


def clear_last_line():
    # Move cursor up and clear the line (ANSI escape sequences)
    sys.stdout.write("\033[F")  # Move cursor up one line
    sys.stdout.write("\033[K")  # Clear line
    sys.stdout.flush()
