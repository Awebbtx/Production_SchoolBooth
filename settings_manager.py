"""
Settings Manager for Schoolbooth Application.

Centralizes all settings management with a single source of truth.
Handles loading, saving, defaults, and type conversion.

This production release uses one flat JSON settings format only.
"""

import json
import os
from typing import Any, Dict


class SettingsSchema:
    """Defines all application settings with their defaults and types."""
    
    SETTINGS = {
        # Core settings
        'camera_index': {'default': 0, 'type': int},
        'output_dir': {'default': None, 'type': str},  # Set in init
        'output_auto_purge_enabled': {'default': False, 'type': bool},
        'output_auto_purge_days': {'default': 30, 'type': int},
        'touch_mode': {'default': False, 'type': bool},
        'attendant_mode': {'default': False, 'type': bool},
        
        # Printer settings
        'photo_printer': {'default': '', 'type': str},
        'qr_printer': {'default': '', 'type': str},
        'photo_printing_enabled': {'default': True, 'type': bool},
        'photo_print_access_code': {'default': False, 'type': bool},
        'borderless_photo': {'default': False, 'type': bool},
        'photo_paper_size': {'default': '4x6', 'type': str},
        'photo_quality': {'default': 90, 'type': int},
        'print_template': {'default': 'Default', 'type': str},
        'qr_printing_enabled': {'default': True, 'type': bool},
        'qr_print_access_code': {'default': True, 'type': bool},
        'auto_print_photo': {'default': False, 'type': bool},
        'auto_print_qr': {'default': False, 'type': bool},
        'show_qr_print_preview': {'default': False, 'type': bool},
        'qr_print_mode': {'default': 'Standard Printer', 'type': str},
        
        # COM port
        'com_port': {'default': 'COM1', 'type': str},
        
        # QR settings
        'qr_header': {'default': '', 'type': str},
        'qr_footer': {'default': '', 'type': str},
        'qr_font_size': {'default': 12, 'type': int},
        'qr_module_size': {'default': 3, 'type': int},
        'qr_error_correction': {'default': 'M', 'type': str},
        'text_font_type': {'default': 'A', 'type': str},
        
        # QR paper settings
        'qr_paper_size': {'default': '4x6', 'type': str},
        'qr_margin_top': {'default': 10, 'type': int},
        'qr_margin_left': {'default': 10, 'type': int},
        'qr_margin_right': {'default': 10, 'type': int},
        'qr_margin_bottom': {'default': 10, 'type': int},
        'default_print_message': {'default': 'Scan to view your professional photo', 'type': str},
        
        # Watermark settings
        'watermark_enabled': {'default': False, 'type': bool},
        'watermark_path': {'default': '', 'type': str},
        'watermark_x': {'default': 50.0, 'type': float},
        'watermark_y': {'default': 50.0, 'type': float},
        'watermark_size': {'default': 30.0, 'type': float},
        'watermark_opacity': {'default': 70.0, 'type': float},
        'watermark_remove_bg': {'default': True, 'type': bool},
        'watermark_rotation': {'default': 0.0, 'type': float},
        'watermark_scale': {'default': 1.0, 'type': float},
        'watermark_interactive': {'default': True, 'type': bool},
        'watermark_snap_grid': {'default': True, 'type': bool},
        'watermark_snap_grid_step': {'default': 5, 'type': int},
        'watermark_snap_center': {'default': True, 'type': bool},
        
        # Image correction settings
        'auto_wb': {'default': False, 'type': bool},
        'auto_color': {'default': False, 'type': bool},
        'wb_temp': {'default': 6500, 'type': int},
        'brightness': {'default': 0, 'type': int},
        'contrast': {'default': 0, 'type': int},
        'saturation': {'default': 100, 'type': int},
        'sharpness': {'default': 0, 'type': int},
        'skin_smoothing': {'default': 0, 'type': int},
        'gamma': {'default': 100, 'type': int},
        
        # Image crop and rotation
        'crop_size': {'default': '4x6', 'type': str},
        'rotation': {'default': 0, 'type': int},
        'show_crop_overlay': {'default': True, 'type': bool},
        
        # WordPress API settings
        'wp_url': {'default': '', 'type': str},
        'wp_shared_secret': {'default': '', 'type': str},
        'wp_api_endpoint': {'default': '/wp-json/pta-schoolbooth/v1/ingest', 'type': str},
        'wp_api_timeout': {'default': 20, 'type': int},
        'wp_enroll_username': {'default': '', 'type': str},
        'wp_app_instance_id': {'default': '', 'type': str},
        'wp_link_enabled': {'default': False, 'type': bool},
        
        # HID Device settings
        'hid_device_id': {'default': '', 'type': str},
        'hid_map_capture_image': {'default': '', 'type': str},
        'hid_map_navigate_left': {'default': '', 'type': str},
        'hid_map_navigate_right': {'default': '', 'type': str},
        'hid_map_select': {'default': '', 'type': str},
        
        # Capture label (neutral identifier for photo session/event)
        'capture_label': {'default': 'Session', 'type': str},
    }
    
    # Float keys for special handling during load
    FLOAT_KEYS = {
        'watermark_x', 'watermark_y', 'watermark_size', 
        'watermark_opacity', 'watermark_rotation', 'watermark_scale'
    }


