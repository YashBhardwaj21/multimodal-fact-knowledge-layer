"""Image preprocessing utilities for document image enhancement and resizing."""

from typing import Optional, Tuple
import numpy as np


class ImagePreprocessor:
    """Provides document image preprocessing routines including resizing and normalization."""

    def __init__(self, target_size: Optional[Tuple[int, int]] = None):
        self.target_size = target_size

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess an image array."""
        if self.target_size and len(image.shape) >= 2:
            import cv2
            return cv2.resize(image, self.target_size)
        return image
