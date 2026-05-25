"""Visualization 層（Step 7）。

從 algorithm 層 FrameResult 渲染兩條獨立 track：
  - final overlay      → visualization.pipeline_visualizer.PipelineVisualizer
  - debug per stage    → visualization.layers.*

依賴方向：visualization → algorithm / config（只讀）。
Algorithm 層禁止 import 本層（避免反向污染分層）。
"""
