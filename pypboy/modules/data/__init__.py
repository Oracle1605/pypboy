from pypboy import BaseModule
from pypboy.modules.data import quests
from pypboy.modules.data import misc
from pypboy.modules.data import holotape_processor
import settings
import os


# logging helpers -----------------------------------------------------------

def _get_logs_dir():
    """Return the path to the data/logs directory, creating it if needed."""
    base = os.path.dirname(__file__)
    logs_dir = os.path.join(base, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def write_log(filename: str, content: str) -> None:
    """Append *content* to *filename* under the logs directory.

    The file is created if it does not already exist.  A newline is added at
    the end of the written content.
    """
    path = os.path.join(_get_logs_dir(), filename)
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")


def print_logs() -> None:
    """Print the contents of all files in the logs directory.

    Each file is preceded by a header showing its name.  If no logs are
    present the function simply returns without error.
    """
    logs_dir = _get_logs_dir()
    for fname in sorted(os.listdir(logs_dir)):
        path = os.path.join(logs_dir, fname)
        if os.path.isfile(path):
            print(f"=== {fname} ===")
            with open(path, encoding="utf-8") as f:
                print(f.read())


class Module(BaseModule):

    def __init__(self, *args, **kwargs):
        self.submodules = [
            holotape_processor.Module(self),
            quests.Module(self),
            misc.Module(self),
        ]
        super(Module, self).__init__(*args, **kwargs)
        
    def handle_resume(self):
        settings.hide_top_menu = False
        settings.hide_submenu = False
        settings.hide_main_menu = False
        settings.hide_footer = False
        self.active.handle_action("resume")
