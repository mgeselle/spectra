import astropy.units as u
import wx
import wx.lib.intctrl as wxli

from astropy.coordinates import Latitude, Longitude, EarthLocation
from config import Config, CameraConfig, TelescopeConfig, SpectrometerConfig, AavsoConfig
import validator
import wxutil


class CamCfgGUI(wx.Dialog):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Camera Configuration')

        panel = wx.Panel(self)
        cam_label = wx.StaticText(panel, wx.ID_ANY, 'Name:')
        self._cam_combo = wx.ComboBox(panel, wx.ID_ANY, choices=Config.get().get_camera_configs(),
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
        # btn_sizer_s doesn't. This would yield a segfault otherwise.
        self._btn_sizer = btn_sizer

        btn_sizer_s = self.CreateSeparatedSizer(btn_sizer)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(btn_sizer_s, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        panel.SetSizer(vbox)
        panel.Fit()

        sz = panel.GetBestSize()
        self.SetClientSize(sz)
        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

        self.Bind(wx.EVT_COMBOBOX, self._combo_evt)
        self.Bind(wx.EVT_BUTTON, self._save, id=wx.ID_SAVE)
        self.Bind(wx.EVT_BUTTON, self._delete, id=wx.ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self._cancel, id=wx.CANCEL)

    # noinspection PyUnusedLocal
    def _combo_evt(self, event: wx.Event):
        entry = self._cam_combo.GetValue()
        cam_cfg = Config.get().get_camera_config(entry)
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
        Config.get().save_camera_config(entry, cfg)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _delete(self, event: wx.CommandEvent):
        entry = self._cam_combo.GetValue()
        if entry == '':
            return
        Config.get().delete_camera_config(entry)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _cancel(self, event: wx.CommandEvent):
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)


class TelescopeCfgGui(wx.Dialog):

    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Telescope Configuration')

        panel = wx.Panel(self)
        name_label = wx.StaticText(panel, label='Name:')
        names = Config.get().get_telescope_config_names()
        self._name_combo = wx.ComboBox(panel, choices=names, style=wx.CB_DROPDOWN | wx.CB_SORT)
        wxutil.size_text_by_chars(self._name_combo, 30)

        apt_label = wx.StaticText(panel, label='Aperture [mm]:')
        self._apt_entry = wxli.IntCtrl(panel, min=100)
        wxutil.size_text_by_chars(self._apt_entry, 5)

        fl_label = wx.StaticText(panel, label='Focal Length [mm]:')
        self._fl_entry = wxli.IntCtrl(panel, min=50)
        wxutil.size_text_by_chars(self._fl_entry, 5)

        self._save_btn = wx.Button(panel, id=wx.ID_SAVE)
        self._delete_btn = wx.Button(panel, id=wx.ID_DELETE)
        self._cancel_btn = wx.Button(panel, id=wx.ID_CANCEL)

        grid = wx.FlexGridSizer(rows=3, cols=2, hgap=5, vgap=5)
        grid.Add(name_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._name_combo, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(apt_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._apt_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(fl_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._fl_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._save_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._delete_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._cancel_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        # Need to keep a reference to the sizer, because
        # btn_sizer_s doesn't. This would yield a segfault otherwise.
        self._btn_sizer = btn_sizer

        btn_sizer_s = self.CreateSeparatedSizer(btn_sizer)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(btn_sizer_s, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        self.Bind(wx.EVT_COMBOBOX, self._combo_evt)
        self.Bind(wx.EVT_BUTTON, self._save, id=wx.ID_SAVE)
        self.Bind(wx.EVT_BUTTON, self._delete, id=wx.ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self._cancel, id=wx.CANCEL)

        panel.SetSizer(vbox)
        panel.Fit()

        sz = panel.GetBestSize()
        self.SetClientSize(sz)
        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

    # noinspection PyUnusedLocal
    def _combo_evt(self, event: wx.Event):
        entry = self._name_combo.GetValue()
        tel_cfg = Config.get().get_telescope_config(entry)
        self._apt_entry.SetValue(tel_cfg.aperture)
        self._fl_entry.SetValue(tel_cfg.focal_length)

    def _save(self, event: wx.CommandEvent):
        if not self.Validate():
            return
        entry = self._name_combo.GetValue()
        if entry == '':
            return
        apt = self._apt_entry.GetValue()
        fl = self._fl_entry.GetValue()
        cfg = TelescopeConfig(apt, fl)
        Config.get().save_telescope_config(entry, cfg)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _delete(self, event: wx.CommandEvent):
        entry = self._name_combo.GetValue()
        if entry == '':
            return
        Config.get().delete_telescope_config(entry)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _cancel(self, event: wx.CommandEvent):
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)


class SpectrometerCfgGui(wx.Dialog):

    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Spectrometer Configuration')

        panel = wx.Panel(self)
        name_label = wx.StaticText(panel, label='Name:')
        names = Config.get().get_spectro_config_names()
        self._name_combo = wx.ComboBox(panel, choices=names, style=wx.CB_DROPDOWN | wx.CB_SORT)
        wxutil.size_text_by_chars(self._name_combo, 30)

        type_label = wx.StaticText(panel, label='Type:')
        self._type_entry = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._type_entry, 30)

        lines_label = wx.StaticText(panel, label='Lines/mm:')
        self._lines_entry = wxli.IntCtrl(panel, min=100)
        wxutil.size_text_by_chars(self._lines_entry, 5)

        self._save_btn = wx.Button(panel, id=wx.ID_SAVE)
        self._delete_btn = wx.Button(panel, id=wx.ID_DELETE)
        self._cancel_btn = wx.Button(panel, id=wx.ID_CANCEL)

        grid = wx.FlexGridSizer(rows=3, cols=2, hgap=5, vgap=5)
        grid.Add(name_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._name_combo, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(type_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._type_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(lines_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._lines_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._save_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._delete_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._cancel_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        # Need to keep a reference to the sizer, because
        # btn_sizer_s doesn't. This would yield a segfault otherwise.
        self._btn_sizer = btn_sizer

        btn_sizer_s = self.CreateSeparatedSizer(btn_sizer)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(btn_sizer_s, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        self.Bind(wx.EVT_COMBOBOX, self._combo_evt)
        self.Bind(wx.EVT_BUTTON, self._save, id=wx.ID_SAVE)
        self.Bind(wx.EVT_BUTTON, self._delete, id=wx.ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self._cancel, id=wx.CANCEL)

        panel.SetSizer(vbox)
        panel.Fit()

        sz = panel.GetBestSize()
        self.SetClientSize(sz)
        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

    # noinspection PyUnusedLocal
    def _combo_evt(self, event: wx.Event):
        entry = self._name_combo.GetValue()
        spec_cfg = Config.get().get_spectro_config(entry)
        self._type_entry.SetValue(spec_cfg.type)
        self._lines_entry.SetValue(spec_cfg.lines_mm)

    def _save(self, event: wx.CommandEvent):
        if not self.Validate():
            return
        entry = self._name_combo.GetValue()
        if entry == '':
            return
        s_type = self._type_entry.GetValue()
        lines = self._lines_entry.GetValue()
        cfg = SpectrometerConfig(s_type, lines)
        Config.get().save_spectro_config(entry, cfg)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _delete(self, event: wx.CommandEvent):
        entry = self._name_combo.GetValue()
        if entry == '':
            return
        Config.get().delete_spectro_config(entry)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _cancel(self, event: wx.CommandEvent):
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)


class AavsoCfgGui(wx.Dialog):

    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('AAVSO Configuration')

        panel = wx.Panel(self)
        name_label = wx.StaticText(panel, label='Name:')
        names = Config.get().get_aavso_config_names()
        self._name_combo = wx.ComboBox(panel, choices=names, style=wx.CB_DROPDOWN | wx.CB_SORT)
        wxutil.size_text_by_chars(self._name_combo, 30)

        tel_label = wx.StaticText(panel, label='Telescope:')
        names = Config.get().get_telescope_config_names()
        self._tel_combo = wx.ComboBox(panel, choices=names, style=wx.CB_DROPDOWN | wx.CB_SORT | wx.CB_READONLY)
        wxutil.size_text_by_chars(self._tel_combo, 30)

        spec_label = wx.StaticText(panel, label='Spectrometer:')
        names = Config.get().get_spectro_config_names()
        self._spec_combo = wx.ComboBox(panel, choices=names, style=wx.CB_DROPDOWN | wx.CB_SORT | wx.CB_READONLY)
        wxutil.size_text_by_chars(self._spec_combo, 30)

        ccd_label = wx.StaticText(panel, label='Camera:')
        names = Config.get().get_camera_configs()
        self._ccd_combo = wx.ComboBox(panel, choices=names, style=wx.CB_DROPDOWN | wx.CB_SORT | wx.CB_READONLY)
        wxutil.size_text_by_chars(self._ccd_combo, 30)

        self._save_btn = wx.Button(panel, id=wx.ID_SAVE)
        self._delete_btn = wx.Button(panel, id=wx.ID_DELETE)
        self._cancel_btn = wx.Button(panel, id=wx.ID_CANCEL)

        grid = wx.FlexGridSizer(rows=4, cols=2, hgap=5, vgap=5)
        grid.Add(name_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._name_combo, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(tel_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._tel_combo, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(spec_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._spec_combo, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(ccd_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._ccd_combo, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._save_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._delete_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._cancel_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        # Need to keep a reference to the sizer, because
        # btn_sizer_s doesn't. This would yield a segfault otherwise.
        self._btn_sizer = btn_sizer

        btn_sizer_s = self.CreateSeparatedSizer(btn_sizer)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(btn_sizer_s, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        self._name_combo.Bind(wx.EVT_COMBOBOX, self._combo_evt)
        self.Bind(wx.EVT_BUTTON, self._save, id=wx.ID_SAVE)
        self.Bind(wx.EVT_BUTTON, self._delete, id=wx.ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self._cancel, id=wx.CANCEL)

        panel.SetSizer(vbox)
        panel.Fit()

        sz = panel.GetBestSize()
        self.SetClientSize(sz)
        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

    # noinspection PyUnusedLocal
    def _combo_evt(self, event: wx.Event):
        entry = self._name_combo.GetValue()
        aavso_cfg = Config.get().get_aavso_config(entry)
        self._tel_combo.SetValue(aavso_cfg.telescope)
        self._spec_combo.SetValue(aavso_cfg.spectrometer)
        self._ccd_combo.SetValue(aavso_cfg.ccd)

    def _save(self, event: wx.CommandEvent):
        if not self.Validate():
            return
        entry = self._name_combo.GetValue()
        if entry == '':
            return
        tel = self._tel_combo.GetValue()
        if tel == '':
            return
        spec = self._spec_combo.GetValue()
        if spec == '':
            return
        ccd = self._ccd_combo.GetValue()
        if ccd == '':
            return
        cfg = AavsoConfig(tel, spec, ccd)
        Config.get().save_aavso_config(entry, cfg)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _delete(self, event: wx.CommandEvent):
        entry = self._name_combo.GetValue()
        if entry == '':
            return
        Config.get().delete_aavso_config(entry)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _cancel(self, event: wx.CommandEvent):
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)


class LocationCfgGui(wx.Dialog):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Location Configuration')

        panel = wx.Panel(self)
        name_label = wx.StaticText(panel, label='Name:')
        names = Config.get().get_location_names()
        self._name_combo = wx.ComboBox(panel, choices=names, style=wx.CB_DROPDOWN | wx.CB_SORT)
        wxutil.size_text_by_chars(self._name_combo, 30)

        lat_label = wx.StaticText(panel, label='Latitude [hh mm [ss]]:')
        self._lat_entry = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._lat_entry, 12)

        lon_label = wx.StaticText(panel, label='Longitude [hh mm [ss]]:')
        self._lon_entry = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._lon_entry, 12)

        alt_label = wx.StaticText(panel, label='Altitude [m]:')
        self._alt_entry = wxli.IntCtrl(panel, min=-100)
        wxutil.size_text_by_chars(self._alt_entry, 4)
        self._alt_entry.SetValue(0)

        self._save_btn = wx.Button(panel, id=wx.ID_SAVE)
        self._delete_btn = wx.Button(panel, id=wx.ID_DELETE)
        self._cancel_btn = wx.Button(panel, id=wx.ID_CANCEL)

        grid = wx.FlexGridSizer(rows=4, cols=2, hgap=5, vgap=5)
        grid.Add(name_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._name_combo, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(lat_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._lat_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(lon_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._lon_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(alt_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._alt_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._save_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._delete_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._cancel_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        btn_sizer.AddStretchSpacer()
        # Need to keep a reference to the sizer, because
        # btn_sizer_s doesn't. This would yield a segfault otherwise.
        self._btn_sizer = btn_sizer

        btn_sizer_s = self.CreateSeparatedSizer(btn_sizer)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(btn_sizer_s, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        self.Bind(wx.EVT_COMBOBOX, self._combo_evt)
        self.Bind(wx.EVT_BUTTON, self._save, id=wx.ID_SAVE)
        self.Bind(wx.EVT_BUTTON, self._delete, id=wx.ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self._cancel, id=wx.CANCEL)

        panel.SetSizer(vbox)
        panel.Fit()

        sz = panel.GetBestSize()
        self.SetClientSize(sz)
        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

    # noinspection PyUnusedLocal
    def _combo_evt(self, event: wx.Event):
        entry = self._name_combo.GetValue()
        loc = Config.get().get_location(entry)
        self._lat_entry.SetValue(loc.lat.to_string())
        self._lon_entry.SetValue(loc.lon.to_string())

    def _save(self, event: wx.CommandEvent):
        if not self._lat_entry.Validate():
            return
        entry = self._name_combo.GetValue()
        if entry == '':
            return
        try:
            lat = Latitude(self._lat_entry.GetValue(), u.deg)
        except ValueError:
            self._lat_entry.SetForegroundColour(wx.Colour(255, 0, 0))
            self._lat_entry.SetFocus()
            return
        try:
            lon = Longitude(self._lon_entry.GetValue(), u.deg)
        except ValueError:
            self._lon_entry.SetForegroundColour(wx.Colour(255, 0, 0))
            self._lon_entry.SetFocus()
        lon = Longitude(self._lon_entry.GetValue(), u.deg)
        loc = EarthLocation(lat=lat, lon=lon, height=self._alt_entry.GetValue() * u.m)
        Config.get().save_location(entry, loc)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _delete(self, event: wx.CommandEvent):
        entry = self._name_combo.GetValue()
        if entry == '':
            return
        Config.get().delete_location(entry)
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)

    def _cancel(self, event: wx.CommandEvent):
        if self.IsModal():
            self.EndModal(event.GetId())
        else:
            self.Show(False)


class AavsoObscodeCfgGui(wx.Dialog):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('AAVSO Observer Code')

        panel = wx.Panel(self)
        obs_label = wx.StaticText(panel, label='Observer Code:')
        self._obs_entry = wx.TextCtrl(panel)
        wxutil.size_text_by_chars(self._obs_entry, 10)
        self._obs_entry.SetValue(Config.get().get_aavso_obscode())

        grid = wx.FlexGridSizer(rows=1, cols=2, hgap=5, vgap=5)
        grid.Add(obs_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)
        grid.Add(self._obs_entry, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT)

        btn_sizer = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(grid, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(btn_sizer, 0, wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        self.Bind(wx.EVT_BUTTON, self._save_or_cancel)

        panel.SetSizer(vbox)
        panel.Fit()

        sz = panel.GetBestSize()
        self.SetClientSize(sz)
        self.Layout()
        sz = self.GetBestSize()
        self.SetSizeHints(sz.x, sz.y, sz.x, sz.y)

    def _save_or_cancel(self, event: wx.CommandEvent):
        ev_id = event.GetId()
        if ev_id == wx.ID_OK:
            obscode = self._obs_entry.GetValue().strip()
            Config.get().set_aavso_obscode(obscode)
            rc = wx.OK
        else:
            rc = wx.CANCEL
        if self.IsModal():
            self.EndModal(rc)
        else:
            self.Show(False)

if __name__ == '__main__':
    app = wx.App()
    app.SetAppName('spectra')
    user_cfg = wx.StandardPaths.Get().GetUserConfigDir()
    print(f'Config @ {user_cfg}')
    frame = wx.Frame(None, title='Config Test')
    pnl = wx.Panel(frame)
    id_ref = wx.NewIdRef()
    cam_button = wx.Button(pnl, id=id_ref.GetId(), label='Run Camera Config')
    tel_button = wx.Button(pnl, id=id_ref.GetId(), label='Run Telescope Config')
    spec_button = wx.Button(pnl, id=id_ref.GetId(), label='Run Spectrometer Config')
    aav_button = wx.Button(pnl, id=id_ref.GetId(), label='Run AAVSO Config')
    loc_button = wx.Button(pnl, id=id_ref.GetId(), label='Run Location Config')
    obs_button = wx.Button(pnl, id=id_ref.GetId(), label='Run Observer Config')
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(cam_button, 0, wx.EXPAND, 3)
    sizer.Add(tel_button, 0, wx.EXPAND, 3)
    sizer.Add(spec_button, 0, wx.EXPAND, 3)
    sizer.Add(aav_button, 0, wx.EXPAND, 3)
    sizer.Add(loc_button, 0, wx.EXPAND, 3)
    sizer.Add(obs_button, 0, wx.EXPAND, 3)
    pnl.SetSizer(sizer)
    pnl.Fit()
    sz = pnl.GetBestSize()
    frame.SetClientSize(sz)


    def _on_btn(event: wx.CommandEvent):
        src = event.GetEventObject()
        if src == cam_button:
            with CamCfgGUI(frame) as dlg:
                res = dlg.ShowModal()
                print(f'Dialog ended with {res}')
        elif src == tel_button:
            with TelescopeCfgGui(frame) as dlg:
                dlg.ShowModal()
        elif src == spec_button:
            with SpectrometerCfgGui(frame) as dlg:
                dlg.ShowModal()
        elif src == aav_button:
            with AavsoCfgGui(frame) as dlg:
                dlg.ShowModal()
        elif src == loc_button:
            with LocationCfgGui(frame) as dlg:
                dlg.ShowModal()
        elif src == obs_button:
            with AavsoObscodeCfgGui(frame) as dlg:
                dlg.ShowModal()

    frame.Bind(wx.EVT_BUTTON, _on_btn)
    frame.Show()
    app.MainLoop()
