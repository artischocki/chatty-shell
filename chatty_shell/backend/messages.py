from langchain_core.messages import ToolMessage, AIMessage
from pydantic import BaseModel


class ChatInput(BaseModel):
    message: str


def sort_tools_calls(messages: list[ToolMessage | AIMessage]) -> dict[str, str]:
    tool_calls = {}
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        if not message.tool_calls:
            continue
        for tool_call in message.tool_calls:
            command = tool_call["args"]["command"]
            id = tool_call["id"]
            tool_calls[command] = id

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        for command in tool_calls:
            if tool_calls[command] == message.tool_call_id:
                tool_calls[command] = message.content
    return tool_calls
