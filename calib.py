import astropy.units as u
from astroquery.nist import Nist
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import tkinter.ttk as ttk
from typing import Sequence, Union, Dict
from config import config
import tkutil
from util import find_input_files


@dataclass
class CalibConfig:
    calib: Path
    input_files: Sequence[Path]
    calib_lines: Sequence[Dict]


def _retrieve_lines(name: str, lower: Union[None, int], higher: Union[None, int]) -> Union[None, Sequence[Dict]]:
    lines = [x.strip() for x in name.split(',')]
    # noinspection PyBroadException
    try:
        result = []
        for line in lines:
            line_src = config.get_calib_table(line)
            if line_src is None:
                line_src = Nist.query(3000 * u.AA, 8500 * u.AA, linename=line)
                config.save_calib_table(line, line_src)
            for row in line_src.iterrows('Observed', 'Rel.'):
                try:
                    observed = row[0]
                    if str(observed) == '--':
                        continue
                    rel = int(row[1])
                    if rel < 10:
                        continue
                    if lower is not None and observed < lower:
                        continue
                    if higher is not None and observed > higher:
                        continue
                    result.append({'lam': observed, 'rel': rel, 'name': line})
                except ValueError:
                    continue
        result.sort(key=lambda x: x['lam'])
        return result
    except Exception:
        return None


def _is_integer(action, key):
    if action == '0':
        return True
    return key.isdigit()


