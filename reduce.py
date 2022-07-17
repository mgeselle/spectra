from pathlib import Path
from queue import Queue
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import tkinter.ttk as ttk
import tkutil
from typing import Union
import bgexec
from config import config
from dark import Dark
from extract import optimal as ex_optimal
from extract import simple as ex_simple
from flat import Flat
from progress import Progress
from rotate import Rotate
from slant import Slant


def _reduce(input_dir: str, master_dir: Union[str, None], output_dir: Union[str, None],
            bias_basename: str, dark_basename: str, flat_basename: str,
            calibration: str, program: str, cfg_name: str,
            status_queue: Queue, progress: Progress):

    event = bgexec.Event(bgexec.INFO, 'Applying dark correction.')
    status_queue.put(event)

    def callback(msg: str):
        evt = bgexec.Event(bgexec.INFO, msg)
        status_queue.put(evt)

    cumul_pfx = ''
    if not progress.is_cancelled():
        dark_prefix = 'drk-'
        dark = Dark(master_dir, bias_basename, dark_basename)
        input_names = [calibration, program]
        if flat_basename is not None and flat_basename.strip() != '':
            input_names.append(flat_basename)
        dark.correct(input_dir, input_names, output_dir, dark_prefix, callback)
        cumul_pfx = dark_prefix

    if not progress.is_cancelled():
        rot_prefix = 'rot-'
        rot = Rotate(output_dir, cumul_pfx + program)
        input_names = [cumul_pfx + calibration,
                       cumul_pfx + program]
        if flat_basename is not None:
            input_names.append(cumul_pfx + flat_basename)
        rot.rotate(output_dir, input_names, output_dir, rot_prefix)
        cumul_pfx = rot_prefix + cumul_pfx

    if not progress.is_cancelled() and flat_basename is not None and flat_basename.strip() != '':
        flt = Flat(progress, output_dir, cumul_pfx + flat_basename)
        input_names = [cumul_pfx + calibration, cumul_pfx + program]
        flat_prefix = 'flt-'
        flt.apply(input_names, prefix=flat_prefix)
        flt.destroy()
        cumul_pfx = flat_prefix + cumul_pfx

    if not progress.is_cancelled():
        slt = Slant(output_dir, cumul_pfx + calibration)
        input_names = [cumul_pfx + calibration, cumul_pfx + program]
        slant_prefix = 'slt-'
        slt.apply(input_names, prefix=slant_prefix)
        cumul_pfx = slant_prefix + cumul_pfx

    if not progress.is_cancelled():
        d_low, d_high = ex_optimal(output_dir, cumul_pfx + program, cfg_name, output_dir, 'p1d-', callback)
        ex_simple(output_dir, cumul_pfx + calibration, (d_low, d_high), output_dir, 'c1d-')

    event = bgexec.Event(bgexec.FINISHED, 'Data reduction complete.')
    status_queue.put(event)


