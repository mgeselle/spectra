from astropy.coordinates import EarthLocation
from astropy.table import Table
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from threading import Lock
from typing import List, Union, Sequence, Tuple
import wx


@dataclass
class CameraConfig:
    ron: float
    gain: float


@dataclass
class ObsLocation:
    location: EarthLocation
    active: bool


class Config:
    _class_lock = Lock()
    _config = None

    def __init__(self):
        self._lock = Lock()
        self._config: wx.ConfigBase = wx.ConfigBase.Get()

    def get_camera_configs(self) -> List[str]:
        result = []
        try:
            self._lock.acquire()
            old_path = self._cd_cam_cfg_path()
            more, value, index = self._config.GetFirstGroup()
            if more and value != '':
                result.append(value)
            while more:
                more, value, index = self._config.GetNextGroup(index)
                if value != '':
                    result.append(value)
            self._config.SetPath(old_path)
            return result
        finally:
            if self._lock.locked():
                self._lock.release()

    def get_camera_config(self, name: str) -> Union[None, CameraConfig]:
        try:
            self._lock.acquire()
            old_path = self._cd_cam_cfg_path()
            result = None
            if self._config.HasGroup(name):
                self._config.SetPath(name)
                ron = self._config.ReadFloat('ron')
                gain = self._config.ReadFloat('gain')
                result = CameraConfig(ron, gain)
            self._config.SetPath(old_path)
            return result
        finally:
            if self._lock.locked():
                self._lock.release()

    def save_camera_config(self, name: str, cfg: CameraConfig):
        try:
            self._lock.acquire()
            old_path = self._cd_cam_cfg_path()
            self._config.SetPath(name)
            self._config.WriteFloat('ron', cfg.ron)
            self._config.WriteFloat('gain', cfg.gain)
            self._config.SetPath(old_path)
            self._config.Flush()
        finally:
            if self._lock.locked():
                self._lock.release()

    def delete_camera_config(self, name: str):
        try:
            self._lock.acquire()
            old_path = self._cd_cam_cfg_path()
            if self._config.HasGroup(name):
                self._config.DeleteGroup(name)
            self._config.SetPath(old_path)
            self._config.Flush()
        finally:
            if self._lock.locked():
                self._lock.release()

    def _cd_cam_cfg_path(self) -> str:
        old_path = self._config.GetPath()
        self._config.SetPath('/Camera')
        return old_path

    def get_last_directory(self) -> Path:
        try:
            self._lock.acquire()
            return Path(self._config.Read('/Global/LastDir', str(Path.home())))
        finally:
            if self._lock.locked():
                self._lock.release()

    def set_last_directory(self, last_dir: Union[str, bytes, PathLike]):
        try:
            self._lock.acquire()
            self._config.Write('/Global/LastDir', str(last_dir))
            self._config.Flush()
        finally:
            if self._lock.locked():
                self._lock.release()

    def set_used_lines(self, used_lines: str):
        try:
            self._lock.acquire()
            self._config.Write('/Calib/UseLines', used_lines)
            self._config.Flush()
        finally:
            if self._lock.locked():
                self._lock.release()

    def get_used_lines(self) -> str:
        try:
            self._lock.acquire()
            return self._config.Read('/Calib/UseLines', 'Ne I')
        finally:
            if self._lock.locked():
                self._lock.release()

    def set_line_limits(self, lower: int, upper: int):
        try:
            self._lock.acquire()
            self._config.WriteInt('/Calib/Low', lower)
            self._config.WriteInt('/Calib/High', upper)
            self._config.Flush()
        finally:
            if self._lock.locked():
                self._lock.release()

    def get_line_limits(self) -> Tuple[int, int]:
        try:
            self._lock.acquire()
            return self._config.ReadInt('/Calib/Low', 3000), self._config.ReadInt('/Calib/High', 10000)
        finally:
            if self._lock.locked():
                self._lock.release()

    @staticmethod
    def get():
        try:
            Config._class_lock.acquire()
            if Config._config is None:
                Config._config = Config()
        finally:
            if Config._class_lock.locked():
                Config._class_lock.release()
        return Config._config

    @staticmethod
    def get_calib_line_names() -> Sequence[str]:
        cfg_dir = Config._get_calib_dir()
        if not cfg_dir.exists():
            return ()
        return [x.stem.replace('_', ' ') for x in cfg_dir.glob('*.fits')]

    @staticmethod
    def get_calib_table(name: str) -> Union[None, Table]:
        file = Config._get_calib_dir() / (name.replace(' ', '_') + '.fits')
        if file.exists():
            return Table.read(file)
        return None

    @staticmethod
    def save_calib_table(name: str, table: Table):
        ini_dir = Config._get_calib_dir()
        ini_dir.mkdir(parents=True, exist_ok=True)
        file = ini_dir / (name.replace(' ', '_') + '.fits')
        table.write(file)

    @staticmethod
    def _get_calib_dir():
        user_config_dir = wx.StandardPaths.Get().GetUserDataDir()
        user_config_path = Path(user_config_dir)
        if user_config_path.exists() and not user_config_path.is_dir():
            user_config_path = Path(user_config_dir + '_data')
        return user_config_path / 'calib'