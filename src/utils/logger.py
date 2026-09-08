"""Logging setup and configuration."""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(log_dir: str = 'logs', log_level: int = logging.INFO):
    """Initialize system logger with file and stream handlers."""
    log_dir = Path(log_dir)
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'app_{timestamp}.log'

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized: {log_file}")
    return logger
