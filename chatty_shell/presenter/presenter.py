from multiprocessing import Process, Queue
from chatty_shell.frontend.view import View
from chatty_shell.backend.model import Model
import time
from pathlib import Path
import logging


class Presenter:
    def __init__(self):
        # queues
        self.human_queue = Queue()
        self.ai_queue = Queue()
        self.popup_queue = Queue()
        self.popup_response_queue = Queue()

        # logger
        self.logger = logging.getLogger()
        logging.basicConfig(filename="debug.log", filemode="w", level=logging.DEBUG)

        # start the View with three queues
        self.view = View(
            human_queue=self.human_queue,
            ai_queue=self.ai_queue,
            popup_queue=self.popup_queue,
            popup_response_queue=self.popup_response_queue,
            logger=self.logger,
        )
        self.view_proc = Process(target=self.view.run, daemon=True)
        self.view_proc.start()

        self.model = Model(self.logger)

        # Check if api key set
        if not self.model.api_key_set():
            self.authenticate()

    def authenticate(self):
        popup_message = "🔑 Enter your OpenAI API key: "
        while True:
            if not self.model.api_key_set():
                env_path = Path(__file__).parents[2] / ".env"

                self.popup_queue.put(popup_message)
                while True:
                    time.sleep(0.2)
                    if self.popup_response_queue.empty():
                        continue
                    token = self.popup_response_queue.get()
                    break
                self.model.set_api_key(token)
                try:
                    self.model.new_message("Test Connection...")
                    # raise Exception
                except:
                    self.model.reset_api_key()
                    popup_message = "🔑 Invalid API key, try again: "
                    continue

                with open(env_path, "w") as f:
                    f.write(f"OPENAI_API_KEY={token}")
                break

    def run(self):

        while True:
            # block until the user types something
            human_msg = self.human_queue.get()
            # run it through model
            sorted_calls, ai_msg = self.model.new_message(human_msg)
            # send the AI’s answer back to the View
            self.ai_queue.put((sorted_calls, ai_msg))
