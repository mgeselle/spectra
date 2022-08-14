from astropy.io import fits
from pathlib import Path
import sys
import wx

from calib import CalibConfigurator
from combine import Combine
from configgui import CamCfgGUI
from crop import Crop
from imgdisplay import ImageDisplay
from reduce import Reduce
from specview import Specview
import wxutil


ID_OPEN = wx.NewIdRef()
ID_COMBINE = wx.NewIdRef()
ID_CROP = wx.NewIdRef()
ID_REDUCE = wx.NewIdRef()
ID_CFG_CAMERA = wx.NewIdRef()
ID_CFG_CALIB = wx.NewIdRef()


class Main(wx.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Spectra')

        menubar = wx.MenuBar()

        self._file_menu = wx.Menu()
        open_item = self._file_menu.Append(ID_OPEN.GetId(), '&Open File...')
        self._file_menu.AppendSeparator()
        exit_item = self._file_menu.Append(wx.ID_EXIT)
        menubar.Append(self._file_menu, '&File')

        self._img_ops_menu = wx.Menu()
        combine_item = self._img_ops_menu.Append(ID_COMBINE.GetId(), '&Combine...')
        crop_item = self._img_ops_menu.Append(ID_CROP.GetId(), 'Cro&p...')
        reduce_item = self._img_ops_menu.Append(ID_REDUCE.GetId(), '&Reduce...')
        menubar.Append(self._img_ops_menu, '&Image Ops')

        self._config_menu = wx.Menu()
        camera_item = self._config_menu.Append(ID_CFG_CAMERA.GetId(), '&Camera')
        calib_cfg_item = self._config_menu.Append(ID_CFG_CALIB.GetId(), 'C&alibration')
        menubar.Append(self._config_menu, '&Configuration')

        self.SetMenuBar(menubar)

        self._content_pane = wx.Panel(self)
        self._image_display = ImageDisplay(self._content_pane)
        self._specview = Specview(self._content_pane)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self._content_pane.SetSizer(sizer)
        sizer.Add(self._image_display, 1, wx.EXPAND)
        sizer.Add(self._specview, 1, wx.EXPAND)
        sizer.Show(self._image_display, False)
        sizer.Layout()
        self._specview_visible = True

        self.Bind(wx.EVT_MENU, self._open, open_item)
        self.Bind(wx.EVT_MENU, lambda evt: sys.exit(0), exit_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, Combine(self)), combine_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, Crop(self)), crop_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, Reduce(self)), reduce_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, CamCfgGUI(self)), camera_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, CalibConfigurator(self)), calib_cfg_item)

        display = wx.Display()
        display_sz = display.GetClientArea()
        width = int(0.6 * display_sz.GetWidth())
        height = int(0.6 * display_sz.GetHeight())
        self.SetSizeHints(width, height)

    def make_specview_visible(self, visible: bool):
        if visible == self._specview_visible:
            return
        sizer = self._content_pane.GetSizer()
        sizer.Show(self._image_display, not visible)
        sizer.Show(self._specview, visible)
        sizer.Layout()
        self._specview_visible = visible

    # noinspection PyUnusedLocal
    def _open(self, event: wx.Event):
        file_name = wxutil.select_file(self)
        if not file_name:
            return
        file_path = Path(file_name)
        self.SetTitle(f'Spectra - {file_path.name}')
        hdu_l = fits.open(file_name)
        header = hdu_l[0].header
        data = hdu_l[0].data
        hdu_l.close()
        if header['NAXIS'] == 1:
            self.make_specview_visible(True)
            self._specview.clear()
            self._specview.add_spectrum(data)
        elif header['NAXIS'] == 2:
            data = None
            self.make_specview_visible(False)
            self._image_display.display(file_name)

    @staticmethod
    def _enable_after_close(event: wx.ShowEvent, menu: wx.Menu, item_id: int):
        if not event.IsShown():
            menu.Enable(item_id, True)

    @staticmethod
    def _show_dialog(event: wx.CommandEvent, dialog: wx.Dialog):
        menu = event.GetEventObject()
        item = event.GetId()
        menu.Enable(item, False)
        dialog.Bind(wx.EVT_SHOW, lambda evt: Main._enable_after_close(evt, menu, item))
        dialog.Show()


if __name__ == '__main__':
    app = wx.App()
    app.SetAppName('spectra')

    main = Main(None)
    app.SetTopWindow(main)
    main.Show()

    app.MainLoop()

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
