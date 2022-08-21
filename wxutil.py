from pathlib import Path
import re
from typing import Union, Sequence
import wx
from config import Config


def size_text_by_chars(tc: Union[wx.TextCtrl, wx.ComboBox, wx.Control], num_chars: int):
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


def select_file(parent: wx.Window) -> Union[None, str]:
    initial_dir = str(Config.get().get_last_directory())
    with wx.FileDialog(parent, message='Open FITS file', defaultDir=initial_dir,
                       wildcard='FITS files (*.fit;*.fits)|*.fit;*.fits',
                       style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
        dlg_res = dlg.ShowModal()
        if dlg_res == wx.ID_CANCEL:
            return None
        result = dlg.GetPath()
        result_path = Path(result)
        Config.get().set_last_directory(result_path.parent)
        return result


def ensure_dir_exists(the_dir: str, role: str, parent: wx.Window) -> Union[Path, None]:
    """Ensure that a directory exists and show a message box if it doesn't.

    :param str the_dir: directory to check
    :param str role: directory role. Used for the message in the message box
    :param parent: parent window for the message box
    :return None | Path: returns a Path object, if the directory exists, None otherwise
    """
    path = Path(the_dir.replace('~', str(Path.home())))
    if path.exists():
        return path

    with wx.MessageDialog(parent, f"{role.capitalize()} directory doesn't exist.", caption='Missing Directory',
                          style=wx.OK | wx.ICON_ERROR) as dlg:
        dlg.ShowModal()
    return None


def create_dir(the_dir: str, role: str, parent: wx.Window) -> Union[Path, None]:
    """Creates a directory if it doesn't exist and shows a message box, if creation fails

    :param str the_dir: directory to create
    :param str role: directory role. Used for the message in the message box
    :param parent: parent window for the message box
    :return None | Path: returns a Path object, if the directory exists, None otherwise
    """
    path = Path(the_dir.replace('~', str(Path.home())))
    if path.exists():
        return path

    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError as err:
        with wx.MessageDialog(parent, f'Error creating {role} directory: {err}',
                              caption='Error Creating', style=wx.OK | wx.ICON_ERROR) as dlg:
            dlg.ShowModal()
            return None

    return path


def find_files_by_pattern(dir_path: Path, pattern: str, role: str, parent: wx.Window,
                          must_exist: bool = True, unique: bool = False,
                          extensions=('.fit', '.fits')) -> Union[None | Path | Sequence[Path]]:
    if unique:
        file_word = 'file'
    else:
        file_word = 'files'
    if not dir_path.exists():
        with wx.MessageDialog(parent, f"Directory for {role} {file_word} doesn't exist.",
                              caption='Missing Directory',
                              style=wx.OK | wx.ICON_ERROR) as dlg:
            dlg.ShowModal()
            return None
    match_pattern = pattern
    suffix_re = ')|('.join(extensions)
    suffix_re.replace('.', '[.]')
    suffix_re = '.*((' + suffix_re + '))$'
    if not re.fullmatch(suffix_re, match_pattern) and not match_pattern.endswith('.*'):
        match_pattern = match_pattern + '.*'
    matches = [f for f in dir_path.glob(match_pattern) if f.suffix in extensions]
    if not matches and must_exist:
        with wx.MessageDialog(parent, f"Pattern for {role} {file_word} doesn't match anything.",
                              caption='No Match',
                              style=wx.OK | wx.ICON_ERROR) as dlg:
            dlg.ShowModal()
            return None
    if unique and len(matches) > 1:
        with wx.MessageDialog(parent, f"Pattern for {role} {file_word} isn't unique.",
                              caption='Not Unique',
                              style=wx.OK | wx.ICON_ERROR) as dlg:
            dlg.ShowModal()
            return None
    if unique:
        if matches:
            return matches[0]
        else:
            return None
    else:
        return matches
