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

    print(" " * indent + "╭" + "─" * (actual_inner + 2) + "╮")
    for line in lines:
        print(" " * indent + "│ " + line.ljust(actual_inner) + " │")
    print(" " * indent + "╰" + "─" * (actual_inner + 2) + "╯")


def print_ai_bubble(text: str):
    term_w = get_width()
    max_total = int(term_w * 3 / 4)
    max_inner = max_total - 4

    lines = wrap_preserve_newlines(text, max_inner)
    actual_inner = max(len(line) for line in lines)

    print("╭" + "─" * (actual_inner + 2) + "╮")
    for line in lines:
        print("│ " + line.ljust(actual_inner) + " │")
    print("╰" + "─" * (actual_inner + 2) + "╯")


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
