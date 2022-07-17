import threading
from time import sleep
import wx
import wx.lib.newevent as ne


ProgressEvent, EVT_ID_PROGRESS = ne.NewEvent()


class Progress(wx.ProgressDialog):
    def __init__(self, title: str, message: str, **kwargs):
        super().__init__(title, message, **kwargs)

        self._id_ref = wx.NewIdRef()

        self.Bind(EVT_ID_PROGRESS, self._on_evt, id=self._id_ref.GetId())

    def message(self, value: int, message: str) -> None:
        event = ProgressEvent(value=value, msg=message)
        event.SetId(self._id_ref.GetId())
        self.QueueEvent(event)

    def _on_evt(self, event: ProgressEvent):
        self.Update(event.value, event.msg)


if __name__ == '__main__':
    app = wx.App()
    frame = wx.Frame(None, title='Progress Test')
    panel = wx.Panel(frame)
    button = wx.Button(panel, label='Run')
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(button)
    panel.SetSizer(sizer)
    panel.Fit()

    CompletionEvent, EVT_ID_COMPLETION = ne.NewEvent()

    def _on_completion(event):
        print('Thread complete')
        if event.progress.WasCancelled():
            event.progress.Destroy()
        frame.Show(True)

    frame.Bind(EVT_ID_COMPLETION, _on_completion)

    prog_max = 100

    def _on_button(event):
        frame.Show(False)
        msg = u'\u00a0' * 40
        progress = Progress('Progress Test', message=msg, parent=frame,
                            style=wx.PD_APP_MODAL | wx.PD_CAN_ABORT, maximum=prog_max)
        print('After progress')

        def _run():
            print('Thread started')
            for i in range(0, prog_max + 1, 10):
                if progress.WasCancelled():
                    break
                progress.message(i, f'{i}% complete')
                sleep(1)
            frame.QueueEvent(CompletionEvent(progress=progress))

        thread = threading.Thread(target=_run)
        thread.start()


    button.Bind(wx.EVT_BUTTON, _on_button)

    frame.Show()
    app.MainLoop()