class CalibConfigurator(tk.Toplevel):
    _last_input_dir = Path.home()

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.title('Calibration Configuration')

        top = ttk.Frame(self, relief=tk.RAISED)
        top.pack(side=tk.TOP, fill=tk.BOTH)

        entry_w = 40
        x_pad = 10
        y_pad = 10

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

        calib_label = ttk.Label(top, text='Calibration:')
        calib_label.grid(row=1, column=0, padx=(x_pad, x_pad),
                         pady=(y_pad, 0), sticky=tk.W)
        self._calib_basename = tk.StringVar(top)
        calib_entry = ttk.Entry(top, width=entry_w, textvariable=self._calib_basename,
                                takefocus=True)
        calib_entry.grid(row=1, column=1, padx=(x_pad, x_pad),
                         pady=(y_pad, 0), sticky=tk.W)

        pgm_label = ttk.Label(top, text='Program Basename:')
        pgm_label.grid(row=2, column=0, padx=(x_pad, x_pad),
                       pady=(y_pad, 0), sticky=tk.W)
        self._pgm_basename = tk.StringVar(top)
        pgm_entry = ttk.Entry(top, width=entry_w, textvariable=self._pgm_basename,
                              takefocus=True)
        pgm_entry.grid(row=2, column=1, padx=(x_pad, x_pad),
                       pady=(y_pad, 0), sticky=tk.W)

        lines_label = ttk.Label(top, text='Calibration Lines:')
        lines_label.grid(row=3, column=0, padx=(x_pad, x_pad),
                         pady=(y_pad, 0), sticky=tk.W)
        self._line_name = tk.StringVar(top)
        line_names = config.get_calib_line_names()
        if len(line_names) < 2:
            line_name_ctl = ttk.Entry(top, width=entry_w, textvariable=self._line_name,
                                      takefocus=True)
        else:
            line_name_ctl = ttk.Combobox(top, width=entry_w, textvariable=self._line_name,
                                         values=line_names, takefocus=True)
        line_name_ctl.grid(row=3, column=1, padx=(x_pad, x_pad),
                           pady=(y_pad, 0), sticky=tk.W)

        val_reg = self.register(_is_integer)
        val_cmd = (val_reg, '%d', '%S')

        range_label = ttk.Label(top, text='Range [' + u'\u00C5' + ']')
        range_label.grid(row=4, column=0, padx=(x_pad, x_pad),
                         pady=(y_pad, 2*y_pad), sticky=tk.W)
        range_frame = ttk.Frame(top)
        self._range_low = tk.StringVar(top)
        self._range_high = tk.StringVar(top)
        r_low_entry = ttk.Entry(range_frame, width=5, textvariable=self._range_low,
                                takefocus=True, validate='key', validatecommand=val_cmd)
        r_low_entry.pack(side=tk.LEFT)
        r_spacer = ttk.Label(range_frame, text='-')
        r_spacer.pack(side=tk.LEFT, padx=10)
        r_high_entry = ttk.Entry(range_frame, width=5, textvariable=self._range_high,
                                 takefocus=True, validate='key', validatecommand=val_cmd)
        r_high_entry.pack(side=tk.LEFT)
        range_frame.grid(row=4, column=1, padx=(x_pad, x_pad),
                         pady=(y_pad, 2*y_pad), sticky=tk.W)

        bottom = ttk.Frame(self, relief=tk.RAISED)
        bottom.pack(side=tk.TOP, fill=tk.BOTH)

        ok_button = ttk.Button(bottom, text='OK', command=self._on_ok)
        ok_button.pack(pady=y_pad, expand=True, side=tk.LEFT)
        cancel_button = ttk.Button(bottom, text='Cancel', command=self._on_cancel)
        cancel_button.pack(pady=y_pad, expand=True, side=tk.LEFT)

        tkutil.center_on_parent(parent, self)

        self._status = tk.IntVar(bottom)
        self._status.set(-1)
        self._calib_config = None

    def _get_input_dir(self) -> Union[str, None]:
        initial_dir = CalibConfigurator._last_input_dir
        raw_result = fd.askdirectory(parent=self, initialdir=initial_dir, mustexist=True)
        if not raw_result:
            return
        CalibConfigurator._last_input_dir = Path(raw_result)
        if raw_result.startswith(str(Path.home())):
            raw_result = raw_result.replace(str(Path.home()), '~')
        self._input_dir.set(raw_result)
        return raw_result

    def _on_ok(self):
        raw_input_dir = self._input_dir.get()
        if raw_input_dir is None or raw_input_dir.strip() == '':
            return
        calib_basename = self._calib_basename.get()
        if calib_basename is None or calib_basename.strip() == '':
            return
        line_name = self._line_name.get()
        if line_name is None or line_name.strip() == '':
            return

        self.wm_withdraw()
        raw_input_dir = raw_input_dir.replace('~', str(Path.home()))
        input_dir = Path(raw_input_dir)
        if not input_dir.exists():
            mb.showerror(title='Calibration Configuration', message='Input directory does not exist.',
                         master=self)
            self.wm_deiconify()
            return

        calib_file = find_input_files(input_dir, calib_basename)
        if len(calib_file) == 0:
            mb.showerror(title='Calibration Configuration', message='Calibration file does not exist.',
                         master=self)
            self.wm_deiconify()
            return
        elif len(calib_file) > 1:
            mb.showerror(title='Calibration Configuration', message='Calibration file not unique.',
                         master=self)
            self.wm_deiconify()
            return

        # Allow empty program basename in order to cater for calibration of
        # just a reference spectrum.
        pgm_basename = self._pgm_basename.get()
        if pgm_basename is None or pgm_basename.strip() == '':
            pgm_files = tuple()
        else:
            pgm_files = find_input_files(input_dir, pgm_basename)
            if len(pgm_files) == 0:
                mb.showerror(title='Calibration Configuration', message='Program file not found.',
                             master=self)
                self.wm_deiconify()
                return
        line_names = self._line_name.get()
        raw_lower = self._range_low.get().strip()
        if raw_lower != '':
            lower = int(raw_lower)
        else:
            lower = None
        raw_higher = self._range_high.get().strip()
        if raw_higher != '':
            higher = int(raw_higher)
        else:
            higher = None
        if higher is not None and lower is not None and higher <= lower:
            mb.showerror(title='Calibration Configuration', message='Higher range <= lower range.',
                         master=self)
            self.wm_deiconify()
            return

        lines = _retrieve_lines(line_names, lower, higher)
        if lines is None:
            mb.showerror(title='Calibration Configuration', message='Error in calibration line name.',
                         master=self)
            self.wm_deiconify()
            return
        self._calib_config = CalibConfig(calib_file[0], pgm_files, lines)
        self._status.set(1)

    def _on_cancel(self):
        self.wm_withdraw()
        self._status.set(0)

    def get_config(self) -> Union[None, CalibConfig]:
        self.wait_variable(self._status)
        if self._status.get():
            result = self._calib_config
        else:
            result = None
        self.destroy()
        return result


def _get_calibration_config(parent: Union[tk.Tk, tk.Toplevel]) -> Union[None, CalibConfig]:
    configurator = CalibConfigurator(parent)
    return configurator.get_config()


if __name__ == '__main__':
    main = tk.Tk()
    main.eval('tk::PlaceWindow . center')

    def print_cfg():
        c_config = _get_calibration_config(main)
        print(c_config)

    but = ttk.Button(main, text='Config', command=print_cfg)
    but.pack(side=tk.TOP, expand=True)

    tk.mainloop()


