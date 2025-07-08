import curses
import textwrap
import time
import pyperclip
from multiprocessing import Queue
from typing import List, Tuple, Dict
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

    def __init__(
        self,
        *,
        human_queue: Queue,
        ai_queue: Queue,
        popup_queue: Queue,
        popup_response_queue: Queue
    ):
        # default input height (will grow later in _recalculate_layout)
        self.input_h = 3

        # IPC queues
        self.human_queue = human_queue
        self.ai_queue = ai_queue
        self.popup_queue = popup_queue
        self.popup_response_queue = popup_response_queue

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

        # Popup state...
        self.popup_active: bool = False
        self.popup_message: str = ""
        self.popup_buffer: str = ""
        self.popup_win = None
        self.popup_input_win = None
        self.popup_h = 0
        self.popup_w = 0
        self.popup_y = 0
        self.popup_x = 0

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
            # 1) check for new popup requests
            if not self.popup_queue.empty():
                self.popup_message = self.popup_queue.get()
                self.popup_buffer = ""
                self.show_popup(self.popup_message)

            # 2) if popup is active, drive popup UI
            if self.popup_active:
                self._draw_popup()
                self._handle_popup_input()
                time.sleep(0.01)
                continue

            # 3) otherwise, normal chat flow
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
        Configure curses: disable the real cursor and set up color pairs.
        """
        # hide the real hardware cursor
        curses.curs_set(0)
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
        Resize the chat and input windows based on the current input buffer.
        The input window height grows to fit wrapped lines, and the chat window
        height shrinks accordingly. The sidebar remains full-height.
        """
        inner_w = self.chat_w - 4  # account for box borders and prompt prefix
        lines: List[str] = []
        for para in self.input_buffer.split("\n"):
            wrapped = textwrap.wrap(para, width=inner_w) or [""]
            lines.extend(wrapped)

        new_input_h = len(lines) + 2  # top & bottom borders
        max_h = self.height - 3  # leave room for at least 1 chat line + borders
        new_input_h = min(new_input_h, max_h)

        if new_input_h == self.input_h:
            return

        self.input_h = new_input_h
        self.chat_h = self.height - self.input_h

        self.chat_win.resize(self.chat_h, self.chat_w)
        self.input_win.resize(self.input_h, self.chat_w)
        self.input_win.mvwin(self.chat_h, 0)

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
        Draw the input window with a '> ' prompt on the first line,
        wrap text to the chat pane width, and render a synthetic cursor
        that advances even when typing spaces.
        """
        win = self.input_win
        win.erase()
        win.box()

        inner_w = self.chat_w - 4  # account for borders + prompt prefix

        # Wrap each paragraph, preserving explicit newlines
        paras = self.input_buffer.split("\n")
        lines: List[str] = []
        for para in paras:
            wrapped = textwrap.wrap(para, width=inner_w) or [""]
            lines.extend(wrapped)

        # Only show as many lines as will fit
        visible = self.input_h - 2
        display = lines[-visible:]

        # Draw each line with prompt or padding
        for idx, line in enumerate(display, start=1):
            prefix = "> " if idx == 1 else "  "
            win.addstr(idx, 1, prefix + line, self.default_attr)

        # Synthetic cursor position based on raw buffer (so spaces count)
        raw_last = paras[-1]
        col_offset = len(raw_last) % inner_w
        if raw_last and col_offset == 0:
            col_offset = inner_w

        cursor_row = len(display)
        prefix_len = 2
        cursor_col = 1 + prefix_len + col_offset
        max_col = self.chat_w - 2
        if cursor_col > max_col:
            cursor_col = max_col

        # Draw the cursor as a reversed character or blank
        try:
            ch = win.inch(cursor_row, cursor_col) & 0xFF
            win.addch(cursor_row, cursor_col, ch, curses.A_REVERSE)
        except curses.error:
            win.addstr(cursor_row, cursor_col, " ", curses.A_REVERSE)

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

    def show_popup(self, message: str) -> None:
        """
        Activate a popup showing `message` and an input box underneath.
        """
        self.popup_active = True
        self.popup_message = message
        self.popup_buffer = ""
        self._create_popup_windows()

    def hide_popup(self) -> None:
        """
        Deactivate and destroy the popup windows.
        """
        self.popup_active = False
        if self.popup_win:
            del self.popup_win
            self.popup_win = None
        if self.popup_input_win:
            del self.popup_input_win
            self.popup_input_win = None

    def _create_popup_windows(self) -> None:
        """
        Compute size and position, then create the popup windows.
        """
        # popup covers 70% of width and 50% of height, centered
        ph = max(6, self.height // 2)
        pw = max(20, (self.width * 7) // 10)
        py = (self.height - ph) // 2
        px = (self.width - pw) // 2

        # content window (with border)
        self.popup_h = ph - 3  # leave 3 rows for input box
        self.popup_w = pw
        self.popup_y = py
        self.popup_x = px

        self.popup_win = curses.newwin(self.popup_h, pw, py, px)
        self.popup_input_win = curses.newwin(3, pw, py + self.popup_h, px)

        for win in (self.popup_win, self.popup_input_win):
            win.bkgd(" ", self.default_attr)
            win.clear()
            win.box()
            win.refresh()

    def _draw_popup(self) -> None:
        """
        Draw the popup message and input prompt, and render
        a synthetic cursor in the popup input field.
        """
        # 1) Render the message portion
        mw = self.popup_win
        if mw is None:
            raise Exception(
                "popup_win has not been initialized. This should not happen."
            )
        mw.erase()
        mw.box()
        mw.addstr(0, 2, " Popup ", self.default_attr)

        inner_msg_w = self.popup_w - 2
        lines = textwrap.wrap(self.popup_message, width=inner_msg_w) or [""]
        visible_msg = self.popup_h - 2
        for idx, line in enumerate(lines[:visible_msg], start=1):
            mw.addstr(idx, 1, line.ljust(inner_msg_w), self.default_attr)
        mw.refresh()

        # 2) Render the input box
        iw = self.popup_input_win
        if iw is None:
            raise Exception(
                "popup_win has not been initialized. This should not happen."
            )
        iw.erase()
        iw.box()

        # Prepare prompt + buffer, clamped to available space
        prefix = "> "
        inner_in_w = self.popup_w - 2  # width inside the borders
        text = prefix + self.popup_buffer
        display = text[:inner_in_w].ljust(inner_in_w)
        iw.addstr(1, 1, display, self.default_attr)

        # 3) Synthetic cursor at end of text
        # cursor column is 1 (left border) + len(display before clipping)
        cursor_col = 1 + min(len(text), inner_in_w)
        try:
            ch = iw.inch(1, cursor_col) & 0xFF
            iw.addch(1, cursor_col, ch, curses.A_REVERSE)
        except curses.error:
            # if it's past the end, draw a reversed space
            iw.addstr(1, cursor_col, " ", curses.A_REVERSE)

        iw.refresh()

    def _handle_popup_input(self) -> None:
        """
        Handle key events when popup is active.
        Enter submits (hides popup), backspace edits buffer.
        """
        if self.popup_input_win is None:
            raise Exception("popup_input_win has not been initialized.")
        key = self.popup_input_win.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            # user has submitted
            self.popup_response_queue.put(self.popup_buffer)
            self.hide_popup()
            return
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self.popup_buffer = self.popup_buffer[:-1]
        elif 32 <= key < 256:
            self.popup_buffer += chr(key)

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
        Process incoming AI messages and tool calls,
        and autoscroll chat and sidebar if each was already at its bottom.
        """
        chat_at_bottom = self.chat_offset == self._max_chat_offset()
        sidebar_at_bottom = self.sidebar_offset == self._max_sidebar_offset()

        # drain all queued AI/tool events
        while not self.ai_queue.empty():
            calls, ai_msg = self.ai_queue.get()

            # record the raw tool calls
            if isinstance(calls, dict):
                self.tool_calls.append(calls)
            else:
                self.tool_calls.extend(calls)

            # append the AI chat message
            self.messages.append((ai_msg, "ai"))

        # if we were viewing the bottom, stay pinned to new bottom
        if chat_at_bottom:
            self.chat_offset = self._max_chat_offset()
        if sidebar_at_bottom:
            self.sidebar_offset = self._max_sidebar_offset()

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
