# terminal_agent.py
from langchain_core.messages import HumanMessage
from tools import shell
from agent import get_agent_executor
from pydantic import BaseModel

import textwrap
import shutil
import sys

# Define model and tools
tools = [shell]

# Create the React agent
agent_executor = get_agent_executor(tools)


class ChatInput(BaseModel):
    message: str


def get_width():
    return shutil.get_terminal_size().columns


def print_user_bubble(text: str):
    term_w = get_width()
    max_total = int(term_w * 3 / 4)
    max_inner = max_total - 4

    wrapped = textwrap.fill(text, width=max_inner)
    lines = wrapped.splitlines()

    actual_inner = max(len(line) for line in lines)
    bubble_w = actual_inner + 4
    indent = term_w - bubble_w

    # right-aligned bubble
    print(" " * indent + "╭" + "─" * (actual_inner + 2) + "╮")
    for line in lines:
        print(" " * indent + "│ " + line.ljust(actual_inner) + " │")
    print(" " * indent + "╰" + "─" * (actual_inner + 2) + "╯")


def print_ai_bubble(text: str):
    term_w = get_width()
    max_total = int(term_w * 3 / 4)
    max_inner = max_total - 4

    wrapped = textwrap.fill(text, width=max_inner)
    lines = wrapped.splitlines()

    actual_inner = max(len(line) for line in lines)
    # left-aligned bubble: indent = 0
    indent = 0

    print("╭" + "─" * (actual_inner + 2) + "╮")
    for line in lines:
        print("│ " + line.ljust(actual_inner) + " │")
    print("╰" + "─" * (actual_inner + 2) + "╯")


def print_banner():
    width = get_width()
    line = "━" * width
    print(line)
    print("🧠 OpenAI Chat Agent — type 'exit' to quit".center(width))


def print_output(text: str):
    width = get_width()
    print("\n🤖 Assistant:\n")
    print(textwrap.fill(text, width=width))
    print()


def clear_last_line():
    # Move cursor up and clear the line (ANSI escape sequences)
    sys.stdout.write("\033[F")  # Move cursor up one line
    sys.stdout.write("\033[K")  # Clear line
    sys.stdout.flush()


def main():
    print_banner()

    while True:
        try:
            user_input = input("> ")
            if user_input.lower() in {"exit", "quit"}:
                break

            clear_last_line()  # Hide the input line after pressing enter

            chat_input = ChatInput(message=user_input)

            print_user_bubble(chat_input.message)

            result = agent_executor.invoke(
                {"messages": [HumanMessage(content=chat_input.message)]},
                config={
                    "configurable": {"thread_id": "abc123"},
                    "recursion_limit": 100,
                },
            )

            messages = result.get("messages", [])
            print_ai_bubble(messages[-1].content)

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break


if __name__ == "__main__":
    main()
