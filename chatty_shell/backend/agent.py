import os
import getpass

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver

from chatty_shell.backend.exceptions import (
    MissingPromptException,
    MissingApiKeyException,
)

API_KEY = "OPENAI_API_KEY"


def _get_llm(model: str | None = None, api_token: str | None = None) -> ChatOpenAI:
    if api_token is None:
        raise MissingApiKeyException
    # default model is gpt-4.1-mini
    if model is None:
        model = "gpt-4.1-mini"

    llm = ChatOpenAI(model=model, api_key=api_token)
    return llm


def _get_memory():
    return MemorySaver()


def get_agent_executor(
    tools: list[BaseTool],
    token: str,
    llm: ChatOpenAI | None = None,
    memory: MemorySaver | None = None,
    system_prompt: str = "",
) -> Runnable:
    if llm is None:
        # get default llm
        llm = _get_llm(api_token=token)
    if memory is None:
        # get new chat history
        memory = _get_memory()
    if system_prompt == "":
        raise MissingPromptException

    agent_executor = create_react_agent(
        model=llm, tools=tools, prompt=system_prompt, checkpointer=memory
    )
    return agent_executor
