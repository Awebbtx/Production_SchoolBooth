"""
Settings Migration Helper

Provides backward compatibility between the old flat settings structure
and the new hierarchical structure (v2.0).

Maps old flat keys to new nested paths transparently.
"""

from typing import Dict, Any, Tuple, List


class SettingsMigration:
    """Maps old flat settings keys to new nested paths."""
    
    # Old flat key → (new nested path as tuple, default value)
    # Path tuples enable safe nested access: ('camera', 'index') → settings['camera']['index']
    KEY_MAPPING = {
        # Camera settings
        'camera_index': (('camera', 'index'), 0),
        'camera_resolution': (('camera', 'resolution'), '1920x1080'),
        'camera_quality': (('camera', 'quality'), 'high'),
        'camera_auto_focus': (('camera', 'auto_focus'), True),
        'camera_focus_mode': (('camera', 'focus_mode'), 'continuous'),
        'camera_fps': (('camera', 'fps'), 30),
        
        # Image adjustments
        'brightness': (('image', 'adjustments', 'brightness'), 0),
        'contrast': (('image', 'adjustments', 'contrast'), 0),
        'saturation': (('image', 'adjustments', 'saturation'), 100),
        'sharpness': (('image', 'adjustments', 'sharpness'), 0),
        'skin_smoothing': (('image', 'adjustments', 'skin_smoothing'), 0),
        'gamma': (('image', 'adjustments', 'gamma'), 100),
        'rotation': (('image', 'rotation'), 0),
        'crop_size': (('image', 'crop_size'), '4x6'),
        'show_crop_overlay': (('image', 'show_crop_overlay'), True),
        
        # White balance
        'auto_wb': (('image', 'white_balance', 'auto'), False),
        'wb_temp': (('image', 'white_balance', 'temperature_kelvin'), 6500),
        
        # Color correction
        'auto_color': (('image', 'color_correction', 'auto'), False),
        
        # Watermark
        'watermark_enabled': (('watermark', 'enabled'), False),
        'watermark_path': (('watermark', 'path'), ''),
        'watermark_x': (('watermark', 'position', 'x'), 50.0),
        'watermark_y': (('watermark', 'position', 'y'), 50.0),
        'watermark_size': (('watermark', 'transform', 'size'), 30.0),
        'watermark_opacity': (('watermark', 'transform', 'opacity'), 70.0),
        'watermark_rotation': (('watermark', 'transform', 'rotation'), 0.0),
        'watermark_scale': (('watermark', 'transform', 'scale'), 1.0),
        'watermark_remove_bg': (('watermark', 'background_removal'), True),
        
        # Output
        'output_dir': (('output', 'directory'), './output'),
        
        # Photo printing
        'photo_printer': (('printing', 'photo', 'printer'), ''),
        'photo_printing_enabled': (('printing', 'photo', 'enabled'), True),
        'photo_print_access_code': (('printing', 'photo', 'print_access_code'), False),
        'auto_print_photo': (('printing', 'photo', 'auto_print'), False),
        'borderless_printing': (('printing', 'photo', 'borderless'), False),
        
        # QR printing
        'qr_printer': (('printing', 'qr', 'printer'), ''),
        'qr_printing_enabled': (('printing', 'qr', 'enabled'), True),
        'qr_print_access_code': (('printing', 'qr', 'print_access_code'), True),
        'auto_print_qr': (('printing', 'qr', 'auto_print'), False),
        'show_qr_print_preview': (('printing', 'qr', 'preview'), False),
        'qr_print_mode': (('printing', 'qr', 'mode'), 'standard'),
        'com_port': (('printing', 'qr', 'com_port'), 'COM1'),
        
        # QR design
        'qr_header': (('qr_codes', 'design', 'header'), ''),
        'qr_footer': (('qr_codes', 'design', 'footer'), ''),
        'qr_font_size': (('qr_codes', 'design', 'font_size'), 12),
        
        # QR thermal
        'qr_module_size': (('qr_codes', 'thermal', 'module_size'), 3),
        'qr_error_correction': (('qr_codes', 'thermal', 'error_correction'), 'M'),
        'text_font_type': (('qr_codes', 'thermal', 'text_font'), 'A'),
        
        # QR paper
        'qr_paper_size': (('qr_codes', 'paper', 'size'), '4x6'),
        'qr_margin_top': (('qr_codes', 'paper', 'margins', 'top'), 10),
        'qr_margin_left': (('qr_codes', 'paper', 'margins', 'left'), 10),
        'qr_margin_right': (('qr_codes', 'paper', 'margins', 'right'), 10),
        'qr_margin_bottom': (('qr_codes', 'paper', 'margins', 'bottom'), 10),
        
        # Interface
        'touch_mode': (('interface', 'touch_mode'), False),
        'attendant_mode': (('interface', 'attendant_mode'), False),
        'default_print_message': (('interface', 'default_print_message'), 'Scan to view your professional photo'),
        
        # WordPress
        'wp_url': (('wordpress', 'url'), ''),
        'wp_shared_secret': (('wordpress', 'shared_secret'), ''),
        'wp_api_endpoint': (('wordpress', 'api', 'endpoint'), '/wp-json/pta-schoolbooth/v1/ingest'),
        'wp_api_timeout': (('wordpress', 'api', 'timeout'), 20),
        'wp_enroll_username': (('wordpress', 'enrollment', 'username'), ''),
        'wp_app_instance_id': (('wordpress', 'enrollment', 'instance_id'), ''),
        'wp_link_enabled': (('wordpress', 'integration_enabled'), False),
        
        # HID
        'hid_device_id': (('input', 'hid_device_id'), None),
        'hid_map_capture_image': (('input', 'hid_mappings', 'capture_image'), ''),
        'hid_map_navigate_left': (('input', 'hid_mappings', 'navigate_left'), ''),
        'hid_map_navigate_right': (('input', 'hid_mappings', 'navigate_right'), ''),
        'hid_map_select': (('input', 'hid_mappings', 'select'), ''),
    }
    
    @staticmethod
    def get_nested(data: Dict[str, Any], path: Tuple[str, ...], default: Any = None) -> Any:
        """Get value from nested dict using tuple path.
        
        Args:
            data: Nested dictionary
            path: Tuple of keys e.g. ('camera', 'index')
            default: Default if path not found
            
        Returns:
            Value at path or default
        """
        current = data
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return default
            else:
                return default
        return current if current is not None else default
    
    @staticmethod
    def set_nested(data: Dict[str, Any], path: Tuple[str, ...], value: Any) -> None:
        """Set value in nested dict using tuple path, creating intermediate dicts as needed.
        
        Args:
            data: Nested dictionary to modify
            path: Tuple of keys e.g. ('camera', 'index')
            value: Value to set
        """
        current = data
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value
    
    @staticmethod
    def flatten_old_to_new(old_flat_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert old flat settings to new nested structure.
        
        Useful for migrating existing flat settings files to v2.0 format.
        
        Args:
            old_flat_data: Old flat settings dictionary
            
        Returns:
            New nested settings dictionary
        """
        new_data = {
            '_meta': {
                'version': '2.0',
                'schema': 'schoolbooth-settings',
                'migrated_from': 'v1.0'
            }
        }
        
        for old_key, (new_path, default) in SettingsMigration.KEY_MAPPING.items():
            if old_key in old_flat_data:
                value = old_flat_data[old_key]
            else:
                value = default
            SettingsMigration.set_nested(new_data, new_path, value)
        
        return new_data
    
    @staticmethod
    def get_mapping_for_old_key(old_key: str) -> Tuple[Tuple[str, ...], Any]:
        """Get nested path and default for an old flat key.
        
        Args:
            old_key: Old flat key name
            
        Returns:
            Tuple of (nested_path_tuple, default_value)
        """
        return SettingsMigration.KEY_MAPPING.get(old_key, (None, None))


# Supported camera resolutions
CAMERA_RESOLUTIONS = {
    '1280x720': {'width': 1280, 'height': 720, 'label': '720p (HD)'},
    '1920x1080': {'width': 1920, 'height': 1080, 'label': '1080p (Full HD)'},
    '2560x1440': {'width': 2560, 'height': 1440, 'label': '1440p (QHD)'},
    '3840x2160': {'width': 3840, 'height': 2160, 'label': '2160p (4K)'},
    '2048x1536': {'width': 2048, 'height': 1536, 'label': '3MP'},
    '2592x1944': {'width': 2592, 'height': 1944, 'label': '5MP'},
    '4000x3000': {'width': 4000, 'height': 3000, 'label': '12MP'},
}

# Camera quality presets
CAMERA_QUALITIES = {
    'low': {'compression': 0.7, 'label': 'Low (Fast)'},
    'medium': {'compression': 0.85, 'label': 'Medium (Balanced)'},
    'high': {'compression': 0.95, 'label': 'High (Best)'},
    'lossless': {'compression': 1.0, 'label': 'Lossless'},
}

# Camera focus modes
CAMERA_FOCUS_MODES = {
    'manual': {'label': 'Manual'},
    'auto': {'label': 'Auto (Single)'},
    'continuous': {'label': 'Continuous (Tracking)'},
    'macro': {'label': 'Macro (Close-up)'},
}
