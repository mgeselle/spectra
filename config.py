import astropy.units as u
import wx

from astropy.coordinates import EarthLocation, Latitude, Longitude
from astropy.table import Table
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from threading import Lock
from typing import List, Union, Sequence, Tuple


@dataclass
class CameraConfig:
    ron: float
    gain: float


@dataclass
class TelescopeConfig:
    aperture: int
    focal_length: int


@dataclass
class SpectrometerConfig:
    type: str
    lines_mm: int


@dataclass
class AavsoConfig:
    telescope: str
    spectrometer: str
    ccd: str


class Config:
    _class_lock = Lock()
    _config = None

    def __init__(self):
        self._lock = Lock()
        self._config: wx.ConfigBase = wx.ConfigBase.Get()

    def get_camera_configs(self) -> List[str]:
        return self._get_config_names('/Camera')

    def get_camera_config(self, name: str) -> Union[None, CameraConfig]:
        try:
            self._lock.acquire()
            old_path = self._cd_cfg_path('/Camera')
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
            old_path = self._cd_cfg_path('/Camera')
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
            old_path = self._cd_cfg_path('/Camera')
            if self._config.HasGroup(name):
                self._config.DeleteGroup(name)
            self._config.SetPath(old_path)
            self._config.Flush()
        finally:
            if self._lock.locked():
                self._lock.release()

    def _cd_cfg_path(self, path: str) -> str:
        old_path = self._config.GetPath()
        self._config.SetPath(path)
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

    def get_location(self, name: str) -> Union[None, EarthLocation]:
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Location')
            if not self._config.HasGroup(name):
                return None
            self._config.SetPath(name)
            latitude = Latitude(self._config.Read('Lat'), u.deg)
            longitude = Longitude(self._config.Read('Lon'), u.deg)
            height = self._config.ReadInt('Ht')
            return EarthLocation(lat=latitude, lon=longitude, height=height * u.m)
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def save_location(self, name: str, location: EarthLocation):
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Location')
            self._config.SetPath(name)
            self._config.Write('Lat', location.lat.to_string())
            self._config.Write('Lon', location.lon.to_string())
            self._config.WriteFloat('Ht', location.height.value)
            self._config.Flush()
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def delete_location(self, name: str):
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Location')
            if self._config.HasGroup(name):
                self._config.DeleteGroup(name)
                self._config.Flush()
        finally:
            self._config.SetPath(old_path)

    def get_location_names(self):
        return self._get_config_names('/Location')

    def get_telescope_config(self, name: str) -> Union[None, TelescopeConfig]:
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Telescope')
            if self._config.HasGroup(name):
                self._config.SetPath(name)
                focal_length = self._config.ReadInt('f')
                aperture = self._config.ReadInt('D')
                return TelescopeConfig(aperture, focal_length)
            else:
                return None
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def save_telescope_config(self, name: str, telescope_config: TelescopeConfig):
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Telescope')
            self._config.SetPath(name)
            self._config.WriteInt('f', telescope_config.focal_length)
            self._config.WriteInt('D', telescope_config.aperture)
            self._config.Flush()
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def delete_telescope_config(self, name: str):
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Telescope')
            if self._config.HasGroup(name):
                self._config.DeleteGroup(name)
                self._config.Flush()
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def get_telescope_config_names(self):
        return self._get_config_names('/Telescope')

    def get_spectro_config(self, name: str) -> Union[None, SpectrometerConfig]:
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Spectrometer')
            if self._config.HasGroup(name):
                self._config.SetPath(name)
                s_type = self._config.Read('type')
                lines_mm = self._config.ReadInt('lines')
                return SpectrometerConfig(s_type, lines_mm)
            else:
                return None
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def save_spectro_config(self, name: str, s_config: SpectrometerConfig):
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Spectrometer')
            self._config.SetPath(name)
            self._config.Write('type', s_config.type)
            self._config.WriteInt('lines', s_config.lines_mm)
            self._config.Flush()
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def delete_spectro_config(self, name):
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Spectrometer')
            if self._config.HasGroup(name):
                self._config.DeleteGroup(name)
                self._config.Flush()
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def get_spectro_config_names(self) -> List[str]:
        return self._get_config_names('/Spectrometer')

    def get_aavso_config(self, name: str) -> Union[None, AavsoConfig]:
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Aavso')
            if self._config.HasGroup(name):
                self._config.SetPath(name)
                telescope = self._config.Read('scope')
                spectrometer = self._config.Read('spectro')
                ccd = self._config.Read('ccd')
                return AavsoConfig(telescope, spectrometer, ccd)
            else:
                return None
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def save_aavso_config(self, name: str, aavso_cfg: AavsoConfig):
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Aavso')
            self._config.SetPath(name)
            self._config.Write('scope', aavso_cfg.telescope)
            self._config.Write('spectro', aavso_cfg.spectrometer)
            self._config.Write('ccd', aavso_cfg.ccd)
            self._config.Flush()
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def delete_aavso_config(self, name: str):
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path('/Aavso')
            if self._config.HasGroup(name):
                self._config.DeleteGroup(name)
                self._config.Flush()
        finally:
            self._config.SetPath(old_path)
            self._lock.release()

    def get_aavso_config_names(self) -> List[str]:
        return self._get_config_names('/Aavso')

    def _get_config_names(self, parent_path: str) -> List[str]:
        result = []
        self._lock.acquire()
        old_path = None
        try:
            old_path = self._cd_cfg_path(parent_path)
            more, value, index = self._config.GetFirstGroup()
            if more and value != '':
                result.append(value)
            while more:
                more, value, index = self._config.GetNextGroup(index)
                if value != '':
                    result.append(value)
            return result
        finally:
            self._config.SetPath(old_path)
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
