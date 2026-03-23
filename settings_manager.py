"""
Settings Manager for Schoolbooth Application

Centralizes all settings management with a single source of truth.
Handles loading, saving, defaults, and type conversion.

Supports both flat and nested JSON structures with automatic conversion.
Use flat keys like self.settings['camera_index'] or nested access like 
self.settings.get_nested('camera.index')
"""

import json
import os
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum

try:
    from settings_migration import SettingsMigration
except ImportError:
    SettingsMigration = None


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
    
    def __init__(self, settings_filename: str = 'camera_settings.json'):
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
        
        Supports both flat (v1.0) and nested (v2.0) JSON structures.
        Nested structures are flattened for internal use but can be accessed
        via nested keys with get_nested() and set_nested().
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(self.settings_filename):
                print(f"Settings file not found: {self.settings_filename}. Using defaults.")
                return False
            
            with open(self.settings_filename, 'r') as f:
                loaded_settings = json.load(f)
            
            # Check if this is a nested v2.0 structure
            if '_meta' in loaded_settings or any(isinstance(v, dict) for v in loaded_settings.values()):
                # This is nested v2.0 structure, flatten it
                print("Loaded nested v2.0 settings structure")
                self._flatten_and_load_v2(loaded_settings)
            else:
                # This is flat v1.0 structure, load directly
                # Type conversion and validation
                for key, value in loaded_settings.items():
                    if key in SettingsSchema.SETTINGS:
                        expected_type = SettingsSchema.SETTINGS[key]['type']
                        
                        # Type conversion
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
                    else:
                        # Accept unknown keys (may be v2.0 settings)
                        self._data[key] = value
            
            return True
        
        except json.JSONDecodeError as e:
            print(f"Error decoding settings file: {e}. Using defaults.")
            return False
        except Exception as e:
            print(f"Error loading settings: {e}. Using defaults.")
            return False
    
    def _flatten_and_load_v2(self, nested_settings: Dict) -> None:
        """
        Flatten nested v2.0 settings structure and load into _data.
        
        Maps nested keys like 'watermark.interactive' to flat keys
        like 'watermark_interactive' based on schema definitions.
        """
        # Mapping of flat keys to nested paths for v2.0 structure
        NESTED_PATHS = {
            # Camera settings
            'camera_index': ('camera', 'index'),
            'camera_resolution': ('camera', 'resolution'),
            'camera_quality': ('camera', 'quality'),
            'camera_auto_focus': ('camera', 'auto_focus'),
            'camera_focus_mode': ('camera', 'focus_mode'),
            'camera_fps': ('camera', 'fps'),
            
            # Image settings
            'rotation': ('image', 'rotation'),
            'crop_size': ('image', 'crop_size'),
            'show_crop_overlay': ('image', 'show_crop_overlay'),
            'brightness': ('image', 'adjustments', 'brightness'),
            'contrast': ('image', 'adjustments', 'contrast'),
            'saturation': ('image', 'adjustments', 'saturation'),
            'sharpness': ('image', 'adjustments', 'sharpness'),
            'gamma': ('image', 'adjustments', 'gamma'),
            'auto_wb': ('image', 'white_balance', 'auto'),
            'wb_temp': ('image', 'white_balance', 'temperature_kelvin'),
            'auto_color': ('image', 'color_correction', 'auto'),
            
            # Watermark settings
            'watermark_enabled': ('watermark', 'enabled'),
            'watermark_path': ('watermark', 'path'),
            'watermark_x': ('watermark', 'position', 'x'),
            'watermark_y': ('watermark', 'position', 'y'),
            'watermark_size': ('watermark', 'transform', 'size'),
            'watermark_opacity': ('watermark', 'transform', 'opacity'),
            'watermark_rotation': ('watermark', 'transform', 'rotation'),
            'watermark_scale': ('watermark', 'transform', 'scale'),
            'watermark_remove_bg': ('watermark', 'background_removal'),
            'watermark_interactive': ('watermark', 'interactive'),
            'watermark_snap_grid': ('watermark', 'snap_grid'),
            'watermark_snap_grid_step': ('watermark', 'snap_grid_step'),
            'watermark_snap_center': ('watermark', 'snap_center'),
            
            # Output settings
            'output_dir': ('output', 'directory'),
            'output_auto_purge_enabled': ('output', 'auto_purge_enabled'),
            'output_auto_purge_days': ('output', 'auto_purge_days'),
            
            # Printing settings
            'photo_printing_enabled': ('printing', 'photo', 'enabled'),
            'photo_printer': ('printing', 'photo', 'printer'),
            'photo_print_access_code': ('printing', 'photo', 'print_access_code'),
            'borderless_photo': ('printing', 'photo', 'borderless'),
            'photo_paper_size': ('printing', 'photo', 'paper_size'),
            'photo_quality': ('printing', 'photo', 'quality'),
            'print_template': ('printing', 'photo', 'template'),
            'auto_print_photo': ('printing', 'photo', 'auto_print'),
            'qr_printing_enabled': ('printing', 'qr', 'enabled'),
            'qr_printer': ('printing', 'qr', 'printer'),
            'auto_print_qr': ('printing', 'qr', 'auto_print'),
            'show_qr_print_preview': ('printing', 'qr', 'preview'),
            'qr_print_mode': ('printing', 'qr', 'mode'),
            'com_port': ('printing', 'qr', 'com_port'),
            
            # QR code settings
            'qr_header': ('qr_codes', 'design', 'header'),
            'qr_footer': ('qr_codes', 'design', 'footer'),
            'qr_font_size': ('qr_codes', 'design', 'font_size'),
            'qr_module_size': ('qr_codes', 'thermal', 'module_size'),
            'qr_error_correction': ('qr_codes', 'thermal', 'error_correction'),
            'text_font_type': ('qr_codes', 'thermal', 'text_font'),
            'qr_paper_size': ('qr_codes', 'paper', 'size'),
            'qr_margin_top': ('qr_codes', 'paper', 'margins', 'top'),
            'qr_margin_left': ('qr_codes', 'paper', 'margins', 'left'),
            'qr_margin_right': ('qr_codes', 'paper', 'margins', 'right'),
            'qr_margin_bottom': ('qr_codes', 'paper', 'margins', 'bottom'),
            
            # Interface settings
            'touch_mode': ('interface', 'touch_mode'),
            'attendant_mode': ('interface', 'attendant_mode'),
            'default_print_message': ('interface', 'default_print_message'),
            'capture_label': ('interface', 'capture_label'),
            
            # WordPress settings
            'wp_link_enabled': ('wordpress', 'integration_enabled'),
            'wp_url': ('wordpress', 'url'),
            'wp_shared_secret': ('wordpress', 'shared_secret'),
            'wp_api_endpoint': ('wordpress', 'api', 'endpoint'),
            'wp_api_timeout': ('wordpress', 'api', 'timeout'),
            'wp_enroll_username': ('wordpress', 'enrollment', 'username'),
            
            # HID settings
            'hid_device_id': ('input', 'hid_device_id'),
            'hid_map_capture_image': ('input', 'hid_mappings', 'capture_image'),
            'hid_map_navigate_left': ('input', 'hid_mappings', 'navigate_left'),
            'hid_map_navigate_right': ('input', 'hid_mappings', 'navigate_right'),
            'hid_map_select': ('input', 'hid_mappings', 'select'),
        }
        
        # Try to extract each flat key from nested structure
        for flat_key, nested_path in NESTED_PATHS.items():
            value = self._get_nested_value(nested_settings, nested_path)
            if value is not None:
                self._data[flat_key] = value
    
    def _get_nested_value(self, data: Dict, path: tuple) -> Any:
        """Extract value from nested dictionary using a path tuple."""
        current = data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
    
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
    
    def get_nested(self, key_path: str, default: Any = None) -> Any:
        """Get value using dot notation for nested keys.
        
        Examples:
            self.settings.get_nested('camera.resolution')
            self.settings.get_nested('printing.qr.mode')
            
        Args:
            key_path: Dot-separated path (e.g., 'camera.resolution')
            default: Default value if not found
            
        Returns:
            Value at path or default
        """
        keys = key_path.split('.')
        current = self._data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return default
            else:
                return default
        return current if current is not None else default
    
    def set_nested(self, key_path: str, value: Any) -> None:
        """Set value using dot notation for nested keys.
        
        Examples:
            self.settings.set_nested('camera.resolution', '1920x1080')
            self.settings.set_nested('printing.qr.mode', 'thermal')
            
        Args:
            key_path: Dot-separated path
            value: Value to set
        """
        keys = key_path.split('.')
        current = self._data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
    
    def migrate_to_nested(self) -> bool:
        """Migrate flat settings to nested v2.0 structure.
        
        Converts old flat key structure to new hierarchical structure
        using the migration mapping. Backs up old file first.
        
        Returns:
            True if migration successful, False otherwise
        """
        if not SettingsMigration:
            print("Warning: settings_migration module not available. Skipping migration.")
            return False
        
        try:
            # Check if already migrated (has _meta)
            if '_meta' in self._data:
                return True
            
            # Backup old file
            backup_file = self.settings_filename + '.bak'
            if os.path.exists(self.settings_filename):
                with open(self.settings_filename, 'r') as f:
                    old_data = json.load(f)
                with open(backup_file, 'w') as f:
                    json.dump(old_data, f, indent=4)
                print(f"Settings backup created: {backup_file}")
            
            # Migrate data
            migrated = SettingsMigration.flatten_old_to_new(self._data)
            self._data = migrated
            
            # Save migrated settings
            self.save()
            print("Settings migrated to v2.0 structure successfully")
            return True
            
        except Exception as e:
            print(f"Error during migration: {e}")
            return False
    
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
