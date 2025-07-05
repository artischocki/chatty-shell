import curses
import textwrap
import time
import subprocess
from multiprocessing import Queue
from typing import Tuple, Optional
from chatty_shell.frontend.ascii import wrap_message


def copy_to_clipboard(text: str):
    try:
        import pyperclip

        pyperclip.copy(text)
    except ImportError:
        p = subprocess.Popen(
            ["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE
        )
        p.communicate(text.encode())


class View:
    def __init__(self, *, human_queue: Queue, ai_queue: Queue):
        # queues
        self.human_queue = human_queue
        self.ai_queue = ai_queue

        # chat + input state
        self.messages: list[Tuple[str, str]] = []
        self.input_buffer: str = ""
        self.scroll_offset: int = 0
        self.scroll_speed: int = 3

        # status & debug
        self.status_msg: Optional[str] = None
        self.status_time: float = 0.0
        self.debug_msgs: list[str] = []
        self.show_debug: bool = False

        # color attributes (set in _init_curses)
        self.default_attr = 0
        self.code_attr = 0

    def log_debug(self, msg: str):
        self.debug_msgs.append(msg)

    def run(self):
        curses.wrapper(self._main)

    def _main(self, stdscr):
        self._init_curses(stdscr)
        self._create_windows(stdscr)
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

    # ── Setup ────────────────────────────────────────────────────────────────────

    def _init_curses(self, stdscr):
        curses.curs_set(1)
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)

        curses.start_color()
        curses.use_default_colors()
        # default fg/bg, and white-on-black for code
        curses.init_pair(1, -1, -1)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
        self.default_attr = curses.color_pair(1)
        self.code_attr = curses.color_pair(2)

        stdscr.bkgd(" ", self.default_attr)
        curses.mousemask(
            curses.BUTTON4_PRESSED | curses.BUTTON5_PRESSED | curses.BUTTON2_PRESSED
        )
        curses.mouseinterval(0)

    def _create_windows(self, stdscr):
        h, w = stdscr.getmaxyx()
        self.height, self.width = h, w
        self.sidebar_w = max(20, w // 4)
        self.chat_w = w - self.sidebar_w
        self.input_h = 3
        self.chat_h = h - self.input_h

        def init_win(win):
            win.bkgd(" ", self.default_attr)
            win.clear()
            win.box()
            win.refresh()

        self.chat_win = curses.newwin(self.chat_h, self.chat_w, 0, 0)
        init_win(self.chat_win)
        self.sidebar_win = curses.newwin(self.chat_h, self.sidebar_w, 0, self.chat_w)
        init_win(self.sidebar_win)
        self.input_win = curses.newwin(self.input_h, w, self.chat_h, 0)
        init_win(self.input_win)
        self.debug_win = curses.newwin(h, w, 0, 0)
        init_win(self.debug_win)

    # ── Drawing ──────────────────────────────────────────────────────────────────

    def _draw_all(self):
        self._draw_chat()
        self._draw_sidebar()
        self._draw_input()
        self._refresh()

    def _draw_chat(self):
        win = self.chat_win
        win.erase()
        win.box()

        flat = self._flatten_chat_map()
        # save for click-to-copy
        self.last_chat_map = flat

        total = len(flat)
        visible = self.chat_h - 2
        max_off = max(0, total - visible)
        self.scroll_offset = min(max_off, max(0, self.scroll_offset))

        for row, (text, who, _, is_code) in enumerate(
            flat[self.scroll_offset : self.scroll_offset + visible], start=1
        ):
            x = 1 if who == "ai" else self.chat_w - len(text) - 1
            attr = self.code_attr if is_code else self.default_attr
            win.addstr(row, x, text, attr)

        win.refresh()

    def _draw_sidebar(self):
        win = self.sidebar_win
        win.erase()
        win.box()
        if self.status_msg and (time.time() - self.status_time) < 3:
            win.addstr(1, 2, self.status_msg[: self.sidebar_w - 4], self.default_attr)
        else:
            self.status_msg = None
        win.refresh()

    def _draw_input(self):
        win = self.input_win
        win.erase()
        win.box()
        prompt = "> " + self.input_buffer[: self.width - 3]
        win.addstr(1, 1, prompt, self.default_attr)
        win.refresh()

    def _draw_debug(self):
        win = self.debug_win
        win.erase()
        win.box()
        y = 1
        for msg in self.debug_msgs[-(self.height - 2) :]:
            for seg in textwrap.wrap(msg, self.width - 2):
                if y < self.height - 1:
                    win.addstr(y, 1, seg, self.default_attr)
                    y += 1
        win.addstr(self.height - 1, 2, "[F2] Hide debug", self.default_attr)
        win.refresh()

    def _refresh(self):
        self.chat_win.noutrefresh()
        self.sidebar_win.noutrefresh()
        self.input_win.noutrefresh()
        curses.doupdate()

    # ── Flatten & Parse ──────────────────────────────────────────────────────────

    def _flatten_chat_map(self) -> list[tuple[str, Optional[str], int, bool]]:
        """
        Returns list of (line_text, who, msg_index, is_code) for
        every wrapped segment plus one blank per message.
        """
        out: list[tuple[str, Optional[str], int, bool]] = []
        inner_w = self.chat_w - 2

        for idx, (msg, who) in enumerate(self.messages):
            # wrap_message now returns (line, is_code)
            segments = wrap_message(msg, inner_w, who)
            for line, is_code in segments:
                out.append((line, who, idx, is_code))
            out.append(("", None, idx, False))

        return out

    # ── Queues ───────────────────────────────────────────────────────────────────

    def _drain_ai_queue(self):
        while not self.ai_queue.empty():
            _, ai_msg = self.ai_queue.get()
            self.messages.append((ai_msg, "ai"))
            self.log_debug(f"AI → {ai_msg!r}")

    # ── Input & Mouse ────────────────────────────────────────────────────────────

    def _handle_input(self):
        keys = []
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
            if key in (curses.KEY_ENTER, 10, 13):
                if burst:
                    self.input_buffer += " "
                else:
                    self._send_human()
                continue
            if key in (curses.KEY_BACKSPACE, 127, 8):
                self.input_buffer = self.input_buffer[:-1]
                continue
            if key == 27:
                exit()
            if 32 <= key < 256:
                self.input_buffer += chr(key)

    def _send_human(self):
        self.human_queue.put(self.input_buffer)
        self.messages.append((self.input_buffer, "human"))
        self.log_debug(f"Human → {self.input_buffer!r}")
        self.input_buffer = ""
        self.scroll_offset = 0

    def _handle_mouse(self):
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return

        # only handle clicks inside the chat pane
        if not (0 <= my < self.chat_h and 0 <= mx < self.chat_w):
            return

        # scroll wheel (unchanged) …
        flat = self._flatten_chat_map()
        total = len(flat)
        visible = self.chat_h - 2
        max_off = max(0, total - visible)
        if bstate & curses.BUTTON4_PRESSED:
            self.scroll_offset = max(0, self.scroll_offset - self.scroll_speed)
            return
        if bstate & curses.BUTTON5_PRESSED:
            self.scroll_offset = min(max_off, self.scroll_offset + self.scroll_speed)
            return

        # middle-click: copy
        if bstate & curses.BUTTON2_PRESSED:
            line_idx = (my - 1) + self.scroll_offset
            if not (0 <= line_idx < len(self.last_chat_map)):
                return

            _, _, msg_idx, is_code = self.last_chat_map[line_idx]

            if is_code:
                # collect only code lines for this message, stripping bubble borders
                code_lines: list[str] = []
                for text, who, idx, code_flag in self.last_chat_map:
                    if idx == msg_idx and code_flag:
                        if text.startswith("│ ") and text.endswith(" │"):
                            content = text[2:-2]
                        else:
                            content = text
                        code_lines.append(content)
                text_to_copy = "\n".join(code_lines)

            else:
                # fallback: copy the original un-framed message
                text_to_copy = self.messages[msg_idx][0]

            copy_to_clipboard(text_to_copy)
            self.status_msg = "Copied to clipboard!"
            self.status_time = time.time()
            return
