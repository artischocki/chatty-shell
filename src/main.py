# terminal_agent.py
from langchain_core.messages import HumanMessage
from agent import get_agent_executor
from pydantic import BaseModel

from messages import sort_tools_calls
from tools import shell
from system_prompt import system_prompt

from out import print_banner, clear_last_line, print_ai_bubble, print_user_bubble
import pprint

# Define model and tools
tools = [shell]

# Create the React agent
agent_executor = get_agent_executor(tools=tools, system_prompt=system_prompt)


class ChatInput(BaseModel):
    message: str


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

            new_messages = []
            for i in range(len(messages)):
                if isinstance(messages[::-1][i], HumanMessage):
                    new_messages = messages[-i:]
                    break

            sorted_tool_calls = sort_tools_calls(new_messages)

            pprint.pp(sorted_tool_calls)
            print()
            print_ai_bubble(messages[-1].content)

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break


if __name__ == "__main__":
    main()