class SettingsManager:
    """
    Centralized settings management.
    
    Single source of truth for all application settings. Handles loading,
    saving, defaults, and type conversion automatically.
    """
    
    def __init__(self, settings_filename: str = 'config.json'):
        """
        Initialize settings manager.
        
        Args:
            settings_filename: Path to settings JSON file
        """
        self.settings_filename = settings_filename
        self._data: Dict[str, Any] = {}
        self._initialize_defaults()
        self.load()
    
    def _initialize_defaults(self):
        """Initialize all settings with their default values."""
        for key, config in SettingsSchema.SETTINGS.items():
            default = config['default']
            
            # Special handling for output_dir
            if key == 'output_dir' and default is None:
                default = os.path.join(os.path.expanduser("~"), "Pictures", "Schoolbooth")
            
            self._data[key] = default
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.
        
        Args:
            key: Setting key
            default: Default value if key not found
            
        Returns:
            Setting value or default
        """
        if key in self._data:
            return self._data[key]
        
        if default is not None:
            return default
        
        # Return schema default if available
        if key in SettingsSchema.SETTINGS:
            schema_default = SettingsSchema.SETTINGS[key]['default']
            if key == 'output_dir' and schema_default is None:
                return os.path.join(os.path.expanduser("~"), "Pictures", "Schoolbooth")
            return schema_default
        
        return None
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a setting value.
        
        Args:
            key: Setting key
            value: Setting value
        """
        if key not in SettingsSchema.SETTINGS:
            print(f"Warning: Unknown setting key '{key}'")
        
        self._data[key] = value
    
    def set_multiple(self, settings_dict: Dict[str, Any]) -> None:
        """
        Set multiple settings at once.
        
        Args:
            settings_dict: Dictionary of key-value pairs
        """
        for key, value in settings_dict.items():
            self.set(key, value)
    
    def update(self, settings_dict: Dict[str, Any]) -> None:
        """
        Update multiple settings at once (dict-like interface).
        
        Args:
            settings_dict: Dictionary of key-value pairs
        """
        self.set_multiple(settings_dict)
    
    def get_all(self) -> Dict[str, Any]:
        """Get a copy of all settings."""
        return self._data.copy()
    
    def load(self) -> bool:
        """
        Load settings from JSON file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(self.settings_filename):
                print(f"Settings file not found: {self.settings_filename}. Using defaults.")
                return False
            
            with open(self.settings_filename, 'r') as f:
                loaded_settings = json.load(f)

            if not isinstance(loaded_settings, dict):
                print("Settings file has invalid structure. Using defaults.")
                return False

            # Flat schema-only load for production.
            for key, value in loaded_settings.items():
                if key not in SettingsSchema.SETTINGS:
                    continue

                expected_type = SettingsSchema.SETTINGS[key]['type']

                try:
                    if expected_type == float and isinstance(value, (int, float)):
                        self._data[key] = float(value)
                    elif expected_type == int and isinstance(value, (int, float)):
                        self._data[key] = int(value)
                    elif expected_type == bool and isinstance(value, bool):
                        self._data[key] = value
                    elif expected_type == str and isinstance(value, str):
                        self._data[key] = value
                    else:
                        self._data[key] = value
                except (ValueError, TypeError) as e:
                    print(f"Warning: Could not convert {key}={value} to {expected_type}: {e}")
            
            return True
        
        except json.JSONDecodeError as e:
            print(f"Error decoding settings file: {e}. Using defaults.")
            return False
        except Exception as e:
            print(f"Error loading settings: {e}. Using defaults.")
            return False
    
    def save(self) -> bool:
        """
        Save all settings to JSON file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.settings_filename) or '.', exist_ok=True)
            
            with open(self.settings_filename, 'w') as f:
                json.dump(self._data, f, indent=4)
            
            return True
        
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False
    
    def reset_to_defaults(self) -> None:
        """Reset all settings to their default values."""
        self._initialize_defaults()
    
    def validate(self, key: str) -> bool:
        """
        Validate that a setting exists in the schema.
        
        Args:
            key: Setting key to validate
            
        Returns:
            True if valid, False otherwise
        """
        return key in SettingsSchema.SETTINGS
    
    def get_schema(self) -> Dict[str, Dict[str, Any]]:
        """Get the complete settings schema."""
        return SettingsSchema.SETTINGS.copy()
    
    def __repr__(self) -> str:
        """String representation of settings manager."""
        return f"SettingsManager(file={self.settings_filename}, settings={len(self._data)})"
    
    def __getitem__(self, key: str) -> Any:
        """Access settings like a dictionary."""
        return self.get(key)
    
    def __setitem__(self, key: str, value: Any) -> None:
        """Set settings like a dictionary."""
        self.set(key, value)
    
    def __contains__(self, key: str) -> bool:
        """Check if a setting exists."""
        return key in self._data
