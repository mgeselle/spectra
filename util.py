from os import PathLike
from pathlib import Path
from typing import MutableSequence, Union


def find_input_files(input_dir: Union[str, bytes, PathLike], input_basename) -> MutableSequence[Path]:
    input_path = Path(input_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"Input directory {input_dir} doesn't exist")
    input_files = []
    if input_basename.endswith('.fits') or input_basename.endswith('.fit'):
        input_files.append(input_path / input_basename)
    else:
        for candidate in input_path.glob(input_basename + '*.*'):
            if candidate.is_file() and candidate.suffix in ('.fits', '.fit'):
                input_files.append(candidate)
    return input_files


def dir_to_path(in_dir: str) -> (Path, None):
    if in_dir is None:
        return None
    in_dir_l = in_dir.replace('~', str(Path.home()))
    return Path(in_dir_l)
