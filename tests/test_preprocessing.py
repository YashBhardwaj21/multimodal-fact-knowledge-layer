import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
import numpy as np
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
