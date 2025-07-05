import curses
import textwrap
import time
import subprocess
from multiprocessing import Queue
from typing import Tuple, Optional
from chatty_shell.frontend.ascii import wrap_message


def copy_to_clipboard(text: str):
    """Try pyperclip first, then xclip."""
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
        # IPC queues
        self.human_queue = human_queue
        self.ai_queue = ai_queue

        # State
        self.messages: list[Tuple[str, str]] = []
        self.input_buffer: str = ""
        self.scroll_offset: int = 0
        self.scroll_speed: int = 3
        self.status_msg: Optional[str] = None
        self.status_time: float = 0.0
        self.debug_msgs: list[str] = []
        self.show_debug: bool = False

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

    def _init_curses(self, stdscr):
        curses.curs_set(1)
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, -1, -1)
        stdscr.bkgd(" ", curses.color_pair(1))
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
            win.bkgd(" ", curses.color_pair(1))
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

    def _draw_all(self):
        self._draw_chat()
        self._draw_sidebar()
        self._draw_input()
        self._refresh()

    def _draw_chat(self):
        win = self.chat_win
        win.erase()
        win.box()

        flat_map = self._flatten_chat_map()
        self.last_chat_map = flat_map

        total = len(flat_map)
        visible = self.chat_h - 2
        max_off = max(0, total - visible)
        self.scroll_offset = min(max_off, max(0, self.scroll_offset))

        slice_ = flat_map[self.scroll_offset : self.scroll_offset + visible]
        for row, (text, who, _) in enumerate(slice_, start=1):
            x = 1 if who == "ai" else self.chat_w - len(text) - 1
            win.addstr(row, x, text)

        win.refresh()

    def _draw_sidebar(self):
        win = self.sidebar_win
        win.erase()
        win.box()
        if self.status_msg and (time.time() - self.status_time) < 3:
            truncated = self.status_msg[: self.sidebar_w - 4]
            win.addstr(1, 2, truncated)
        else:
            self.status_msg = None
        win.refresh()

    def _draw_input(self):
        win = self.input_win
        win.erase()
        win.box()
        prompt = "> " + self.input_buffer[: self.width - 3]
        win.addstr(1, 1, prompt)
        win.refresh()

    def _draw_debug(self):
        win = self.debug_win
        win.erase()
        win.box()
        y = 1
        for msg in self.debug_msgs[-(self.height - 2) :]:
            for seg in textwrap.wrap(msg, self.width - 2):
                if y < self.height - 1:
                    win.addstr(y, 1, seg)
                    y += 1
        win.addstr(self.height - 1, 2, "[F2] Hide debug")
        win.refresh()

    def _refresh(self):
        self.chat_win.noutrefresh()
        self.sidebar_win.noutrefresh()
        self.input_win.noutrefresh()
        curses.doupdate()

    def _flatten_chat_map(self) -> list[tuple[str, Optional[str], int]]:
        out: list[tuple[str, Optional[str], int]] = []
        inner_w = self.chat_w - 2
        for idx, (msg, who) in enumerate(self.messages):
            bubble = wrap_message(msg, inner_w, who)
            for line in bubble:
                out.append((line, who, idx))
            out.append(("", None, idx))
        return out

    def _drain_ai_queue(self):
        while not self.ai_queue.empty():
            _, ai_msg = self.ai_queue.get()
            self.messages.append((ai_msg, "ai"))
            self.log_debug(f"AI → {ai_msg!r}")

    def _handle_input(self):
        # collect all keys this cycle
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
            if key == 27:  # ESC
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
        if not (0 <= my < self.chat_h and 0 <= mx < self.chat_w):
            return

        total = len(self._flatten_chat_map())
        visible = self.chat_h - 2
        max_off = max(0, total - visible)

        if bstate & curses.BUTTON4_PRESSED:
            self.scroll_offset = max(0, self.scroll_offset - self.scroll_speed)
        elif bstate & curses.BUTTON5_PRESSED:
            self.scroll_offset = min(max_off, self.scroll_offset + self.scroll_speed)
        elif bstate & curses.BUTTON2_PRESSED:
            line_idx = (my - 1) + self.scroll_offset
            if 0 <= line_idx < len(self.last_chat_map):
                _, _, msg_idx = self.last_chat_map[line_idx]
                full_msg = self.messages[msg_idx][0]
                copy_to_clipboard(full_msg)
                self.status_msg = "Copied to clipboard!"
                self.status_time = time.time()
