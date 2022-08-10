import threading
from typing import Callable, Iterable, Any
import wx
import wx.lib.newevent as ne


ProgressEvent, EVT_ID_PROGRESS = ne.NewEvent()


class TaskDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, **kwargs):
        super().__init__(parent, **kwargs)
        self.cancel_flag = threading.Event()
        self._progress = None
        self._progress_title = 'Running...'
        self._message_template = u'\u00a0' * 40
        self._completion_callback = None
        self._auto_hide = False

    @property
    def progress_title(self):
        return self._progress_title

    @progress_title.setter
    def progress_title(self, title: str):
        self._progress_title = title

    @property
    def message_template(self):
        return self._message_template

    @message_template.setter
    def message_template(self, template: str):
        self._message_template = template

    @property
    def completion_callback(self):
        return self._completion_callback

    @completion_callback.setter
    def completion_callback(self, callback: Callable[[], None]):
        self._completion_callback = callback

    @property
    def auto_hide(self):
        return self._auto_hide

    @auto_hide.setter
    def auto_hide(self, hide: bool):
        self._auto_hide = hide

    def run_task(self, maximum: int, target: Callable[[...], None], args: Iterable[Any]):
        self.cancel_flag.clear()
        style = wx.PD_CAN_ABORT
        if self._auto_hide:
            style = style | wx.PD_AUTO_HIDE
        self._progress = wx.ProgressDialog(self._progress_title, parent=self, maximum=maximum,
                                           message=self._message_template, style=style)

        self.Bind(EVT_ID_PROGRESS, self._on_progress)
        self._progress.Bind(wx.EVT_SHOW, self._on_progress_show)

        thread = threading.Thread(target=target, args=args)
        thread.start()

    def send_progress(self, value: int, message: str):
        event = ProgressEvent(value=value, message=message)
        if not self.cancel_flag.is_set():
            self.QueueEvent(event)
        return self.cancel_flag.is_set()

    # noinspection PyUnusedLocal
    def on_cancel(self, event: wx.Event):
        if self.IsModal():
            self.EndModal(wx.CANCEL)
        else:
            self.Show(False)

    def _on_progress(self, event: ProgressEvent):
        if self._progress is None:
            return
        value = event.value
        message = event.message
        running, _ = self._progress.Update(value, message)
        if not running:
            self.cancel_flag.set()
            self._progress.Destroy()
            self._progress = None

    # noinspection PyUnusedLocal
    def _on_progress_show(self, event):
        if self._progress is not None:
            self._progress.Destroy()
            self._progress = None
        if self._completion_callback:
            self._completion_callback()
        elif self.IsModal():
            if self.cancel_flag.is_set():
                self.EndModal(wx.CANCEL)
            else:
                self.EndModal(wx.OK)
        else:
            self.Show(False)
