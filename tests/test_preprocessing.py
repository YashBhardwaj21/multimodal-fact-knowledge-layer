"""Unit tests for image preprocessing."""

import pytest
import numpy as np
from pathlib import Path
from src.preprocessing import ImagePreprocessor


def test_image_preprocessor_initialization():
    """Test ImagePreprocessor initialization."""
    preprocessor = ImagePreprocessor()
    assert preprocessor is not None
    assert preprocessor.target_size is None


def test_image_preprocessor_with_target_size():
    """Test ImagePreprocessor with target size."""
    preprocessor = ImagePreprocessor(target_size=(800, 600))
    assert preprocessor.target_size == (800, 600)
