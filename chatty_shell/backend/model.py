from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv
import os
from pathlib import Path
import time

from chatty_shell.backend.agent import get_agent_executor
from chatty_shell.backend.messages import sort_tools_calls
from chatty_shell.backend.tools import shell_tool
from chatty_shell.backend.prompts import system_prompt
from chatty_shell.backend.exceptions import MissingApiKeyException


class ChatInput(BaseModel):
    message: str


class Model:
    def __init__(self, logger):
        self.logger = logger
        # Authenticate
        self._get_api_token()
        if self.api_key_set():
            self._get_agent()

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

    def _get_api_token(self) -> None:
        # try to get from global env
        token = os.getenv("OPENAI_API_KEY")
        if token:
            self._api_key = token
            return

        # try to get from .env file
        env_path = Path(__file__).parents[2] / ".env"
        load_dotenv(env_path)
        token = os.getenv("OPENAI_API_KEY")
        if token:
            self._api_key = token
            return

        # else None
        self._api_key = None

    def _get_agent(self) -> None:
        if not self._api_key:
            raise MissingApiKeyException
        # Define model and tools
        tools = [shell_tool]
        # Create the React agent
        self._agent_executor = get_agent_executor(
            tools=tools, system_prompt=system_prompt, token=self._api_key
        )
        return

    def api_key_set(self) -> bool:
        if self._api_key is None:
            return False
        return True

    def set_api_key(self, val: str) -> None:
        self.logger.info("Setting api key and reinit agent.")
        self._api_key = val
        # reinitialize agent with new token
        self._get_agent()
        return

    def reset_api_key(self) -> None:
        self.logger.info("Resetting api key and agent executor.")
        self._api_key = None
        self._agent_executor = None
