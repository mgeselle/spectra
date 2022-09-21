import numpy as np
import sys
from pathlib import Path
from typing import Tuple

import wx
from astropy.io import fits

import calib
import fitsheader
import response
import util
import wxutil
from combine import Combine
from configgui import CamCfgGUI, TelescopeCfgGui, SpectrometerCfgGui, AavsoCfgGui, LocationCfgGui, AavsoObscodeCfgGui
from crop import Crop
from imgdisplay import ImageDisplay
from reduce import Reduce
from specview import Specview, AnnotationHandler, ContinuumFit, EVT_ID_FILE_READY

ID_OPEN = wx.NewIdRef()
ID_SAVE = wx.NewIdRef()
ID_ADD_SP = wx.NewIdRef()
ID_COMBINE = wx.NewIdRef()
ID_CROP = wx.NewIdRef()
ID_REDUCE = wx.NewIdRef()
ID_CFG_CAMERA = wx.NewIdRef()
ID_CFG_CALIB = wx.NewIdRef()
ID_ANNOTATE = wx.NewIdRef()
ID_RECTIFY = wx.NewIdRef()


class Main(wx.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Spectra')

        menubar = wx.MenuBar()

        self._file_menu = wx.Menu()
        open_item = self._file_menu.Append(ID_OPEN.GetId(), '&Open File...')
        save_item = self._file_menu.Append(ID_SAVE.GetId(), '&Save File...')
        self._file_menu.Enable(ID_SAVE.GetId(), False)
        add_sp_item = self._file_menu.Append(ID_ADD_SP.GetId(), '&Add Spectrum...')
        self._file_menu.Enable(ID_ADD_SP.GetId(), False)
        header_item = self._file_menu.Append(wx.ID_ANY, 'Show &Header')
        self._file_menu.AppendSeparator()
        exit_item = self._file_menu.Append(wx.ID_EXIT)
        menubar.Append(self._file_menu, '&File')

        self._img_ops_menu = wx.Menu()
        combine_item = self._img_ops_menu.Append(ID_COMBINE.GetId(), '&Combine...')
        crop_item = self._img_ops_menu.Append(ID_CROP.GetId(), 'Cro&p...')
        reduce_item = self._img_ops_menu.Append(ID_REDUCE.GetId(), '&Reduce...')
        menubar.Append(self._img_ops_menu, '&Image Ops')

        self._spec_ops_menu = wx.Menu()
        calib_item = self._spec_ops_menu.Append(wx.ID_ANY, '&Wavelength Calibration')
        calc_resp_item = self._spec_ops_menu.Append(wx.ID_ANY, 'Calculate &Response')
        apply_resp_item = self._spec_ops_menu.Append(wx.ID_ANY, '&Apply Response')
        menubar.Append(self._spec_ops_menu, '&Spectrum Ops')

        self._config_menu = wx.Menu()
        telescope_item = self._config_menu.Append(wx.ID_ANY, '&Telescope')
        spectro_item = self._config_menu.Append(wx.ID_ANY, '&Spectrometer')
        camera_item = self._config_menu.Append(ID_CFG_CAMERA.GetId(), '&Camera')
        aavso_item = self._config_menu.Append(wx.ID_ANY, 'AAVSO Equipment &Package')
        obs_item = self._config_menu.Append(wx.ID_ANY, 'AAVSO &Observer Code')
        loc_item = self._config_menu.Append(wx.ID_ANY, '&Location')
        calib_cfg_item = self._config_menu.Append(ID_CFG_CALIB.GetId(), 'C&alibration')
        menubar.Append(self._config_menu, '&Configuration')

        self.SetMenuBar(menubar)

        self._toolbar = self.CreateToolBar()
        resource_dir = Path(__file__).absolute().parent / 'resources'
        annotate_bmp = wx.Bitmap()
        annotate_bmp.LoadFile(str(resource_dir / 'pencil@1x.png'))
        self._toolbar.SetToolBitmapSize(wx.Size(24, 24))
        annotate_tool = self._toolbar.AddCheckTool(ID_ANNOTATE.GetId(), 'Annotate', annotate_bmp,
                                                   shortHelp='Add annotation to image')

        rectify_bmp = wx.Bitmap()
        rectify_bmp.LoadFile(str(resource_dir / 'funnel@1x.png'))
        rectify_tool = self._toolbar.AddCheckTool(ID_RECTIFY.GetId(), 'Rectify', rectify_bmp,
                                                  shortHelp='Rectify spectrum')

        self._toolbar.Realize()
        self._toolbar.EnableTool(ID_ANNOTATE.GetId(), False)
        self._toolbar.EnableTool(ID_RECTIFY.GetId(), False)

        self._content_pane = wx.Panel(self)
        self._image_display = ImageDisplay(self._content_pane)
        self._specview = Specview(self._content_pane)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._image_display, 1, wx.EXPAND)
        sizer.Add(self._specview, 1, wx.EXPAND)
        sizer.Show(self._image_display, False)
        sizer.SetSizeHints(self._content_pane)
        self._content_pane.SetSizer(sizer)
        self._specview_visible = True
        tb_sz = self._toolbar.GetBestSize()
        cp_sz = self._content_pane.GetMinSize()
        min_sz = wx.Size(cp_sz.Width, cp_sz.Height + tb_sz.Height + 50)
        self.SetMinSize(min_sz)
        sizer.Layout()

        self.Bind(wx.EVT_MENU, self._open, open_item)
        self.Bind(wx.EVT_MENU, lambda evt: self._specview.save_file(), save_item)
        self.Bind(wx.EVT_MENU, self._add_spectrum, add_sp_item)
        self.Bind(wx.EVT_MENU, self._show_header, header_item)
        self.Bind(wx.EVT_MENU, lambda evt: sys.exit(0), exit_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, Combine(self)), combine_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, Crop(self)), crop_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, Reduce(self)), reduce_item)
        self.Bind(wx.EVT_MENU, self._show_calib_file_dialog, calib_item)
        self.Bind(wx.EVT_MENU, self._run_calc_response, calc_resp_item)
        self.Bind(wx.EVT_MENU, self._run_apply_response, apply_resp_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, TelescopeCfgGui(self)), telescope_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, SpectrometerCfgGui(self)), spectro_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, CamCfgGUI(self)), camera_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, AavsoCfgGui(self)), aavso_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, AavsoObscodeCfgGui(self)), obs_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, LocationCfgGui(self)), loc_item)
        self.Bind(wx.EVT_MENU, lambda evt: Main._show_dialog(evt, calib.CalibConfigurator(self)), calib_cfg_item)
        self._toolbar.Bind(wx.EVT_MENU, self._toggle_annotate, annotate_tool)
        self._toolbar.Bind(wx.EVT_MENU, self._toggle_rectify, rectify_tool)
        self.Bind(EVT_ID_FILE_READY, lambda evt: self._file_menu.Enable(ID_SAVE.GetId(), True))

        display = wx.Display()
        display_sz = display.GetClientArea()
        width = int(0.6 * display_sz.GetWidth())
        height = int(0.6 * display_sz.GetHeight())
        if width < min_sz.Width:
            width = min_sz.Width
        if height < min_sz.Height:
            height = min_sz.Height
        self.SetMinClientSize(wx.Size(width, height))

    def make_specview_visible(self, visible: bool):
        if visible == self._specview_visible:
            return
        sizer = self._content_pane.GetSizer()
        sizer.Show(self._image_display, not visible)
        sizer.Show(self._specview, visible)
        sizer.Layout()
        self._specview_visible = visible
        self.Layout()

    def _open(self, event: wx.CommandEvent):
        menu = event.GetEventObject()
        file_name = wxutil.select_file(self)
        if not file_name:
            return
        file_path = Path(file_name)
        self.SetTitle(f'Spectra - {file_path.name}')
        hdu_l = fits.open(file_name)
        header = hdu_l[0].header
        data = hdu_l[0].data
        hdu_l.close()
        self._file_menu.Enable(ID_SAVE, False)
        if self._specview_visible:
            self._toolbar.ToggleTool(ID_ANNOTATE, False)
            self._toolbar.ToggleTool(ID_RECTIFY, False)
            self._specview.toggle_event_handler(None)

        if header['NAXIS'] == 1 or data.shape[0] == 1:
            if data.shape[0] == 1:
                disp_data = data[0]
            else:
                disp_data = data
            self.make_specview_visible(True)
            self._specview.clear()
            self._specview.add_spectrum(disp_data, header)
            menu.Enable(ID_ADD_SP.GetId(), True)
            self._toolbar.EnableTool(ID_ANNOTATE.GetId(), True)
            self._toolbar.EnableTool(ID_RECTIFY.GetId(), True)
        elif header['NAXIS'] == 2:
            data = None
            self.make_specview_visible(False)
            self._image_display.display(file_name)
            menu.Enable(ID_ADD_SP.GetId(), False)
            self._toolbar.EnableTool(ID_ANNOTATE.GetId(), False)
            self._toolbar.EnableTool(ID_RECTIFY.GetId(), False)

    def _add_spectrum(self, event: wx.CommandEvent):
        file_name = wxutil.select_file(self)
        if not file_name:
            return
        file_path = Path(file_name)
        with fits.open(file_path) as hdu_l:
            data = hdu_l[0].data
            header = hdu_l[0].header
        if header['NAXIS'] != 1 and data.shape[0] != 1:
            return
        if 'CRVAL1' not in header:
            return
        self._file_menu.Enable(ID_SAVE, False)
        if data.shape[0] == 1:
            data = data[0, :]
        data_max = np.max(data)
        if data_max != 1.0:
            data = data / data_max
        data = data + 0.1 * self._specview.current_max
        self._specview.add_spectrum(data, header)

    def _show_header(self, event: wx.CommandEvent):
        menu, item = Main._disable_before_open(event)

        file = wxutil.select_file(self)
        if not file:
            menu.Enable(item, True)
            return

        dlg = fitsheader.FitsHeaderDialog(self, Path(file))
        dlg.Bind(wx.EVT_SHOW, lambda evt: Main._enable_after_close(evt, menu, item))
        dlg.Show()

    def _toggle_annotate(self, event: wx.CommandEvent):
        if event.GetSelection():
            self._specview.toggle_event_handler(AnnotationHandler())
            self._toolbar.EnableTool(ID_RECTIFY.GetId(), False)
        else:
            self._specview.toggle_event_handler(None)
            self._toolbar.EnableTool(ID_RECTIFY.GetId(), True)

    def _toggle_rectify(self, event: wx.CommandEvent):
        if event.GetSelection():
            self._specview.toggle_event_handler(ContinuumFit(self))
            self._toolbar.EnableTool(ID_ANNOTATE.GetId(), False)
        else:
            self._specview.toggle_event_handler(None)
            self._toolbar.EnableTool(ID_ANNOTATE.GetId(), True)

    def _show_calib_file_dialog(self, event: wx.CommandEvent):
        menu, item = Main._disable_before_open(event)
        dialog = calib.CalibFileDialog(self)

        def _on_calib_file_close(evt: wx.ShowEvent):
            if evt.IsShown():
                return
            calib_file = dialog.calib_file
            pgm_file = dialog.pgm_file
            output_path = dialog.output_dir

            dialog.Destroy()
            if not calib_file:
                menu.Enable(item, True)
                return

            with fits.open(calib_file) as hdu_l:
                data = hdu_l[0].data
            peaks, fwhms = calib.find_peaks(data)
            calib_dialog = calib.CalibDialog(self, data, peaks, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

            def _on_calib_close(calib_show_evt: wx.ShowEvent):
                if calib_show_evt.IsShown():
                    return
                poly = calib_dialog.poly
                calib_dialog.Destroy()
                if poly is not None:
                    center = data.size / 2
                    min_dist = None
                    prev_peak = None
                    prev_fwhm = None
                    for peak, fwhm in zip(peaks, fwhms):
                        dist = abs(center - peak)
                        if min_dist is None or dist < min_dist:
                            min_dist = dist
                        elif dist > min_dist:
                            lambda_peak = poly(prev_peak)
                            delta_lambda = poly(prev_peak + prev_fwhm / 2) - poly(prev_peak - prev_fwhm / 2)
                            resolution = lambda_peak / delta_lambda
                            break
                        prev_peak = peak
                        prev_fwhm = fwhm

                    # noinspection PyUnboundLocalVariable
                    calib.apply_calibration(calib_file, poly, output_path, resolution)
                    if pgm_file:
                        calib.apply_calibration(pgm_file, poly, output_path, resolution)
                menu.Enable(item, True)

            calib_dialog.Bind(wx.EVT_SHOW, _on_calib_close)
            calib_dialog.Show()

        dialog.Bind(wx.EVT_SHOW, _on_calib_file_close)
        dialog.Show()

    def _run_calc_response(self, event: wx.CommandEvent):
        menu, item = Main._disable_before_open(event)
        rec_file = wxutil.select_file(self, 'Select Recorded Spectrum')
        if not rec_file:
            menu.Enable(item, True)
            return
        ref_file = wxutil.select_file(self, 'Select Reference Spectrum')
        if not ref_file:
            menu.Enable(item, True)
            return
        out_dir = wxutil.select_dir(self, must_exist=False, title='Select Output Directory')
        if out_dir:
            rec_path = Path(rec_file)
            ref_path = Path(ref_file)
            out_path = util.dir_to_path(out_dir)
            try:
                out_path.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                with wx.MessageDialog(self, 'Error creating output directory: ' + str(e), 'Error',
                                      style=wx.OK | wx.CENTRE | wx.ICON_ERROR) as dlg:
                    dlg.ShowModal()
                menu.Enable(item, True)
                return
            response.create_response(rec_path, ref_path, out_path)
        menu.Enable(item, True)

    def _run_apply_response(self, event: wx.CommandEvent):
        menu, item = Main._disable_before_open(event)
        resp_file = wxutil.select_file(self, 'Select Response File')
        if not resp_file:
            menu.Enable(item, True)
            return
        pgm_file = wxutil.select_file(self, 'Select Spectrum')
        if not pgm_file:
            menu.Enable(item, True)
            return
        out_dir = wxutil.select_dir(self, must_exist=False, title='Select Output Directory')
        if out_dir:
            resp_path = Path(resp_file)
            pgm_path = Path(pgm_file)
            out_path = util.dir_to_path(out_dir)
            try:
                out_path.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                with wx.MessageDialog(self, 'Error creating output directory: ' + str(e), 'Error',
                                      style=wx.OK | wx.CENTRE | wx.ICON_ERROR) as dlg:
                    dlg.ShowModal()
                menu.Enable(item, True)
                return
            response.apply_response(resp_path, pgm_path, out_path)
        menu.Enable(item, True)

    @staticmethod
    def _disable_before_open(event: wx.CommandEvent) -> Tuple[wx.Menu, int]:
        menu = event.GetEventObject()
        item = event.GetId()
        menu.Enable(item, False)
        return menu, item

    @staticmethod
    def _enable_after_close(event: wx.ShowEvent, menu: wx.Menu, item_id: int):
        if not event.IsShown():
            menu.Enable(item_id, True)
            event.GetEventObject().Destroy()

    @staticmethod
    def _show_dialog(event: wx.CommandEvent, dialog: wx.Dialog):
        menu, item = Main._disable_before_open(event)
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
