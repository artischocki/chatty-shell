import os
import getpass

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver

from exceptions import MissingPrompException

API_KEY = "OPENAI_API_KEY"


def _get_llm(model: str | None = None) -> ChatOpenAI:
    # default model is gpt-3.5-turbo
    if model is None:
        model = "gpt-3.5-turbo"
    if not os.environ.get(API_KEY):
        os.environ[API_KEY] = getpass.getpass("Enter your OpenAI-API key: ")

    llm = ChatOpenAI(model=model)
    return llm


def _get_memory():
    return MemorySaver()


def get_agent_executor(
    tools: list[BaseTool],
    llm: ChatOpenAI | None = None,
    memory: MemorySaver | None = None,
    system_prompt: str = "",
) -> Runnable:
    if llm is None:
        # get default llm
        llm = _get_llm()
    if memory is None:
        # get new chat history
        memory = _get_memory()
    if system_prompt == "":
        # raise MissingPrompException
        system_prompt = "You are a terminal agent."

    agent_executor = create_react_agent(
        model=llm, tools=tools, prompt=system_prompt, checkpointer=memory
    )
    return agent_executor
