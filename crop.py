from astropy.io import fits
import queue
from pathlib import Path
from queue import Queue
import tkinter as tk
import tkinter.messagebox as mb
import tkinter.ttk as ttk
from typing import Tuple
from bgexec import BgExec, Event
import bgexec
from progress import Progress
import tkutil


def _is_int(action, key_val):
    if action == '0':
        return True
    else:
        return key_val.isdigit()


def _do_crop(in_dir: Path, out_dir: Path,
             x: Tuple[int, int], y: Tuple[int, int],
             status_queue: Queue, progress: Progress) -> None:
    n_processed = 0
    for in_file in sorted(in_dir.iterdir()):
        if not in_file.is_file() or not (in_file.suffix in ('.fits', '.fit')):
            continue
        if progress.is_cancelled():
            return
        msg = f'Processing {in_file}'
        evt = Event(bgexec.INFO, msg)
        status_queue.put(evt)
        full_out_file = out_dir / in_file.name
        hdu_l = fits.open(in_file)
        header = hdu_l[0].header
        data = hdu_l[0].data
        new_data = data[y[0]:y[1], x[0]:x[1]]
        new_hdu = fits.PrimaryHDU(new_data, header)
        new_hdu.writeto(full_out_file, overwrite=True)
        hdu_l.close()
        n_processed = n_processed + 1

    evt = Event(bgexec.FINISHED, f'Processed {n_processed:<d} file(s).')
    status_queue.put(evt)


