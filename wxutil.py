from typing import Union
import wx
import wx.lib.newevent as ne


CompletionEvent, EVT_SP_COMPLETE = ne.NewEvent()


def size_text_by_chars(tc: Union[wx.TextCtrl, wx.ComboBox], num_chars: int):
    ext = tc.GetFullTextExtent('M' * num_chars)
    sz = tc.GetSizeFromTextSize(ext[0])
    tc.SetInitialSize(sz)


def select_dir(parent: wx.Window, must_exist: bool) -> Union[None, str]:
    pass
