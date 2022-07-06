from astropy.io import fits
from functools import partial
import numpy as np
import numpy.typing as npt
from os import PathLike
from pathlib import Path
import queue
import tkinter as tk
from tkinter import ttk
import tkinter.messagebox as mb
from typing import Union, Any
import bgexec
import tkutil


def _do_combine_bg(in_dir: Union[str, bytes, PathLike], in_basename: str, out_dir: Union[str, bytes, PathLike],
                   out_name: str, mode: str):
    in_path = Path(in_dir)
    input_files = []
    for candidate in in_path.glob(in_basename + '*.*'):
        if candidate.is_file() and candidate.suffix in ('.fits', '.fit'):
            input_files.append(candidate)
    input_data: Union[None, npt.NDArray[Any]] = None
    header = None
    data_idx = 0
    in_type = None
    for input_file in input_files:
        in_hdu_l = fits.open(input_file)
        data: npt.NDArray[Any] = in_hdu_l[0].data
        if input_data is None:
            header = in_hdu_l[0].header
            num_files = len(input_files)
            input_data = np.empty((num_files, data.shape[0], data.shape[1]), data.dtype)
            header['HISTORY'] = f'Combined {num_files} files.'
            in_type = data.dtype
        input_data[data_idx, :, :] = data
        in_hdu_l.close()
        data_idx = data_idx + 1
    if mode == 'median':
        output_data = np.median(input_data, axis=0)
    else:
        output_data = np.mean(input_data, axis=0)
    out_hdu = fits.PrimaryHDU(output_data.astype(in_type), header)
    out_name_full = out_name
    if not out_name_full.endswith('.fit') and not out_name_full.endswith('.fits'):
        out_name_full = out_name_full + input_files[0].suffix
    out_path = Path(out_dir) / out_name_full
    out_hdu.writeto(out_path, overwrite=True)
    return f'Combined {len(input_files)} images.'


class Combine(tk.Toplevel):
    _methods = ['average', 'median']

    def __init__(self, parent):
        super().__init__(parent)
        super().title('Combine Images')

        self._master = parent.winfo_toplevel()

        xpad = 10
        ypad = 10
        top = ttk.Frame(self, relief=tk.RAISED)
        top.pack(side=tk.TOP, fill=tk.BOTH, ipadx=xpad, ipady=ypad)

        in_dir_label = ttk.Label(top, text='Input Directory:')
        in_dir_label.grid(row=0, column=0, padx=(xpad, xpad), pady=(2 * ypad, 0), sticky=tk.W)
        self._in_dir = tk.StringVar(top, '')
        in_dir_entry = ttk.Entry(top, width=40, textvariable=self._in_dir, takefocus=True)
        in_dir_entry.grid(row=0, column=1, padx=(xpad, xpad), pady=(2 * ypad, 0), sticky=tk.W)
        self._folder_icon = tkutil.load_icon(top, 'folder')
        in_dir_btn = ttk.Button(top, image=self._folder_icon, command=self._select_in_dir)
        in_dir_btn.grid(row=0, column=2, padx=(0, 0), pady=(2 * ypad, 0), sticky=tk.W)

        base_name_label = ttk.Label(top, text='Image Basename:')
        base_name_label.grid(row=1, column=0, padx=(xpad, xpad), pady=(ypad, 0), sticky=tk.W)
        self._in_base_name = tk.StringVar(top, '')
        in_base_name_entry = ttk.Entry(top, width=40, textvariable=self._in_base_name,
                                       takefocus=True)
        in_base_name_entry.grid(row=1, column=1, padx=(xpad, xpad), pady=(ypad, 0), sticky=tk.W)

        out_dir_label = ttk.Label(top, text='Output Directory:')
        out_dir_label.grid(row=2, column=0, padx=(xpad, xpad), pady=(ypad, 0), sticky=tk.W)
        self._out_dir = tk.StringVar(top, '')
        out_dir_entry = ttk.Entry(top, width=40, textvariable=self._out_dir,
                                  takefocus=True)
        out_dir_entry.grid(row=2, column=1, padx=(xpad, xpad), pady=(ypad, 0), sticky=tk.W)
        out_dir_btn = ttk.Button(top, image=self._folder_icon, command=self._select_out_dir)
        out_dir_btn.grid(row=2, column=2, padx=(0, 0), pady=(ypad, 0), sticky=tk.W)

        out_name_label = ttk.Label(top, text='Output Name:')
        out_name_label.grid(row=3, column=0, padx=(xpad, xpad), pady=(ypad, 0), sticky=tk.W)
        self._out_name = tk.StringVar(top, '')
        out_name_entry = ttk.Entry(top, width=40, textvariable=self._out_name,
                                   takefocus=True)
        out_name_entry.grid(row=3, column=1, padx=(xpad, xpad), pady=(ypad, 0), sticky=tk.W)

        method_label = ttk.Label(top, text='Method:')
        method_label.grid(row=4, column=0, padx=(xpad, xpad), pady=(ypad, 2 * ypad), sticky=tk.W)
        self._method = tk.StringVar(top, Combine._methods[0])
        method_combo = ttk.Combobox(top, textvariable=self._method,
                                    values=Combine._methods, state='readonly',
                                    width=8, takefocus=True)
        method_combo.grid(row=4, column=1, padx=(xpad, xpad), pady=(ypad, 2 * ypad), sticky=tk.W)

        bottom = ttk.Frame(self, relief=tk.RAISED)
        bottom.pack(fill=tk.BOTH, side=tk.TOP, ipadx=20, ipady=20)
        ok_button = ttk.Button(bottom, text='OK', command=self._do_combine)
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

    def _do_combine(self):
        in_dir = self._in_dir.get().strip()
        in_basename = self._in_base_name.get().strip()
        out_dir = self._out_dir.get().strip()
        out_name = self._out_name.get().strip()
        if not in_dir or not in_basename or not out_dir or not out_name:
            return

        mode = self._method.get()
        tkutil.state_all(self, tk.DISABLED)
        self.configure(cursor='watch')

        in_dir = in_dir.replace('~', str(Path.home()))
        out_dir = out_dir.replace('~', str(Path.home()))

        if not list(Path(in_dir).glob(in_basename + '*.fits'))\
                and not list(Path(in_dir).glob(in_basename + '*.fit')):
            mb.showerror(master=self, message='No matching input files found.')
            self.configure(cursor='arrow')
            tkutil.state_all(self, tk.NORMAL)
            return

        out_path = Path(out_dir)
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as err:
            mb.showerror(master=self, message=f'Cannot create output dir: {err}.')
            self.configure(cursor='arrow')
            tkutil.state_all(self, tk.NORMAL)
            return

        run_bg = partial(_do_combine_bg, in_dir, in_basename, out_dir, out_name, mode)
        self._queue = queue.Queue()
        self._bg_exec = bgexec.BgExec(run_bg, self._queue)
        self._bg_exec.start()
        self._check_progress()

    def _on_success(self, result: str):
        self.wm_withdraw()
        mb.showinfo(master=self._master, message=result)
        self.destroy()

    def _on_error(self, error_msg: str):
        mb.showerror(master=self, message=error_msg)
        self.configure(cursor='arrow')
        tkutil.state_all(self, tk.NORMAL)

    def _check_progress(self):
        if self._bg_exec.is_alive():
            self._master.after(100, self._check_progress)
        else:
            evt: bgexec.Event = self._queue.get()
            if evt.evt_type == bgexec.FINISHED:
                self._on_success(str(evt.client_data))
            else:
                self._on_error(str(evt.client_data))
