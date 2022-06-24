import tkinter as tk
import tkinter.ttk as ttk
import tkutil


class Progress(tk.Toplevel):
    def __init__(self, parent: (tk.Tk, tk.Toplevel), title: str):
        super().__init__(parent)
        self.title(title)
        top = ttk.Frame(self, relief=tk.RAISED)
        top.pack(side=tk.TOP, fill=tk.BOTH)
        self._progress = ttk.Progressbar(top, orient=tk.HORIZONTAL,
                                         mode='indeterminate', length=250)
        self._progress.pack(side=tk.TOP, fill=tk.X,
                            ipadx=20, ipady=40)
        self._text = tk.StringVar(top)
        self._text.set('')
        label = ttk.Label(top, textvariable=self._text)
        label.pack(side=tk.TOP, fill=tk.BOTH, ipadx=20, ipady=20, expand=True)

        bottom = ttk.Frame(self, relief=tk.RAISED)
        bottom.pack(side=tk.TOP, fill=tk.BOTH)
        button = ttk.Button(bottom, text="Cancel", command=self._cancel)
        button.pack(side=tk.LEFT, expand=True, pady=20)
        self._cancelled = False

        tkutil.center_on_parent(parent, self)

    def _cancel(self):
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def message(self, message: str) -> None:
        self._text.set(message)

    def start(self):
        self._progress.start()