class Crop(tk.Toplevel):
    def __init__(self, parent: (tk.Tk, tk.Toplevel)):
        super().__init__(parent)
        self.title('Crop Images')
        self._master = parent

        x_pad = 20
        y_pad = 20
        top = ttk.Frame(self, relief=tk.RAISED)
        top.pack(side=tk.TOP, fill=tk.X, ipadx=x_pad, ipady=y_pad)

        in_dir_label = ttk.Label(top, text='Input Directory:')
        in_dir_label.grid(row=0, column=0, padx=(x_pad, 0), pady=(2 * y_pad, 0), sticky=tk.W)
        self._in_dir = tk.StringVar(top, '')
        in_dir_entry = ttk.Entry(top, width=40, textvariable=self._in_dir, takefocus=True)
        in_dir_entry.grid(row=0, column=1, padx=(x_pad, x_pad), pady=(2 * y_pad, 0), sticky=tk.W)
        self._folder_icon = tkutil.load_icon(top, 'folder')
        in_dir_btn = ttk.Button(top, image=self._folder_icon, command=self._select_in_dir)
        in_dir_btn.grid(row=0, column=2, padx=(0, 0), pady=(2 * y_pad, 0), sticky=tk.W)

        out_dir_label = ttk.Label(top, text='Output Directory:')
        out_dir_label.grid(row=1, column=0, padx=(x_pad, 0), pady=(y_pad, 0), sticky=tk.W)
        self._out_dir = tk.StringVar(top, '')
        out_dir_entry = ttk.Entry(top, width=40, textvariable=self._out_dir,
                                  takefocus=True)
        out_dir_entry.grid(row=1, column=1, padx=(x_pad, x_pad), pady=(y_pad, 0), sticky=tk.W)
        out_dir_btn = ttk.Button(top, image=self._folder_icon, command=self._select_out_dir)
        out_dir_btn.grid(row=1, column=2, padx=(0, 0), pady=(y_pad, 0), sticky=tk.W)

        c_frame = ttk.Frame(top)
        c_frame.grid(row=2, column=0, columnspan=3, sticky=tk.N+tk.E+tk.W, pady=(y_pad, 0))

        c1_label = ttk.Label(c_frame, text='x1, y1')
        c1_label.grid(row=0, column=0, padx=(x_pad, 0), pady=(0, y_pad))
        self._x1 = tk.IntVar()
        c_validate = (self.register(_is_int), '%d', '%P')
        cx1_entry = ttk.Entry(c_frame, width=6, justify=tk.RIGHT,
                              textvariable=self._x1, validate='key', validatecommand=c_validate)
        cx1_entry.grid(row=0, column=1, padx=(x_pad, 0), pady=(0, y_pad),
                       sticky=tk.W)
        self._y1 = tk.IntVar()
        cy1_entry = ttk.Entry(c_frame, width=6, justify=tk.RIGHT,
                              textvariable=self._y1, validate='key', validatecommand=c_validate)
        cy1_entry.grid(row=0, column=2, padx=(x_pad, 0), pady=(0, y_pad),
                       sticky=tk.W)

        c2_label = ttk.Label(c_frame, text='x2, y2')
        c2_label.grid(row=1, column=0, padx=(x_pad, 0))
        self._x2 = tk.IntVar()
        cx2_entry = ttk.Entry(c_frame, width=6, justify=tk.RIGHT,
                              textvariable=self._x2, validate='key', validatecommand=c_validate)
        cx2_entry.grid(row=1, column=1, padx=(x_pad, 0),
                       sticky=tk.W)
        self._y2 = tk.IntVar()
        cy2_entry = ttk.Entry(c_frame, width=6, justify=tk.RIGHT,
                              textvariable=self._y2, validate='key', validatecommand=c_validate)
        cy2_entry.grid(row=1, column=2, padx=(x_pad, 0),
                       sticky=tk.W)

        bottom = ttk.Frame(self, relief=tk.RAISED)
        bottom.pack(fill=tk.BOTH, side=tk.TOP, ipadx=20, ipady=20)
        ok_button = ttk.Button(bottom, text='OK', command=self._crop)
        ok_button.pack(side=tk.LEFT, expand=True)
        cancel_button = ttk.Button(bottom, text='Cancel', command=self.destroy)
        cancel_button.pack(side=tk.LEFT, expand=True)

        tkutil.center_on_parent(parent, self)

        in_dir_entry.focus_set()

    def _select_in_dir(self):
        new_in_dir = tkutil.select_dir(self, True)
        if new_in_dir:
            self._in_dir.set(new_in_dir)

    def _select_out_dir(self):
        new_out_dir = tkutil.select_dir(self, False)
        if new_out_dir:
            self._out_dir.set(new_out_dir)

    def _crop(self):
        in_path = tkutil.dir_to_path(self._in_dir.get())
        if in_path is None or not in_path.exists():
            return
        if not any(in_path.glob('*.fits')) and not any(in_path.glob('*.fit')):
            return
        out_path = tkutil.dir_to_path(self._out_dir.get())
        if out_path is None:
            return

        x1 = self._x1.get()
        x2 = self._x2.get()
        y1 = self._y1.get()
        y2 = self._y2.get()
        if x1 == x2 or y1 == y2:
            return

        self.withdraw()
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as err:
            mb.showerror(master=self._master,
                         message=f'Cannot create output directory: {err}')
            self.deiconify()
            return

        status_queue = queue.Queue()
        progress = Progress(self._master, 'Cropping...')
        x_tup = sorted((x1, x2))
        y_tup = tuple(sorted((y1, y2)))

        def do_crop():
            _do_crop(in_path, out_path,
                     (x_tup[0], x_tup[1]), (y_tup[0], y_tup[1]),
                     status_queue, progress)

        bg_exec = BgExec(do_crop, status_queue)
        progress.start()
        bg_exec.start()
        self._check_progress(bg_exec, status_queue, progress)

    def _check_progress(self, bg_exec: BgExec, status_queue: Queue, progress: Progress):
        while not status_queue.empty():
            event = status_queue.get()
            if event.evt_type == bgexec.ERROR:
                progress.withdraw()
                mb.showerror(master=self._master, message=event.client_data)
                self.destroy()
                return
            elif event.evt_type == bgexec.FINISHED:
                progress.withdraw()
                mb.showinfo(master=self._master, message=event.client_data)
                self.destroy()
                return
            progress.message(str(event.client_data))
        if bg_exec.is_alive():
            def do_check(): self._check_progress(bg_exec, status_queue, progress)
            self._master.after(100, do_check)
