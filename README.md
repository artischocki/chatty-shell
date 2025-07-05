# Chatty‑Shell

**Chatty‑Shell** is a terminal-based AI assistant that lets you chat naturally while executing real shell commands in your current session. It’s designed to be transparent, predictable, and safe—yet powerful.

---

## 🚀 Features

* **Natural Language Chat**
  Talk to the AI just like a friend—ask questions, get explanations, or request commands.

* **Shell Tool**

  * The agent executes real shell commands directly from the chat in your current terminal session.
  * Non‑destructive commands (e.g., `ls`, `cat`, `pwd`) can be run freely by the agent.

* **History Lookup Tool (Optional)**

  * Requires your consent, because history can contain sensitive information. You don't have to use this feature.
  * Inspect your past shell commands to recall context.

---

## 🔧 Shell Tool Rules

1. **Non‑destructive Commands**
   The Agent may run any command that doesn’t modify or delete existing files _without_ asking.

2. **File‑Altering Operations**

   * If a command will change or remove files, the agent **must ask for your permission** first.
   * If **you explicitly ask** for file changes or risky operations, it may proceed immediately.

3. **File Creation**

   * No prior permission is needed to create new files.
   * The agent will always **inform you** when it has created any file (and where).

---

## 🕵 History Lookup Tool Rules

* You grant permission once via the chat application.
* After that, the agent can inspect your shell history whenever it might be useful.
* No further prompts are needed for history lookups.

---

## ⚠️ Warnings & Best Practices

* **Real Effects**: Commands you issue in Chatty‑Shell run in your live terminal session. Mistakes can have immediate consequences.
* **Review Before Execution**: Always read and confirm tool‑generated commands before they run.
* **Sensitive Data**: Avoid sharing passwords or secrets in chat. Chatty‑Shell does not redact them automatically.
* **Backups**: Keep backups of important files—especially before performing batch or recursive operations.

---

## 📦 Installation

```bash
pip install chatty-shell
```

## 💬 Usage

After installation, start the assistant with:

```bash
chat
```

Then type as you would in any chat:

![Demo](./assets/demo.gif)

* Prefix any message with a shell command directly, or just ask the AI to run one.
* The agent will display a shell-style response bubble with the command output.

---

## 🔐 Security & Privacy

* **Credentials**: Chatty‑Shell does not handle SSH keys or API tokens. Any command touching credentials is your responsibility.
* **Local Scope**: All commands affect your local machine only (no cloud sync).

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
