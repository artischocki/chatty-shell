import curses
import textwrap


def view(stdscr):
    # Initialize curses modes
    curses.curs_set(1)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)

    # Initialize colors for default background
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, -1, -1)
    default_color = curses.color_pair(1)

    # Apply background to stdscr
    stdscr.bkgd(" ", default_color)
    stdscr.clear()
    stdscr.refresh()

    # Get screen dimensions
    height, width = stdscr.getmaxyx()

    # Calculate panel sizes
    sidebar_width = max(20, width // 4)
    chat_width = width - sidebar_width
    input_height = 3
    chat_height = height - input_height

    # Create windows
    chat_win = curses.newwin(chat_height, chat_width, 0, 0)
    sidebar_win = curses.newwin(chat_height, sidebar_width, 0, chat_width)
    input_win = curses.newwin(input_height, width, chat_height, 0)

    # Apply default background to all windows
    for win in (chat_win, sidebar_win, input_win):
        win.bkgd(" ", default_color)
        win.clear()
        win.box()
        win.refresh()

    messages = []
    input_buffer = ""

    # Input window handles input to avoid clearing other panes
    input_win.keypad(True)
    input_win.nodelay(False)

    while True:
        # Draw chat pane
        chat_win.erase()
        chat_win.box()
        y = 1
        for msg in messages[-(chat_height - 2) :]:
            for line in textwrap.wrap(msg, chat_width - 2):
                if y < chat_height - 1:
                    chat_win.addstr(y, 1, line)
                    y += 1

        # Draw sidebar pane
        sidebar_win.erase()
        sidebar_win.box()

        # Draw input pane
        input_win.erase()
        input_win.box()
        input_win.addstr(1, 1, "> " + input_buffer[: width - 3])

        # Refresh all panes
        chat_win.noutrefresh()
        sidebar_win.noutrefresh()
        input_win.noutrefresh()
        curses.doupdate()

        # Read input from input_win, not stdscr
        key = input_win.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            messages.append(input_buffer)
            input_buffer = ""
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            input_buffer = input_buffer[:-1]
        elif key == 27:  # ESC to exit
            break
        elif 32 <= key < 256:
            input_buffer += chr(key)
