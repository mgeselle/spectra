from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
import tkinter.ttk as ttk
from typing import List, Union

from tkutil import center_on_parent


@dataclass
class CameraConfig:
    ron: float
    gain: float


class Config:
    def __init__(self):
        self._ini_file = Path.home() / '.spectra' / 'spectra.ini'
        self._config = ConfigParser()
        if self._ini_file.exists():
            self._config.read(self._ini_file)

    def get_camera_configs(self) -> List[str]:
        return [x[4:] for x in self._config.sections() if x.startswith('CAM:')]

    def get_camera_config(self, name: str) -> Union[None, CameraConfig]:
        section = 'CAM:' + name
        if not self._config.has_section(section):
            return None
        ron = self._config.getfloat(section, 'ron')
        gain = self._config.getfloat(section, 'gain')
        return CameraConfig(ron, gain)

    def save_camera_config(self, name: str, cfg: CameraConfig):
        section = 'CAM:' + name
        if not self._config.has_section(section):
            self._config[section] = {}
        self._config[section]['ron'] = str(cfg.ron)
        self._config[section]['gain'] = str(cfg.gain)
        if not self._ini_file.parent.exists():
            self._ini_file.parent.mkdir(parents=True)
        with self._ini_file.open('w') as fp:
            self._config.write(fp)

    def delete_camera_config(self, name: str):
        section = 'CAM:' + name
        self._config.pop(name)
        with self._ini_file.open('w') as fp:
            self._config.write(fp)


config = Config()


def _is_valid_float(value_after):
    if value_after == '':
        return True
    try:
        float(value_after)
        return True
    except ValueError:
        return False


class CamCfgGUI(tk.Toplevel):
    def __init__(self, parent: Union[tk.Tk, tk.Toplevel]):
        super().__init__(parent)
        self.title('Camera Configuration')

        pad_x = 20
        pad_y = 10
        top = ttk.Frame(self, relief=tk.RAISED)
        cam_label = ttk.Label(top, text='Name:')
        cam_label.grid(row=0, column=0, sticky=tk.W, padx=pad_x, pady=(2 * pad_y, pad_y))
        self._cam_combo = ttk.Combobox(top, width=30, values=config.get_camera_configs(),
                                       takefocus=True)
        self._cam_combo.bind('<<ComboboxSelected>>', self._combo_evt)
        self._cam_combo.grid(row=0, column=1, sticky=tk.E, padx=pad_x, pady=(2 * pad_y, pad_y))

        ron_label = ttk.Label(top, text='Read-Out Noise [e-]:')
        ron_label.grid(row=1, column=0, sticky=tk.W, padx=pad_x, pady=(pad_y, pad_y))

        c_validate_float = (self.register(_is_valid_float), '%P')
        self._ron = tk.StringVar()
        ron_entry = ttk.Entry(top, width=8, validatecommand=c_validate_float, textvariable=self._ron)
        ron_entry.grid(row=1, column=1, sticky=tk.E, padx=pad_x,  pady=(pad_y, pad_y))

        gain_label = ttk.Label(top, text='Gain [e-/ADU]:')
        gain_label.grid(row=2, column=0, sticky=tk.W, padx=pad_x,  pady=(pad_y, pad_y))
        self._gain = tk.StringVar()
        gain_entry = ttk.Entry(top, width=8, validatecommand=c_validate_float, textvariable=self._gain)
        gain_entry.grid(row=2, column=1, sticky=tk.E, padx=pad_x,  pady=(pad_y, pad_y))

        top.pack(side=tk.TOP, expand=True, fill=tk.BOTH, ipadx=10, ipady=10)

        bottom = ttk.Frame(self, relief=tk.RAISED)
        save_but = ttk.Button(bottom, text='Save', command=self._save)
        save_but.pack(side=tk.LEFT, expand=True)
        del_but = ttk.Button(bottom, text='Delete', command=self._delete)
        del_but.pack(side=tk.LEFT, expand=True)
        cancel_but = ttk.Button(bottom, text='Cancel', command=self.destroy)
        cancel_but.pack(side=tk.LEFT, expand=True)

        bottom.pack(side=tk.TOP, expand=True, fill=tk.BOTH, ipadx=10, ipady=10)

        center_on_parent(parent, self)

    def _combo_evt(self, event):
        entry = self._cam_combo.get()
        cam_cfg = config.get_camera_config(entry)
        self._gain.set(str(cam_cfg.gain))
        self._ron.set(str(cam_cfg.ron))

    def _save(self):
        entry = self._cam_combo.get()
        ron_str = self._ron.get()
        gain_str = self._gain.get()
        if entry == '' or not _is_valid_float(ron_str) or not _is_valid_float(gain_str):
            return
        self.wm_withdraw()
        cfg = CameraConfig(float(ron_str), float(gain_str))
        config.save_camera_config(entry, cfg)
        self.destroy()

    def _delete(self):
        entry = self._cam_combo.get()
        if entry == '':
            return
        self.wm_withdraw()
        config.delete_camera_config(entry)
        self.destroy()

