"""對外 input 入口：load(path) → FrameSequence。

依路徑類型自動分派到對應 reader：
- 資料夾                     → png_reader.read_directory
- 單一 .dcm / .DICOM          → dicom_reader.read（內部判斷 single / multi frame）
- 單一 .png / .jpg / 等       → png_reader.read_file

caller 不必判斷檔案類型，也不必認識個別 reader 模組。
"""
import os

from input.frame_sequence import FrameSequence
from input.readers import dicom_reader, png_reader


_DICOM_SUFFIX = ('.dcm', '.dicom')
_IMAGE_SUFFIX = ('.png', '.jpg', '.jpeg', '.bmp')


def load(path: str) -> FrameSequence:
    if os.path.isdir(path):
        return png_reader.read_directory(path)

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Path not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext in _DICOM_SUFFIX:
        return dicom_reader.read(path)
    if ext in _IMAGE_SUFFIX:
        return png_reader.read_file(path)

    raise ValueError(
        f"Unsupported file extension: {ext!r}. "
        f"Supported: DICOM {_DICOM_SUFFIX}, image {_IMAGE_SUFFIX}"
    )
