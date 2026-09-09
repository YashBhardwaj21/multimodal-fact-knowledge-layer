"""Configuration manager."""

import yaml
from pathlib import Path
from typing import Dict, Any


class Config:
    """Configuration manager for the project."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'config.yaml'
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            'ocr': {
                'model_name': 'Qwen/Qwen3-VL-4B-Instruct'
            },
            'storage': {
                'base_dir': 'data/object_store',
                'max_quota_gb': 10
            },
            'paths': {
                'raw_data': 'data/raw',
                'processed_data': 'data/processed',
                'outputs': 'outputs',
                'logs': 'logs'
            }
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def save(self, output_path: str = None):
        """Save configuration to YAML file."""
        output_path = output_path or self.config_path
        with open(output_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False)
