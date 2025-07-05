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
        """
        Initialize the view with queues for outgoing human messages and incoming AI/tool responses.
        """
        # IPC queues
        self.human_queue: Queue = human_queue
        self.ai_queue: Queue = ai_queue

        # Chat state
        self.messages: List[Tuple[str, str]] = []  # (text, author)
        self.input_buffer: str = ""
        self.chat_offset: int = 0
        self.chat_scroll_speed: int = 3

        # Sidebar state
        self.tool_calls: List[Dict[str, str]] = []  # list of {cmd: output}
        self.sidebar_offset: int = 0

        # Debug overlay
        self.debug_messages: List[str] = []
        self.show_debug: bool = False

        # Color attributes (set in curses init)
        self.default_attr: int = 0
        self.code_attr: int = 0
        self.cmd_attr: int = 0

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
        """
        h, w = stdscr.getmaxyx()
        self.height, self.width = h, w
        self.sidebar_w = max(20, w // 4)
        self.chat_w = w - self.sidebar_w
        self.input_h = 3
        self.chat_h = h - self.input_h

        def setup(win):
            win.bkgd(" ", self.default_attr)
            win.clear()
            win.box()
            win.refresh()

        self.chat_win = curses.newwin(self.chat_h, self.chat_w, 0, 0)
        self.sidebar_win = curses.newwin(self.chat_h, self.sidebar_w, 0, self.chat_w)
        self.input_win = curses.newwin(self.input_h, w, self.chat_h, 0)
        self.debug_win = curses.newwin(h, w, 0, 0)

        for win in (self.chat_win, self.sidebar_win, self.input_win, self.debug_win):
            setup(win)

    def _draw_all(self) -> None:
        """
        Draw all panes and update the screen.
        """
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
        Render tool call commands and their outputs in a scrollable sidebar.
        """
        win = self.sidebar_win
        win.erase()
        win.box()

        flat = self._flatten_sidebar()
        visible = self.chat_h - 2
        total = len(flat)
        max_off = max(0, total - visible)
        self.sidebar_offset = min(max_off, max(0, self.sidebar_offset))

        segment = flat[self.sidebar_offset : self.sidebar_offset + visible]
        for row, (text, attr) in enumerate(segment, start=1):
            win.addstr(row, 1, text, attr)

        win.refresh()

    def _draw_input(self) -> None:
        """
        Render the user input prompt at the bottom.
        """
        win = self.input_win
        win.erase()
        win.box()
        prompt = "> " + self.input_buffer[: self.width - 3]
        win.addstr(1, 1, prompt, self.default_attr)
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
            elif key == curses.KEY_F2:
                self.show_debug = True
            elif key in (curses.KEY_ENTER, 10, 13):
                if burst:
                    self.input_buffer += " "
                else:
                    self._send_human()
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                self.input_buffer = self.input_buffer[:-1]
            elif key == 27:  # ESC
                exit()
            elif 32 <= key < 256:
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
