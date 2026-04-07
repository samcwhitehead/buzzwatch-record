#!/usr/bin/env python3
"""
Configuration management for video recorder experiments
"""

import json
from pathlib import Path
from datetime import datetime

# =============================================================================
# Defaults
# =============================================================================
CONFIG_SCHEMA  = {

    "camera": {  # this dict for args that can be passed directly to rpicam as name/value pairs
        "width": 1920,
        "height": 1080,
        "bitrate": 10000000,
        "framerate": 30,
        "autofocus-mode": 'manual',
        "lens-position": 6.5,  # In diopters
        "shutter": 5000,  # in microseconds(?)
        "analoggain": 1.5,
    },

    "recording": {
        "chunk_minutes": 20,
    },

    "storage": {
        "local_path": "/home/samwhitehead/Videos",
        "external_path": "/media/samwhitehead/T7 Shield/buzzwatch_videos",
        "transfer_hours": 12.0,
        "cleanup_days": 30,
        "file_ext": '.mp4',
    },

    # "display": {
    #     "preview": False
    # },
    #
    # "advanced": {
    #     "rpicam_config_file": None,
    #     "additional_rpicam_args": []
    # }
}


# =============================================================================
# Class
# =============================================================================
class ExperimentConfig:
    """Manage experiment configurations"""

    @staticmethod
    def get_defaults():
        """
        Get default values for all parameters

        Returns:
            dict: Nested dictionary of default values organized by section
        """
        defaults = {}
        for section, params in CONFIG_SCHEMA.items():
            defaults[section] = {}
            for param_name, param_info in params.items():
                defaults[section][param_name] = param_info
        return defaults

    @staticmethod
    def get_default(section, param):
        """
        Get default value for a specific parameter

        Args:
            section: Section name (e.g., 'recording', 'camera')
            param: Parameter name (e.g., 'bitrate', 'sharpness')

        Returns:
            Default value for the parameter, or None if not found
        """
        return CONFIG_SCHEMA.get(section, {}).get(param, {}).get("default")

    @staticmethod
    def create_template():
        """Create a template configuration file"""
        config = {
            'info': {
                "experiment_name": "My Experiment",
                "date_created": datetime.now().strftime("%Y-%m-%d"),
                "notes": "Description of this experiment"
            }
        }

        # Start with defaults
        defaults = ExperimentConfig.get_defaults()

        # Add sections with defaults (or all parameters if include_all)
        for section, params in defaults.items():
            if section not in config:
                config[section] = {}

            for param_name, default_value in params.items():
                # Skip if already set by preset
                if param_name in config[section]:
                    continue

                # Only include parameters with non-None defaults unless include_all is True
                if default_value is not None:
                    config[section][param_name] = default_value

        # with open(filepath, 'w') as f:
        #     json.dump(config, f, indent=2)
        # print(f"Template configuration created: {filepath}")

        return config

    @staticmethod
    def load(filepath):
        """Load configuration from JSON file"""
        with open(filepath, 'r') as f:
            config = json.load(f)
        return config

    @staticmethod
    def save(config, filepath):
        """Save configuration to JSON file with usage timestamp"""
        config['info']['last_used'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)

    @staticmethod
    def validate(config):
        """Validate configuration has required fields"""
        required_sections = ['recording', 'storage', 'camera']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required section: {section}")

        required_recording = ['chunk_minutes', 'resolution']
        for field in required_recording:
            if field not in config['recording']:
                raise ValueError(f"Missing required recording field: {field}")

        required_camera = ['bitrate', 'framerate']
        for field in required_camera:
            if field not in config['camera']:
                raise ValueError(f"Missing required camera field: {field}")

        return True

    @staticmethod
    def merge_with_defaults(config):
        """
        Merge configuration with defaults, filling in missing values

        Args:
            config: Partial configuration dictionary

        Returns:
            Complete configuration with defaults filled in
        """
        defaults = ExperimentConfig.get_defaults()
        merged = defaults.copy()

        # Deep merge config into defaults
        for section, params in config.items():
            if section in merged and isinstance(params, dict):
                merged[section].update(params)
            else:
                merged[section] = params

        return merged

    @staticmethod
    def get_all_params(config):
        """Get a flat dictionary of all parameters with their metadata"""
        params = {}
        for section, section_params in config.items():
            if isinstance(section_params, dict):
                for param_name, param_info in section_params.items():
                    full_name = f"{section}.{param_name}"
                    params[full_name] = param_info
            else:
                params[section] = section_params
        return params

    @staticmethod
    def get_arg_value(config, arg_name):
        """
        Get the value of a given argument in a config dict
        (basically just loops over sections for us)
        
        Args:
            config: configuration dictionary, as in CONFIG_SCHEMA
            arg_name: str, name of the argument we want a value for

        Returns:
            val: value of argument 'arg_name'
        """
        val = None
        for section, section_params in config.items():
            for param_name, param_info in section_params.items():
                if param_name == arg_name:
                    val = config[section][param_name]
                    return val
        return val

# =============================================================================
# Config manager
# =============================================================================
class ConfigManager:
    """Helper class for managing nested configuration"""

    @staticmethod
    def deep_update(base_dict, update_dict):
        """
        Recursively merge update_dict into base_dict
        Handles arbitrary nesting depth
        """
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                ConfigManager.deep_update(base_dict[key], value)
            else:
                base_dict[key] = value
        return base_dict

    @staticmethod
    def set_value(dictionary, path, value):
        """
        Set value using dot notation path
        Creates intermediate dicts if they don't exist

        Examples:
            set_value(config, 'recording.bitrate', 15000000)
            set_value(config, 'camera.settings.awb', 'daylight')
        """
        keys = path.split('.')
        current = dictionary

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    @staticmethod
    def get_value(dictionary, path, default=None):
        """
        Get value using dot notation path
        Returns default if path doesn't exist

        Examples:
            get_value(config, 'recording.bitrate')
            get_value(config, 'camera.settings.awb', default='auto')
        """
        keys = path.split('.')
        current = dictionary

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    @staticmethod
    def has_value(dictionary, path):
        """Check if a path exists in the dictionary"""
        keys = path.split('.')
        current = dictionary

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return False

        return True

    @staticmethod
    def delete_value(dictionary, path):
        """Delete a value at the given path"""
        keys = path.split('.')
        current = dictionary

        for key in keys[:-1]:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return False  # Path doesn't exist

        if keys[-1] in current:
            del current[keys[-1]]
            return True
        return False

# =============================================================================
# Convenience functions for importing
# =============================================================================

def get_default_bitrate():
    """Get default bitrate"""
    return ExperimentConfig.get_default('camera', 'bitrate')

def get_default_resolution():
    """Get default resolution"""
    return ExperimentConfig.get_default('recording', 'resolution')

def get_default_framerate():
    """Get default framerate"""
    return ExperimentConfig.get_default('camera', 'framerate')

# =============================================================================
# Main
# =============================================================================
if __name__ == "__main__":
    # Create example config
    config = ExperimentConfig.create_template()