class Reduce(tk.Toplevel):
    _last_dir_selected = Path.home()
    _last_input_dir = None
    _last_master_dir = None
    _last_output_dir = None

    def __init__(self, parent: Union[tk.Tk, tk.Toplevel]):
        super().__init__(parent)
        self.title('Reduce Images')

        self._master = parent

        x_pad = 10
        y_pad = 10
        entry_w = 40

        top = ttk.Frame(self, relief=tk.RAISED)
        top.pack(side=tk.TOP, fill=tk.BOTH, ipadx=x_pad, ipady=y_pad)

        input_dir_label = ttk.Label(top, text='Input Directory:')
        input_dir_label.grid(row=0, column=0, padx=(x_pad, x_pad),
                             pady=(2*y_pad, 0), sticky=tk.W)
        self._input_dir = tk.StringVar(top)
        input_dir = ttk.Entry(top, width=entry_w, textvariable=self._input_dir,
                              takefocus=True)
        input_dir.grid(row=0, column=1, padx=(x_pad, x_pad),
                       pady=(2*y_pad, 0), sticky=tk.W)
        self._folder_icon = tkutil.load_icon(top, 'folder')
        get_input_folder = ttk.Button(top, image=self._folder_icon,
                                      command=self._get_input_dir)
        get_input_folder.grid(row=0, column=2, padx=(0, x_pad),
                              pady=(2*y_pad, 0), sticky=tk.W)

        master_dir_label = ttk.Label(top, text='Master Directory:')
        master_dir_label.grid(row=1, column=0, padx=(x_pad, x_pad),
                              pady=(y_pad, 0), sticky=tk.W)
        self._master_dir = tk.StringVar(top)
        master_dir = ttk.Entry(top, width=entry_w, textvariable=self._master_dir,
                               takefocus=True)
        master_dir.grid(row=1, column=1, padx=(x_pad, x_pad),
                        pady=(y_pad, 0), sticky=tk.W)
        get_master_folder = ttk.Button(top, image=self._folder_icon,
                                       command=self._get_master_dir)
        get_master_folder.grid(row=1, column=2, padx=(0, x_pad),
                               pady=(y_pad, 0), sticky=tk.W)

        output_dir_label = ttk.Label(top, text='Output Directory:')
        output_dir_label.grid(row=2, column=0, padx=(x_pad, x_pad),
                              pady=(y_pad, 0), sticky=tk.W)
        self._output_dir = tk.StringVar(top)
        output_dir = ttk.Entry(top, width=entry_w, textvariable=self._output_dir,
                               takefocus=True)
        output_dir.grid(row=2, column=1, padx=(x_pad, x_pad),
                        pady=(y_pad, 0), sticky=tk.W)
        get_output_folder = ttk.Button(top, image=self._folder_icon,
                                       command=self._get_output_dir)
        get_output_folder.grid(row=2, column=2, padx=(0, x_pad),
                               pady=(y_pad, 0), sticky=tk.W)

        bias_label = ttk.Label(top, text='Bias:')
        bias_label.grid(row=3, column=0, padx=(x_pad, x_pad),
                        pady=(y_pad, 0), sticky=tk.W)
        self._bias_basename = tk.StringVar(top)
        bias_entry = ttk.Entry(top, width=entry_w, textvariable=self._bias_basename,
                               takefocus=True)
        bias_entry.grid(row=3, column=1, padx=(x_pad, x_pad),
                        pady=(y_pad, 0), sticky=tk.W)

        dark_label = ttk.Label(top, text='Dark Basename:')
        dark_label.grid(row=4, column=0, padx=(x_pad, x_pad),
                        pady=(y_pad, 0), sticky=tk.W)
        self._dark_basename = tk.StringVar(top)
        dark_entry = ttk.Entry(top, width=entry_w, textvariable=self._dark_basename,
                               takefocus=True)
        dark_entry.grid(row=4, column=1, padx=(x_pad, x_pad),
                        pady=(y_pad, 0), sticky=tk.W)

        flat_label = ttk.Label(top, text='Flat:')
        flat_label.grid(row=5, column=0, padx=(x_pad, x_pad),
                        pady=(y_pad, 0), sticky=tk.W)
        self._flat_basename = tk.StringVar(top)
        flat_entry = ttk.Entry(top, width=entry_w, textvariable=self._flat_basename,
                               takefocus=True)
        flat_entry.grid(row=5, column=1, padx=(x_pad, x_pad),
                        pady=(y_pad, 0), sticky=tk.W)

        calib_label = ttk.Label(top, text='Calibration:')
        calib_label.grid(row=6, column=0, padx=(x_pad, x_pad),
                         pady=(y_pad, 0), sticky=tk.W)
        self._calib_basename = tk.StringVar(top)
        calib_entry = ttk.Entry(top, width=entry_w, textvariable=self._calib_basename,
                                takefocus=True)
        calib_entry.grid(row=6, column=1, padx=(x_pad, x_pad),
                         pady=(y_pad, 0), sticky=tk.W)

        pgm_label = ttk.Label(top, text='Program Basename:')
        pgm_label.grid(row=7, column=0, padx=(x_pad, x_pad),
                       pady=(y_pad, 0), sticky=tk.W)
        self._pgm_basename = tk.StringVar(top)
        pgm_entry = ttk.Entry(top, width=entry_w, textvariable=self._pgm_basename,
                              takefocus=True)
        pgm_entry.grid(row=7, column=1, padx=(x_pad, x_pad),
                       pady=(y_pad, 0), sticky=tk.W)

        cam_cfg_label = ttk.Label(top, text='Camera Configuration:')
        cam_cfg_label.grid(row=8, column=0, padx=(x_pad, x_pad),
                           pady=(y_pad, 0), sticky=tk.W)
        self._cam_cfg_name = tk.StringVar(top)
        cam_cfg_combo = ttk.Combobox(top, width=30, state='readonly',
                                     textvariable=self._cam_cfg_name, values=config.get_camera_configs())
        cam_cfg_combo.grid(row=8, column=1, padx=(x_pad, x_pad),
                           pady=(y_pad, 0), sticky=tk.W)

        bottom = ttk.Frame(self, relief=tk.RAISED)
        bottom.pack(side=tk.TOP, fill=tk.BOTH, ipadx=x_pad, ipady=y_pad)
        ok_button = ttk.Button(bottom, text='OK', command=self._do_reduce)
        ok_button.pack(side=tk.LEFT, expand=True)
        cancel_button = ttk.Button(bottom, text='Cancel', command=self.destroy)
        cancel_button.pack(side=tk.LEFT, expand=True)

        tkutil.center_on_parent(parent, self)

    def _get_input_dir(self) -> None:
        in_dir = self._get_folder(Reduce._last_input_dir, True)
        if in_dir is not None:
            self._input_dir.set(in_dir)
            Reduce._last_input_dir = in_dir

    def _get_output_dir(self) -> None:
        out_dir = self._get_folder(Reduce._last_output_dir, False)
        if out_dir is not None:
            self._output_dir.set(out_dir)
            Reduce._last_output_dir = out_dir

    def _get_master_dir(self) -> None:
        mst_dir = self._get_folder(Reduce._last_master_dir, True)
        if mst_dir is not None:
            self._master_dir.set(mst_dir)
            Reduce._last_master_dir = mst_dir

    def _get_folder(self, initialdir: Union[str, Path, None], mustexist: bool) -> Union[str, None]:
        if initialdir is None:
            initialdir = Reduce._last_dir_selected
        raw_result = fd.askdirectory(parent=self, initialdir=initialdir, mustexist=mustexist)
        if not raw_result:
            return
        Reduce._last_dir_selected = Path(raw_result)
        if raw_result.startswith(str(Path.home())):
            raw_result = raw_result.replace(str(Path.home()), '~')

        return raw_result

    def _do_reduce(self) -> None:
        input_dir = self._input_dir.get()
        if not input_dir:
            return
        home_dir = str(Path.home())
        input_dir = input_dir.replace('~', home_dir)
        output_dir = self._output_dir.get()
        if not output_dir:
            return
        output_dir = output_dir.replace('~', home_dir)
        master_dir = self._master_dir.get()
        if not master_dir:
            master_dir = input_dir
        else:
            master_dir = master_dir.replace('~', home_dir)
        bias_name = self._bias_basename.get()
        dark_name = self._dark_basename.get()
        flat_name = self._flat_basename.get()
        pgm_basename = self._pgm_basename.get()
        if not pgm_basename:
            return
        calib_name = self._calib_basename.get()
        if not calib_name:
            return

        self.withdraw()

        out_path = Path(output_dir)
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as err:
            mb.showerror(master=self, message=f'Cannot create output dir: {err}.')
            self.deiconify()
            return

        status_queue = Queue()
        progress = Progress(self._master, 'Reducing Images')

        def run_reduce():
            _reduce(input_dir=input_dir, master_dir=master_dir, output_dir=output_dir,
                    bias_basename=bias_name, dark_basename=dark_name,
                    flat_basename=flat_name, calibration=calib_name, program=pgm_basename,
                    cfg_name=self._cam_cfg_name.get(),
                    status_queue=status_queue, progress=progress)

        bg_exec = bgexec.BgExec(run_reduce, status_queue)
        progress.start()
        bg_exec.start()
        self._check_progress(bg_exec, status_queue, progress)

    def _check_progress(self, bg_exec: bgexec.BgExec, status_queue: Queue, progress: Progress):
        while not status_queue.empty():
            event = status_queue.get()
            if event.evt_type == bgexec.INFO:
                progress.message(str(event.client_data))
            elif event.evt_type == bgexec.ERROR:
                progress.destroy()
                mb.showerror(master=self, message=str(event.client_data))
                self.deiconify()
                return
            else:
                progress.destroy()
                mb.showinfo(master=self, message=str(event.client_data))
                self.destroy()
                return
        if bg_exec.is_alive():

            def check_progress():
                self._check_progress(bg_exec, status_queue, progress)

            self._master.after(100, check_progress)
