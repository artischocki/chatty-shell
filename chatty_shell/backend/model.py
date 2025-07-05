from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv
import os

from chatty_shell.backend.agent import get_agent_executor
from chatty_shell.backend.messages import sort_tools_calls
from chatty_shell.backend.tools import shell_tool
from chatty_shell.backend.prompts import system_prompt


def get_agent(api_token: str):
    # Define model and tools
    tools = [shell_tool]
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


class Model:
    def __init__(self):
        # Authenticate
        self._agent_executor = get_agent(get_api_token())

    def new_message(self, message: str):

        chat_input = ChatInput(message=message)

        result = self._agent_executor.invoke(
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
        final_message = messages[-1].content

        return sorted_tool_calls, final_message
