"""Visualization layer renderers（per-stage debug 圖）。

每個 renderer 自帶 should_save_debug() gate，caller 可無條件呼叫；
disabled / 該 stage 未開時 renderer 立即返回，不做任何 I/O。
"""
