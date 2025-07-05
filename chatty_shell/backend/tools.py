from langchain.tools import tool
import subprocess


@tool
def shell_tool(command: str) -> str:
    """Executes a shell command and returns the output."""
    try:
        result = subprocess.check_output(
            command, shell=True, stderr=subprocess.STDOUT, text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        return f"Error:\n{e.output}"
