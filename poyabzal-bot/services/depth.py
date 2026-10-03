"""Chuqurlik (kameragacha masofa) xaritasi — iPhone «portret» rejimi uchun.

Model: Depth-Anything-V2 Small (Apache-2.0 litsenziya, tijoratda bepul).
Birinchi ishga tushishda ~100 MB yuklab olinadi, keyin kompyuterda saqlanadi.
Bir rasmga ~0,5 soniya, ~300 MB xotira.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

MODEL_URL = "https://github.com/fabio-sim/Depth-Anything-ONNX/releases/download/v2.0.0/depth_anything_v2_vits.onnx"
MODEL_SHA256 = "d2b11a11c1d4a12b47608fa65a17ee9a4c605b55ee1730c8e3b526304f2562be"
MODEL_DIR = Path.home() / ".rembg" / "models" / "depth-anything-v2-small"
INPUT_SIZE = 518
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class DepthEstimator:
    def __init__(self) -> None:
        import onnxruntime as ort
        import pooch

        path = pooch.retrieve(
            MODEL_URL, known_hash=f"sha256:{MODEL_SHA256}",
            fname="depth_anything_v2_vits.onnx", path=MODEL_DIR, progressbar=True,
        )
        opts = ort.SessionOptions()
        opts.enable_cpu_mem_arena = False
        opts.enable_mem_pattern = False
        self.session = ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def predict(self, img: Image.Image) -> np.ndarray:
        """0..1 oralig'ida chuqurlik: 1 — kameraga eng yaqin, 0 — eng uzoq. Rasm o'lchamida."""
        rgb = img.convert("RGB")
        x = np.asarray(rgb.resize((INPUT_SIZE, INPUT_SIZE), Image.BICUBIC), dtype=np.float32) / 255.0
        x = ((x - _MEAN) / _STD).transpose(2, 0, 1)[None]
        depth = self.session.run(None, {self.input_name: x})[0][0]
        depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-6)
        resized = Image.fromarray(depth.astype(np.float32)).resize(rgb.size, Image.BILINEAR)
        return np.asarray(resized, dtype=np.float32)
