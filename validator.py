import string
import wx


class DecimalValidator(wx.Validator):
    def __init__(self):
        super().__init__()
        self.Bind(wx.EVT_CHAR, DecimalValidator._on_char)

    def Clone(self) -> wx.Object:
        return self.__class__()

    def TransferToWindow(self) -> bool:
        return True

    def TransferFromWindow(self) -> bool:
        ctrl = self.GetWindow()
        if ctrl is None:
            return True

        text = ctrl.GetValue()
        if text != '':
            try:
                float(text)
            except ValueError:
                return False

        return True

    def Validate(self, parent):
        return self.TransferFromWindow()

    @staticmethod
    def _on_char(event: wx.KeyEvent):
        key = event.GetKeyCode()
        ctrl = event.GetEventObject()

        text_value: str = wx.TextCtrl.GetValue(ctrl)
        pos = ctrl.GetInsertionPoint()
        sel_start, sel_to = ctrl.GetSelection()
        select_len = sel_to - sel_start

        new_value = text_value
        need_validation = False
        allow_event = False
        if key in (wx.WXK_DELETE, wx.WXK_BACK):
            if select_len:
                new_value = text_value[:sel_start] + text_value[sel_to:]
            elif key == wx.WXK_DELETE and pos < len(text_value):
                if pos == len(text_value) - 1:
                    new_value = text_value[:-1]
                elif pos == 0:
                    new_value = text_value[1:]
                else:
                    new_value = text_value[:pos] + text_value[pos + 1:]
            elif key == wx.WXK_BACK and pos > 0:
                if pos == len(text_value):
                    new_value = text_value[:-1]
                elif pos == 1:
                    new_value = text_value[1:]
                else:
                    new_value = text_value[:pos-1] + text_value[pos:]
            if new_value == '.' or new_value == '':
                allow_event = True
            else:
                need_validation = True
        elif chr(key) == '.':
            if len(text_value) == 0 or '.' not in text_value:
                allow_event = True
            need_validation = False
        elif chr(key) in string.digits:
            if select_len:
                new_value = text_value[:sel_start] + chr(key) + text_value[sel_to:]
            elif pos == len(text_value):
                new_value = text_value + chr(key)
            elif pos == 0:
                new_value = chr(key) + text_value
            else:
                new_value = text_value[:pos] + chr(key) + text_value[pos:]
            need_validation = True
        elif key < wx.WXK_SPACE or key > 255:
            allow_event = True
            need_validation = False
        else:
            need_validation = False

        if need_validation:
            try:
                float(new_value)
                allow_event = True
            except ValueError:
                allow_event = False

        if allow_event:
            event.Skip()


if __name__ == '__main__':
    app = wx.App()
    frame = wx.Frame(None, title='Progress Test')

    panel = wx.Panel(frame)
    ctrl = wx.TextCtrl(panel, validator=DecimalValidator())
    ctrl.SetInitialSize(ctrl.GetSizeFromTextSize(ctrl.GetFullTextExtent('0' * 8)[0]))
    sizer = wx.BoxSizer(wx.HORIZONTAL)
    sizer.Add(ctrl, 0, wx.ALL, border=10)
    panel.SetSizer(sizer)

    panel.Fit()

    sz = panel.GetBestSize()
    # SystemSettings.GetMetric(wx.SYS_CAPTION_Y) always returns -1.
    # Using empirical value 28
    frame.SetSizeHints(sz.x, sz.y + 28, sz.x, sz.y + 28)
    frame.Show()
    app.MainLoop()

