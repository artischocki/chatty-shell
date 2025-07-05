from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv
import os

from chatty_shell.agent import get_agent_executor
from chatty_shell.messages import sort_tools_calls
from chatty_shell.tools import shell
from chatty_shell.system_prompt import system_prompt
from chatty_shell.out import (
    print_banner,
    clear_last_line,
    print_ai_bubble,
    print_user_bubble,
    print_tool_bubble,
)


def get_agent(api_token: str):
    # Define model and tools
    tools = [shell]
    # Create the React agent
    agent_executor = get_agent_executor(
        tools=tools, system_prompt=system_prompt, token=api_token
    )
    return agent_executor


class ChatInput(BaseModel):
    message: str


def get_api_token() -> str:
    # return env var if set
    token = os.getenv("OPENAI_API_KEY")
    if token:
        return token

    # Locate or create .env
    env_path = find_dotenv(usecwd=True) or os.path.join(os.getcwd(), ".env")
    load_dotenv(env_path)
    token = os.getenv("OPENAI_API_KEY")
    if token:
        return token

    # Prompt once and persist if missing
    token = input("🔑 Enter your OpenAI API key: ").strip()
    with open(env_path, "a") as f:
        f.write(f"\nOPENAI_API_KEY={token}\n")
    load_dotenv(env_path)
    return token


def main():
    print_banner()

    # Authenticate
    api_token = get_api_token()
    agent_executor = get_agent(api_token)

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

            if sorted_tool_calls:
                for command in sorted_tool_calls:
                    print_tool_bubble(command, sorted_tool_calls[command])
            # pprint.pp(sorted_tool_calls)
            # print()
            print_ai_bubble(messages[-1].content)

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break


if __name__ == "__main__":
    main()
