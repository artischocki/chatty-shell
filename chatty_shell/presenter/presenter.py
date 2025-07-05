from multiprocessing import Process, Queue
from chatty_shell.frontend.view import View
from chatty_shell.backend.model import Model


class Presenter:
    def __init__(self):
        # 1) Create two queues for IPC
        self.human_queue = Queue()
        self.ai_queue = Queue()

        # 2) Start the View in a separate process
        self.view = View(human_queue=self.human_queue, ai_queue=self.ai_queue)
        self.view_proc = Process(target=self.view.run, daemon=True)
        self.view_proc.start()

        # 3) Init your Model in this (main) process
        self.model = Model()

    def run(self):
        while True:
            # block until the user types something
            human_msg = self.human_queue.get()
            # run it through model
            sorted_calls, ai_msg = self.model.new_message(human_msg)
            # send the AI’s answer back to the View
            self.ai_queue.put((sorted_calls, ai_msg))
