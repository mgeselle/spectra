from astropy.table import Table
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union, Sequence
import wx

import validator
import wxutil


@dataclass
class CameraConfig:
    ron: float
    gain: float


# TODO Use wx.ConfigBase for storing settings.
# TODO Use wx.StandardPaths to determine where to store downloaded files.
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
        self._config.pop(section)
        with self._ini_file.open('w') as fp:
            self._config.write(fp)

    def get_calib_line_names(self) -> Sequence[str]:
        cfg_dir = self._ini_file.parent
        if not cfg_dir.exists():
            return ()
        return [x.stem.replace('_', ' ') for x in cfg_dir.glob('*.fits')]

    def get_calib_table(self, name: str) -> Union[None, Table]:
        file = self._ini_file.parent / (name.replace(' ', '_') + '.fits')
        if file.exists():
            return Table.read(file)
        return None

    def save_calib_table(self, name: str, table: Table):
        ini_dir = self._ini_file.parent
        ini_dir.mkdir(parents=True, exist_ok=True)
        file = ini_dir / (name.replace(' ', '_') + '.fits')
        table.write(file)


config = Config()


class CamCfgGUI(wx.Dialog):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Camera Configuration')

        panel = wx.Panel(self)
        cam_label = wx.StaticText(panel, wx.ID_ANY, 'Name:')
        self._cam_combo = wx.ComboBox(panel, wx.ID_ANY, choices=config.get_camera_configs(),
                                      style=wx.CB_DROPDOWN | wx.CB_SORT)
        wxutil.size_text_by_chars(self._cam_combo, 30)

        ron_label = wx.StaticText(panel, wx.ID_ANY, 'Read-Out Noise [e-]:')
        self._ron_entry = wx.TextCtrl(panel, id=wx.ID_ANY, validator=validator.DecimalValidator())
        wxutil.size_text_by_chars(self._ron_entry, 5)

        gain_label = wx.StaticText(panel, wx.ID_ANY, 'Gain [e-/ADU]:')
        self._gain_entry = wx.TextCtrl(panel, id=wx.ID_ANY, validator=validator.DecimalValidator())
        wxutil.size_text_by_chars(self._gain_entry, 5)

        self._save_btn = wx.Button(panel, id=wx.ID_SAVE)
        self._delete_btn = wx.Button(panel, id=wx.ID_DELETE)
        self._cancel_btn = wx.Button(panel, id=wx.ID_CANCEL)

        grid = wx.FlexGridSizer(rows=3, cols=2, hgap=5, vgap=5)
        grid.Add(cam_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._cam_combo, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(ron_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._ron_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(gain_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._gain_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._save_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._delete_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._cancel_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        # Need to keep a reference to the sizer, because
        # btn_sizer_s doesn't. This will yield a segfault.
        self._btn_sizer = btn_sizer

        btn_sizer_s = self.CreateSeparatedSizer(btn_sizer)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(btn_sizer_s, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.EXPAND, 10)

        panel.SetSizer(vbox)
        panel.Fit()

        sz = panel.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        self.Bind(wx.EVT_COMBOBOX, self._combo_evt)
        self.Bind(wx.EVT_BUTTON, self._save, id=wx.ID_SAVE)
        self.Bind(wx.EVT_BUTTON, self._delete, id=wx.ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self._cancel, id=wx.CANCEL)

    # noinspection PyUnusedLocal
    def _combo_evt(self, event: wx.Event):
        entry = self._cam_combo.GetValue()
        cam_cfg = config.get_camera_config(entry)
        self._gain_entry.SetValue(str(cam_cfg.gain))
        self._ron_entry.SetValue(str(cam_cfg.ron))

    def _save(self, event: wx.CommandEvent):
        if not self.Validate():
            return
        entry = self._cam_combo.GetValue()
        if entry == '':
            return
        ron_str = self._ron_entry.GetValue()
        gain_str = self._gain_entry.GetValue()
        cfg = CameraConfig(float(ron_str), float(gain_str))
        config.save_camera_config(entry, cfg)
        self.EndModal(event.GetId())

    def _delete(self, event: wx.CommandEvent):
        entry = self._cam_combo.GetValue()
        if entry == '':
            return
        config.delete_camera_config(entry)
        self.EndModal(event.GetId())

    def _cancel(self, event: wx.CommandEvent):
        self.EndModal(event.GetId())


if __name__ == '__main__':
    app = wx.App()
    frame = wx.Frame(None, title='Camera Config Test')
    pnl = wx.Panel(frame)
    id_ref = wx.NewIdRef()
    button = wx.Button(pnl, id=id_ref.GetId(), label='Run')
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(button)
    pnl.SetSizer(sizer)
    pnl.Fit()

    # noinspection PyUnusedLocal
    def _on_btn(event):
        with CamCfgGUI(frame) as dlg:
            res = dlg.ShowModal()
            print(f'Dialog ended with {res}')

    frame.Bind(wx.EVT_BUTTON, _on_btn, id=id_ref.GetId())
    frame.Show()
    app.MainLoop()
