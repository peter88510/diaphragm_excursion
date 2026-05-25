"""RunBundle：聚合所有 per-layer config，避免 main.py 散落 instantiate。

設計取向：
- 純聚合，不重新發明 cfg 欄位；sub-cfg 內部結構不變
- 每個 layer 仍只認自己 cfg type（visualization 吃 VisualizationConfig，
  不吃 RunBundle）→ functional independence 保留
- for_phase classmethod 只代 detection（與 DiaphragmDetectionConfig.for_phase 對齊）；
  其他 cfg 用 default；未來需要跨 cfg phase preset 再擴
"""
from dataclasses import dataclass, field

from config.diaphragm_detection_config import DiaphragmDetectionConfig, Phase
from config.dicom_crop_config import DicomCropConfig
from config.excursion_config import ExcursionConfig
from config.motion_curve_config import MotionCurveConfig
from config.multiframe_config import MultiframeConfig
from config.paddleseg_config import PaddleSegSegmenterConfig
from config.roi_band_config import RoiBandConfig
from config.visualization_config import VisualizationConfig


@dataclass
class RunBundle:
    segmenter: PaddleSegSegmenterConfig = field(default_factory=PaddleSegSegmenterConfig)
    dicom_crop: DicomCropConfig = field(default_factory=DicomCropConfig)
    detection: DiaphragmDetectionConfig = field(default_factory=DiaphragmDetectionConfig)
    roi_band: RoiBandConfig = field(default_factory=RoiBandConfig)
    motion_curve: MotionCurveConfig = field(default_factory=MotionCurveConfig)
    excursion: ExcursionConfig = field(default_factory=ExcursionConfig)
    viz: VisualizationConfig = field(default_factory=VisualizationConfig)
    multiframe: MultiframeConfig = field(default_factory=MultiframeConfig)

    @classmethod
    def for_phase(cls, phase: Phase) -> "RunBundle":
        """目前只代 detection cfg；其他 sub-cfg 用 default。"""
        return cls(detection=DiaphragmDetectionConfig.for_phase(phase))
