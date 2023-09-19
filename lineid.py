import astropy.units as u
import config
import matplotlib as plot
import numpy as np
import numpy.ma as ma
import numpy.typing as npt
import re
import specview
import threading
import typing as ty
import wx
import wxutil
import wx.lib.newevent as ne

from astropy.table import table
from astroquery.nist import Nist


NistEvent, EVT_ID_NIST = ne.NewEvent()

_colours = ['xkcd:lime green', 'xkcd:light magenta', 'xkcd:teal', 'xkcd:light purple', 'xkcd:goldenrod',
            'xkcd:light red', 'xkcd:cerulean', 'xkcd:dark cyan', 'xkcd:tangerine', 'xkcd:maize']
_rgb_colours = [wx.Colour(0x89fe05), wx.Colour(0xfa5ff7), wx.Colour(0x029386), wx.Colour(0xbf77f6), wx.Colour(0xfac205),
                wx.Colour(0xff474c), wx.Colour(0x0485d1), wx.Colour(0x0a888a), wx.Colour(0xff9408), wx.Colour(0xf4d054)]


class LineIDDialog(wx.Dialog):

    def __init__(self, parent: wx.Window, min_wavelen, max_wavelen,
                 specview: specview.Specview, **kwargs):
        super().__init__(parent, **kwargs)
        self.SetTitle('Line Identification')

        species_label = wx.StaticText(self, wx.ID_ANY, 'Species:')
        self._species_entry = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        wxutil.size_text_by_chars(self._species_entry, 8)
        self._species_list = wx.ListView(self, wx.ID_ANY, style=wx.LC_REPORT)
        extent = self._species_list.GetFullTextExtent('M' * 16)
        self._species_list.AppendColumn('Displaying'
                                        , wx.LIST_FORMAT_LEFT, extent[0])
        self._species_list.SetInitialSize(wx.Size(extent[0], extent[1] * 10))

        species_sizer = wx.BoxSizer(wx.HORIZONTAL)
        species_sizer.Add(species_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        species_sizer.Add(self._species_entry, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(species_sizer, 0, wx.ALL, 5)
        dialog_sizer.Add(self._species_list, 0, wx.GROW | wx.ALL, 5)

        self.SetSizerAndFit(dialog_sizer)

        self._species_entry.Bind(wx.EVT_TEXT_ENTER, self._on_enter)
        self.Bind(EVT_ID_NIST, self._retrieval_done)
        self._species_list.Bind(wx.EVT_LIST_KEY_DOWN, self._on_list_key_down)

        self._loaded = dict()
        self._min_wavelen = min_wavelen
        self._max_wavelen = max_wavelen
        self._specview = specview
        self._colour_idx = 0

    def _on_enter(self, event: wx.CommandEvent):
        species = self._species_entry.GetValue().strip()
        if not species:
            return
        key = species.upper()
        if key in self._loaded:
            return
        species_table = config.Config.get().get_calib_table(species)
        if species_table:
            self._display_species(species, species_table)
        else:
            wx.BeginBusyCursor()
            thread = threading.Thread(target=self._retrieve_species, args=[species])
            thread.start()

    def _retrieve_species(self, species: str):
        try:
            ref_spectrum = Nist.query(config.MIN_WAVELEN * u.AA, config.MAX_WAVELEN * u.AA,
                                      linename=species, wavelength_type='vac+air')
        except Exception as e:
            self.QueueEvent(NistEvent(msg=e.args[0]))
        else:
            config.Config.get().save_calib_table(species, ref_spectrum)
            self.QueueEvent(NistEvent(msg=None, species=species))

    def _display_species(self, species: str, spec_table: table.Table):
        global _colours
        global _rgb_colours
        wavelengths = []
        intensities = []
        for wavelength, rel_int in spec_table.iterrows('Observed', 'Rel.'):
            if wavelength is ma.masked or wavelength < self._min_wavelen:
                continue
            if wavelength > self._max_wavelen:
                break
            try:
                rel_i_m = re.match(r'\d+', str(rel_int))
                if not rel_i_m:
                    continue
                rel_int = float(rel_i_m.group(0))
            except ValueError:
                continue
            except ma.core.MaskError:
                continue
            wavelengths.append(wavelength)
            intensities.append(rel_int)
        if len(wavelengths) == 0:
            return
        np_intens = np.array(intensities)
        np_intens = np_intens / (2 * np.max(np_intens))
        # XKCD colours are at https://xkcd.com/color/rgb/
        line_coll = self._specview.add_vlines(wavelengths, np_intens,
                                              _rgb_colours[self._colour_idx].GetAsString(wx.C2S_HTML_SYNTAX))
        key = species.upper()
        if not self._loaded:
            self._species_list.Append([species])
            idx = 0
        else:
            idx = -1
            for (i, spec_key) in enumerate(sorted(self._loaded.keys())):
                if spec_key > key:
                    idx = i
                    break
            if idx == -1:
                self._species_list.Append([species])
                idx = len(self._loaded.keys())
            else:
                self._species_list.InsertItem(idx, species)
        self._species_list.SetItemBackgroundColour(idx, _rgb_colours[self._colour_idx])
        self._loaded[key] = line_coll
        self._colour_idx += 1
        if self._colour_idx == len(_colours):
            self._colour_idx = 0

    def _retrieval_done(self, event: NistEvent):
        wx.EndBusyCursor()
        if event.msg is not None:
            with wx.MessageDialog(self, event.msg, style=wx.OK | wx.CENTRE | wx.ICON_ERROR) as dlg:
                dlg.ShowModal()
        else:
            species = event.species
            species_table = config.Config.get().get_calib_table(species)
            self._display_species(species, species_table)

    def _on_list_key_down(self, event: wx.ListEvent):
        # This looks iffy: I'd rather use a portable way to refer to delete and backspace...
        if event.GetKeyCode() in (8, 127):
            sorted_keys = sorted(self._loaded.keys())
            deleted_key = sorted_keys[event.GetIndex()]
            line_coll = self._loaded[deleted_key]
            self._specview.remove_vlines(line_coll)
            del self._loaded[deleted_key]
            self._species_list.DeleteItem(event.GetIndex())

    def clear_all_lines(self):
        sorted_keys = sorted(self._loaded.keys())
        for k in sorted_keys:
            self._specview.remove_vlines(self._loaded[k])
            self._species_list.DeleteItem(0)
        self._loaded.clear()

    def set_limit(self, min_wavelen, max_wavelen):
        self._min_wavelen = min_wavelen
        self._max_wavelen = max_wavelen


_dialog: ty.Union[None, LineIDDialog] = None


def show_dialog(specview: specview.Specview, parent, min_wavelen, max_wavelen):
    global _dialog
    if _dialog:
        _dialog.set_limit(min_wavelen, max_wavelen)
        return

    _dialog = LineIDDialog(parent, min_wavelen, max_wavelen, specview)
    _dialog.Bind(wx.EVT_SHOW, _on_hide_dialog)
    _dialog.Show()


def hide_dialog():
    global _dialog
    if not _dialog:
        return
    _dialog.Show(False)


def is_dialog_visible():
    global _dialog
    return _dialog is not None


def _on_hide_dialog(event: ty.Union[None, wx.ShowEvent]):
    global _dialog
    if event is None or not event.IsShown():
        _dialog.clear_all_lines()
        _dialog.Destroy()
        _dialog = None


def clear_lines():
    global _dialog
    if _dialog:
        _dialog.clear_all_lines()


if __name__ == '__main__':
    app = wx.App()
    frame = wx.Frame(None, title='LineID Test')
    pnl = wx.Panel(frame)
    id_ref = wx.NewIdRef()
    button = wx.Button(pnl, id=id_ref.GetId(), label='Run')
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(button, 0, 0, 0)
    pnl.SetSizer(sizer)
    pnl.Fit()
    pnl_sz = pnl.GetBestSize()
    frame.SetClientSize(pnl_sz)

    # noinspection PyUnusedLocal
    def _on_btn(event):
        button.Disable()
        dlg = LineIDDialog(frame)

        def on_dlg_show(evt: wx.ShowEvent):
            if not evt.IsShown():
                dlg.Destroy()
                button.Enable()

        dlg.Bind(wx.EVT_SHOW, on_dlg_show)
        dlg.Show()

    frame.Bind(wx.EVT_BUTTON, _on_btn, id=id_ref.GetId())
    frame.Show()
    app.MainLoop()
