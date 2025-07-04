# 🎙️ LangGraph Terminal Chat Agent

A sleek, interactive terminal-based chat agent built with LangGraph’s prebuilt React agent and OpenAI’s GPT-4.  
Type `ai` to hop into a chat session that:

- 💬 Wraps your messages in right-aligned speech bubbles  
- 🤖 Presents AI replies in left-aligned bubbles  
- 🛠️ Splits tool calls into a neat command/response bubble  
- 📐 Auto-fits each bubble to your terminal width (up to ¾ of the screen)  
- ✨ Clears your input line for a cleaner chat UI  

---

## 🚀 Features

- **Prebuilt React Agent**  
  Leverage LangGraph’s `create_react_agent` with minimal wiring—no custom graph definitions needed.

- **Shell Tool Integration**  
  Prefix any message with a shell command (or call via the React agent) and see the output in a split bubble.

- **Adaptive Bubbles**  
  Messages auto-wrap and right-/left-align, shrinking to fit their content.

- **Disappearing Prompt**  
  Your typed line vanishes on Enter, leaving only the formatted chat bubbles.

---

## 💾 Installation

1. **Clone the repo**  
   ```bash
   git clone https://github.com/your-username/langgraph-terminal-agent.git
   cd langgraph-terminal-agent
   python src/main.py
   ```
TODO pypi package releasen
