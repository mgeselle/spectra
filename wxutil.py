from pathlib import Path
from typing import Union
import wx
import wx.lib.newevent as ne
from config import Config


CompletionEvent, EVT_SP_COMPLETE = ne.NewEvent()


def size_text_by_chars(tc: Union[wx.TextCtrl, wx.ComboBox], num_chars: int):
    ext = tc.GetFullTextExtent('M' * num_chars)
    sz = tc.GetSizeFromTextSize(ext[0])
    tc.SetInitialSize(sz)


def select_dir(parent: wx.Window, must_exist: bool) -> Union[None, str]:
    initial_dir = str(Config.get().get_last_directory())
    style = wx.DD_DEFAULT_STYLE
    if must_exist:
        style = style | wx.DD_DIR_MUST_EXIST
    with wx.DirDialog(parent, 'Choose Directory', defaultPath=initial_dir, style=style) as dlg:
        dlg_res = dlg.ShowModal()
        if dlg_res == wx.ID_CANCEL:
            return None
        raw_result = dlg.GetPath()
        Config.get().set_last_directory(raw_result)
        return raw_result.replace(str(Path.home()), '~')

