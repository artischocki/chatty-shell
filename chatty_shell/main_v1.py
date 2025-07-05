import curses
from chatty_shell.frontend.presenter import presenter


if __name__ == "__main__":
    curses.wrapper(presenter)
