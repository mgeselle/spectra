from pathlib import Path
import threading
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.ttk as ttk
from typing import Callable, Any


_last_dir_selected = None


def state_all(root: (tk.Widget, tk.BaseWidget), state: (tk.NORMAL, tk.DISABLED)) -> None:
    for child in root.winfo_children():
        if isinstance(child, ttk.Frame):
            state_all(child, state)
        else:
            # noinspection PyArgumentList
            child.configure(state=state)


class BgExec(threading.Thread):
    def __init__(self, run_func: Callable[[], str], success_func: Callable[[str], Any], error_func: Callable[[str], Any]):
        super().__init__()

        self._run_func = run_func
        self._success_func = success_func
        self._error_func = error_func

    def run(self):
        try:
            result = self._run_func()
            self._success_func(result)
        except Exception as err:
            self._error_func(str(err))


def load_icon(master: (tk.Widget, tk.BaseWidget), name: str) -> tk.PhotoImage:
    res_dir = Path(__file__).parent / 'resources'
    file_name = name
    if not file_name.endswith('.gif'):
        file_name = file_name + '.gif'
    return tk.PhotoImage(master=master, file=res_dir / file_name)


def center_on_parent(parent: (tk.Tk, tk.Toplevel), child: tk.Toplevel) -> None:
    parent.update_idletasks()
    child.resizable(width=False, height=False)

    parent_cx = parent.winfo_x() + parent.winfo_width() / 2
    parent_cy = parent.winfo_y() + parent.winfo_height() / 2

    w = child.winfo_width()
    h = child.winfo_height()
    x = int(parent_cx - w / 2)
    y = int(parent_cy - h / 2)
    child.geometry(f'{w:<d}x{h:<d}+{x:<d}+{y:<d}')


def select_dir(parent: (tk.Tk, tk.Toplevel), must_exist: bool = False) -> (str, None):
    global _last_dir_selected
    if _last_dir_selected is None:
        init_dir = Path.home()
    else:
        init_dir = str(_last_dir_selected).replace('~', str(Path.home()))
    raw_result = fd.askdirectory(parent=parent, initialdir=init_dir, mustexist=must_exist)
    if not raw_result:
        return
    if raw_result.startswith(str(Path.home())):
        raw_result = raw_result.replace(str(Path.home()), '~')
    _last_dir_selected = raw_result
    return raw_result


def dir_to_path(in_dir: str) -> (Path, None):
    if in_dir is None:
        return None
    in_dir_l = in_dir.replace('~', str(Path.home()))
    return Path(in_dir_l)

