import curses
import textwrap
import time
import pyperclip
from multiprocessing import Queue
from typing import List, Tuple, Optional, Dict
from chatty_shell.frontend.ascii import wrap_message


def copy_to_clipboard(text: str) -> None:
    """
    Copy the given text to the system clipboard.
    """
    pyperclip.copy(text)


class View:
    """
    Text-based UI using curses. Displays a scrollable chat pane on the left,
    a scrollable tool-output sidebar on the right, and an input prompt at the bottom.
    Supports code highlighting, mouse scrolling, and middle-click copying.
    """

    def __init__(self, *, human_queue: Queue, ai_queue: Queue):
        # default input height (will grow later in _recalculate_layout)
        self.input_h = 3

        # IPC queues
        self.human_queue = human_queue
        self.ai_queue = ai_queue

        # Chat state...
        self.messages: List[Tuple[str, str]] = []
        self.input_buffer: str = ""
        self.chat_offset: int = 0
        self.chat_scroll_speed: int = 3

        # Sidebar state...
        self.sidebar_offset: int = 0
        self.tool_calls: List[Dict[str, str]] = []

        # Debug...
        self.debug_messages: List[str] = []
        self.show_debug: bool = False

        # Color attrs (filled in _init_curses)...
        self.default_attr = 0
        self.code_attr = 0
        self.cmd_attr = 0

    def run(self) -> None:
        """
        Launch the curses application.
        """
        curses.wrapper(self._main)

    def _main(self, stdscr) -> None:
        """
        Curses entry point: initialize, then enter the main loop.
        """
        self._init_curses(stdscr)
        self._init_windows(stdscr)
        self.input_win.nodelay(True)
        self.input_win.keypad(True)

        while True:
            self._drain_ai_queue()

            if self.show_debug:
                self._draw_debug()
                self._handle_debug_toggle()
                time.sleep(0.01)
                continue

            self._draw_all()
            self._handle_input()
            time.sleep(0.01)

    def _init_curses(self, stdscr) -> None:
        """
        Configure curses modes and initialize color pairs.
        """
        curses.curs_set(1)
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)

        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, -1, -1)  # default
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)  # code/output
        curses.init_pair(3, curses.COLOR_BLUE, -1)  # commands

        self.default_attr = curses.color_pair(1)
        self.code_attr = curses.color_pair(2)
        self.cmd_attr = curses.color_pair(3)

        stdscr.bkgd(" ", self.default_attr)
        curses.mousemask(
            curses.BUTTON4_PRESSED | curses.BUTTON5_PRESSED | curses.BUTTON2_PRESSED
        )
        curses.mouseinterval(0)

    def _init_windows(self, stdscr) -> None:
        """
        Create and initialize the chat, sidebar, input, and debug windows.
        Chat + input share the left width; sidebar runs full height on the right.
        """
        h, w = stdscr.getmaxyx()
        self.height, self.width = h, w
        self.sidebar_w = max(20, w // 4)
        self.chat_w = w - self.sidebar_w
        # input_h was set by _recalculate_layout (or defaults to 3)
        self.chat_h = h - self.input_h

        def setup(win):
            win.bkgd(" ", self.default_attr)
            win.clear()
            win.box()
            win.refresh()

        # left: chat area
        self.chat_win = curses.newwin(self.chat_h, self.chat_w, 0, 0)
        setup(self.chat_win)
        # right: sidebar full height
        self.sidebar_win = curses.newwin(self.height, self.sidebar_w, 0, self.chat_w)
        setup(self.sidebar_win)
        # bottom-left: input, same width as chat
        self.input_win = curses.newwin(self.input_h, self.chat_w, self.chat_h, 0)
        setup(self.input_win)
        # full-screen debug overlay
        self.debug_win = curses.newwin(self.height, w, 0, 0)
        setup(self.debug_win)

    def _recalculate_layout(self) -> None:
        """
        Recompute chat_h and input_h based on current input_buffer.
        Resize chat and input windows; leave sidebar at full height.
        """
        inner_w = self.chat_w - 3  # account for borders
        lines: list[str] = []
        for para in self.input_buffer.split("\n"):
            wrapped = textwrap.wrap(para, width=inner_w) or [""]
            lines.extend(wrapped)

        # new height = top border + lines + bottom border
        new_input_h = len(lines) + 2
        max_h = self.height - 3
        new_input_h = min(new_input_h, max_h)

        if new_input_h == self.input_h:
            return

        self.input_h = new_input_h
        self.chat_h = self.height - self.input_h

        # resize/move chat
        self.chat_win.resize(self.chat_h, self.chat_w)
        # resize/move input (same width as chat)
        self.input_win.resize(self.input_h, self.chat_w)
        self.input_win.mvwin(self.chat_h, 0)
        # sidebar stays full height; debug stays full screen

    def _draw_all(self) -> None:
        """
        Before each frame, recalc sizes then draw all panes.
        """
        self._recalculate_layout()
        self._draw_chat()
        self._draw_sidebar()
        self._draw_input()
        self._refresh()

    def _draw_chat(self) -> None:
        """
        Render chat messages with bubble framing and syntax-highlighted code.
        """
        win = self.chat_win
        win.erase()
        win.box()
        win.addstr(0, 2, " Chat ", self.default_attr)

        flat = self._flatten_chat()
        self.last_chat_map = flat

        visible = self.chat_h - 2
        total = len(flat)
        max_off = max(0, total - visible)
        self.chat_offset = min(max_off, max(0, self.chat_offset))

        segment = flat[self.chat_offset : self.chat_offset + visible]
        for row, (text, who, is_code) in enumerate(segment, start=1):
            x = 1 if who == "ai" else self.chat_w - len(text) - 1
            if not is_code:
                win.addstr(row, x, text, self.default_attr)
            else:
                left, inner, right = text[:2], text[2:-2], text[-2:]
                win.addstr(row, x, left, self.default_attr)
                win.addstr(row, x + 2, inner, self.code_attr)
                win.addstr(row, x + 2 + len(inner), right, self.default_attr)

        win.refresh()

    def _draw_sidebar(self) -> None:
        """
        Render the sidebar (full-height) with scrolling.
        """
        win = self.sidebar_win
        win.erase()
        win.box()
        win.addstr(0, 2, " Terminal Session ", self.default_attr)

        flat = self._flatten_sidebar()
        visible = self.height - 2
        total = len(flat)
        max_off = max(0, total - visible)
        self.sidebar_offset = min(max_off, max(0, self.sidebar_offset))

        for row, (text, attr) in enumerate(
            flat[self.sidebar_offset : self.sidebar_offset + visible], start=1
        ):
            win.addstr(row, 1, text, attr)

        win.refresh()

    def _draw_input(self) -> None:
        """
        Render the input window, growing to fit the input, with a '> ' prompt
        at the start of the first line.
        """
        win = self.input_win
        win.erase()
        win.box()

        inner_w = self.width - 3

        # wrap each paragraph to fit, preserving explicit newlines
        lines: List[str] = []
        for para in self.input_buffer.split("\n"):
            wrapped = textwrap.wrap(para, width=inner_w) or [""]
            lines.extend(wrapped)

        # only display as many lines as will fit
        visible = self.input_h - 2
        display = lines[-visible:]

        for idx, line in enumerate(display, start=1):
            # first line gets the prompt, subsequent lines get two spaces
            prefix = "> " if idx == 1 else "  "
            text = prefix + line
            win.addstr(idx, 1, text, self.default_attr)

        win.refresh()

    def _draw_debug(self) -> None:
        """
        Overlay a debug window showing internal log messages.
        """
        win = self.debug_win
        win.erase()
        win.box()
        y = 1
        for msg in self.debug_messages[-(self.height - 2) :]:
            for seg in textwrap.wrap(msg, self.width - 2):
                if y < self.height - 1:
                    win.addstr(y, 1, seg, self.default_attr)
                    y += 1
        win.addstr(self.height - 1, 2, "[F2] Hide debug", self.default_attr)
        win.refresh()

    def _refresh(self) -> None:
        """
        Batch-refresh all visible windows.
        """
        self.chat_win.noutrefresh()
        self.sidebar_win.noutrefresh()
        self.input_win.noutrefresh()
        curses.doupdate()

    def _flatten_chat(self) -> List[Tuple[str, str, bool]]:
        """
        Flatten chat messages into a list of (line, author, is_code) for rendering.
        """
        lines: List[Tuple[str, str, bool]] = []
        max_inner = self.chat_w - 2

        for msg, who in self.messages:
            for text, is_code in wrap_message(msg, max_inner, who):
                lines.append((text, who, is_code))
        return lines

    def _flatten_sidebar(self) -> List[Tuple[str, int]]:
        """
        Flatten tool calls into a list of (line, attribute) for rendering.
        """
        out: List[Tuple[str, int]] = []
        max_inner = self.sidebar_w - 2

        for call in self.tool_calls:
            for cmd, output in call.items():
                out.append((cmd[:max_inner], self.cmd_attr))
                for ln in output.splitlines():
                    text = ln[:max_inner]
                    pad = " " * (max_inner - len(text))
                    out.append((text + pad, self.code_attr))
                out.append((" " * max_inner, self.default_attr))

        return out

    def _drain_ai_queue(self) -> None:
        """
        Process incoming AI messages and tool calls, and autoscroll if at bottom.
        """
        at_bottom = self.chat_offset == self._max_chat_offset()

        while not self.ai_queue.empty():
            calls, ai_msg = self.ai_queue.get()
            if isinstance(calls, dict):
                self.tool_calls.append(calls)
            else:
                self.tool_calls.extend(calls)

            self.messages.append((ai_msg, "ai"))

        if at_bottom:
            self.chat_offset = self._max_chat_offset()

    def _max_chat_offset(self) -> int:
        """
        Compute the maximum scroll offset for the chat pane.
        """
        total = len(self._flatten_chat())
        visible = self.chat_h - 2
        return max(0, total - visible)

    def _max_sidebar_offset(self) -> int:
        """
        Compute the maximum scroll offset for the sidebar.
        """
        total = len(self._flatten_sidebar())
        visible = self.chat_h - 2
        return max(0, total - visible)

    def _handle_input(self) -> None:
        """
        Read and process all pending key and mouse events.
        Any Enter (KEY_ENTER, 10, 13) sends the message,
        unless part of a multi-key paste (then treated as space).
        """
        keys: List[int] = []
        while True:
            k = self.input_win.getch()
            if k == -1:
                break
            keys.append(k)
        if not keys:
            return

        burst = len(keys) > 1
        for key in keys:
            if key == curses.KEY_MOUSE:
                self._handle_mouse()
                continue

            if key == curses.KEY_F2:
                self.show_debug = True
                continue

            # Enter / Return: send or, in a paste burst, insert space
            if key in (curses.KEY_ENTER, 10, 13):
                if burst:
                    self.input_buffer += " "
                else:
                    self._send_human()
                continue

            if key in (curses.KEY_BACKSPACE, 127, 8):
                self.input_buffer = self.input_buffer[:-1]
                continue

            if key == 27:  # ESC
                exit()

            if 32 <= key < 256:
                self.input_buffer += chr(key)

    def _send_human(self) -> None:
        """
        Send the current input buffer as a human message if non-empty.
        """
        # Prevent sending empty or whitespace-only messages
        if not self.input_buffer.strip():
            return

        at_bottom = self.chat_offset == self._max_chat_offset()
        self.human_queue.put(self.input_buffer)
        self.messages.append((self.input_buffer, "human"))
        self.input_buffer = ""
        if at_bottom:
            self.chat_offset = self._max_chat_offset()

    def _handle_mouse(self) -> None:
        """
        Handle mouse scroll for chat/sidebar and middle-click copying.
        """
        try:
            _, mx, my, _, b = curses.getmouse()
        except curses.error:
            return

        # Chat pane area
        if 0 <= my < self.chat_h and 0 <= mx < self.chat_w:
            if b & curses.BUTTON4_PRESSED:
                self.chat_offset = max(0, self.chat_offset - self.chat_scroll_speed)
                return
            if b & curses.BUTTON5_PRESSED:
                self.chat_offset = min(
                    self._max_chat_offset(), self.chat_offset + self.chat_scroll_speed
                )
                return
            if b & curses.BUTTON2_PRESSED:
                line_idx = my - 1 + self.chat_offset
                if 0 <= line_idx < len(self.last_chat_map):
                    _, _, is_code = self.last_chat_map[line_idx]
                    msg_idx = self.last_chat_map[line_idx][2]
                    if is_code:
                        code_lines = [
                            text[2:-2]
                            for text, _, idx, code_flag in self.last_chat_map
                            if idx == msg_idx and code_flag
                        ]
                        copy_to_clipboard("\n".join(code_lines))
                    else:
                        copy_to_clipboard(self.messages[msg_idx][0])
                return

        # Sidebar area
        if 0 <= my < self.chat_h and self.chat_w <= mx < self.chat_w + self.sidebar_w:
            if b & curses.BUTTON4_PRESSED:
                self.sidebar_offset = max(
                    0, self.sidebar_offset - self.chat_scroll_speed
                )
            elif b & curses.BUTTON5_PRESSED:
                self.sidebar_offset = min(
                    self._max_sidebar_offset(),
                    self.sidebar_offset + self.chat_scroll_speed,
                )
            return

    def _handle_debug_toggle(self) -> None:
        """
        Close the debug overlay when F2 is pressed.
        """
        key = self.input_win.getch()
        if key == curses.KEY_F2:
            self.show_debug = False
            self.input_win.clear()
            self.input_win.box()
            self.input_win.refresh()
