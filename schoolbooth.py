import os
import sys
import json
import csv
import base64
import tempfile
import secrets
import subprocess
import hashlib
import hmac
import string
import time
import math
import shutil
import qrcode.constants
from datetime import datetime, timedelta
from io import BytesIO
from urllib import request as urllib_request
from urllib import error as urllib_error

# Help Qt find system fonts on Windows (PyQt wheels may not ship bundled fonts).
if sys.platform == 'win32':
    os.environ.setdefault('QT_QPA_FONTDIR', r'C:\Windows\Fonts')
    # Silence repeated non-fatal Qt font path warnings on PyQt wheels.
    _qt_rules = os.environ.get('QT_LOGGING_RULES', '')
    _font_rule = 'qt.qpa.fonts.warning=false'
    if _font_rule not in _qt_rules:
        os.environ['QT_LOGGING_RULES'] = f"{_qt_rules};{_font_rule}".strip(';')

import numpy as np
import cv2

from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QPropertyAnimation, QObject, pyqtSignal, QThread, QSize
from PyQt5.QtGui import QImage, QPixmap, QFont, QIcon
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QCheckBox,
                             QComboBox, QMessageBox, QFileDialog, QGroupBox,
                             QSpinBox, QDoubleSpinBox, QSlider, QGridLayout, QDialog,
                             QDialogButtonBox, QMenu, QAction, QMenuBar,
                             QLineEdit, QFormLayout, QSizePolicy, QTextEdit,
                             QInputDialog, QScrollArea, QToolTip, QListWidget, QStyle)

import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from PIL import Image, ImageDraw, ImageFont
import escpos.printer as p
from settings_manager import SettingsManager

ACCESS_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_secure_access_code(length=8):
    raw = ''.join(secrets.choice(ACCESS_CODE_ALPHABET) for _ in range(length))
    if length == 8:
        return raw[:4] + '-' + raw[4:]
    return raw


def format_access_code_for_display(code):
    normalized = ''.join(ch for ch in str(code).upper() if ch.isalnum())
    if len(normalized) == 8:
        return normalized[:4] + '-' + normalized[4:]
    return normalized

# PyInstaller runtime fixes
if getattr(sys, 'frozen', False):
    # Fix escpos file locations
    from escpos import escpos

    escpos.DEVICE_FILE = os.path.join(sys._MEIPASS, 'escpos', 'capabilities.json')

    # Windows-specific fixes
    if sys.platform == 'win32':
        # Add pywin32 DLLs to path
        try:
            pywin32_dir = os.path.join(sys._MEIPASS, 'pywin32_system32')
            os.environ['PATH'] = pywin32_dir + ';' + os.environ['PATH']
        except Exception as e:
            print(f"PyInstaller PATH setup error: {e}")

# For device detection on Linux
import glob  # For device detection on Linux

# For input monitoring - not used
#from pynput import mouse, keyboard  # For input monitoring

# Windows-specific printing imports
if sys.platform == 'win32':
    try:
        import win32print
        import win32api
        import win32con
        import win32gui
        from ctypes import windll, byref, c_ulong, Structure, POINTER
        import win32com.client

        # Add pywin32_system_32 to PATH
        try:
            pywin32_dir = os.path.join(sys.prefix, "Lib", "site-packages", "pywin32_system32")
            if os.path.exists(pywin32_dir) and pywin32_dir not in os.environ["PATH"]:
                os.environ["PATH"] = pywin32_dir + ";" + os.environ["PATH"]
        except Exception as e:
            print("Error setting environment path. " + str(e))

        # GetRawInputDeviceList/Info are called via ctypes windll.user32 directly below

    except ImportError:
        print("Error importing win32 modules. Ensure pywin32 is installed.")
        win32print = None
        win32api = None
        win32con = None
        win32gui = None


from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QLineEdit, QPushButton, QDialogButtonBox,
                             QMessageBox, QApplication)
from PyQt5.QtCore import Qt

# ---------------------------------------------------------------------------
# Application version and update source
# ---------------------------------------------------------------------------
APP_VERSION   = "3.0.0"
GITHUB_OWNER  = "Awebbtx"
GITHUB_REPO   = "Schoolbooth"


class HIDMappingDialog(QDialog):
    """
    A dialog for mapping HID device inputs to application actions.

    Features:
    - Detects available HID devices on Windows systems
    - Allows mapping specific keys/buttons to application actions
    - Saves mappings to a settings dictionary

    Args:
        parent (QWidget): Parent widget
        settings (dict): Dictionary to store persistent settings
    """

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings or {}
        self.mappings = {}
        self.key_capture_field = None
        self.current_action = None
        self.available_devices = self._get_available_devices()
        self.selected_device_id = self.settings.get('hid_device_id')

        self._init_ui()
        self._load_mappings()

        # Window properties
        self.setWindowTitle("HID Device Mapping")
        self.setMinimumSize(400, 300)

    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout()

        # Device selection
        device_group = QHBoxLayout()
        device_label = QLabel("Select HID Device:")
        self.device_combo = QComboBox()
        self._populate_devices()
        device_group.addWidget(device_label)
        device_group.addWidget(self.device_combo)
        layout.addLayout(device_group)

        # Action mappings
        self._create_mapping_field("Capture Image", layout)
        self._create_mapping_field("Navigate Left", layout)
        self._create_mapping_field("Navigate Right", layout)
        self._create_mapping_field("Select", layout)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def _create_mapping_field(self, action_name, parent_layout):
        """Create a mapping row for a specific action."""
        row = QHBoxLayout()
        label = QLabel(f"{action_name}:")
        field = QLineEdit()
        field.setReadOnly(True)

        # Custom click handler for capturing input
        def start_capture(event):
            self.key_capture_field = field
            self.current_action = action_name
            field.setText("Press any key...")
            field.setFocus()

        field.mousePressEvent = start_capture
        self.mappings[action_name] = field

        row.addWidget(label)
        row.addWidget(field)
        parent_layout.addLayout(row)

    def _populate_devices(self):
        """Populate the device combo box with available devices."""
        self.device_combo.clear()
        for device in self.available_devices:
            self.device_combo.addItem(device['name'], device['handle'])

        # Select currently configured device if available
        if self.selected_device_id:
            index = self.device_combo.findData(self.selected_device_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)

    def _get_available_devices(self):
        """Detect available HID devices with better error handling"""
        devices = []

        if sys.platform != 'win32':
            print("HID device detection only supported on Windows")
            return devices

        if windll is None:
            print("Win32 API not available for HID detection")
            return devices

        try:
            # Get device count first
            device_count = c_ulong()
            windll.user32.GetRawInputDeviceList(
                None,
                byref(device_count),
                sizeof(RAWINPUTDEVICELIST)
            )

            # Get actual device list
            device_list = (RAWINPUTDEVICELIST * device_count.value)()
            windll.user32.GetRawInputDeviceList(
                byref(device_list),
                byref(device_count),
                sizeof(RAWINPUTDEVICELIST)
            )

            for i in range(device_count.value):
                device = device_list[i]
                if device.dwType == win32con.RIM_TYPEHID:
                    # Get device name
                    name_length = c_ulong()
                    windll.user32.GetRawInputDeviceInfoW(
                        device.hDevice,
                        win32con.RIDI_DEVICENAME,
                        None,
                        byref(name_length)
                    )

                    name_buffer = create_unicode_buffer(name_length.value)
                    windll.user32.GetRawInputDeviceInfoW(
                        device.hDevice,
                        win32con.RIDI_DEVICENAME,
                        byref(name_buffer),
                        byref(name_length)
                    )

                    devices.append({
                        'name': f"HID Device {i} ({name_buffer.value})",
                        'handle': device.hDevice
                    })

        except Exception as e:
            print(f"HID device detection error: {str(e)}")

        return devices

    def _load_mappings(self):
        """Load saved mappings from settings."""
        for action in self.mappings:
            key = self.settings.get(
                f'hid_map_{action.lower().replace(" ", "_")}',
                ""
            )
            self.mappings[action].setText(key)

    def keyPressEvent(self, event):
        """Handle key presses when capturing input."""
        if self.key_capture_field:
            key = event.key()
            try:
                # First try to get the text representation
                key_name = event.text()

                # If no text (like for special keys), use the enum name
                if not key_name:
                    key_name = self._get_qt_key_name(key)

                self.key_capture_field.setText(f"{key_name} ({key})")
                self.settings[
                    f'hid_map_{self.current_action.lower().replace(" ", "_")}'
                ] = f"{key_name} ({key})"

            except Exception as e:
                print(f"Error processing key press: {e}")
                self.key_capture_field.setText(f"Unknown Key ({key})")

            finally:
                self.key_capture_field = None
                self.current_action = None
        else:
            super().keyPressEvent(event)

    def _get_qt_key_name(self, key_code):
        """Convert Qt key code to human-readable name."""
        # Create a mapping of common special keys
        key_map = {
            Qt.Key_Left: "Left",
            Qt.Key_Right: "Right",
            Qt.Key_Up: "Up",
            Qt.Key_Down: "Down",
            Qt.Key_Return: "Enter",
            Qt.Key_Enter: "Enter",
            Qt.Key_Escape: "Escape",
            Qt.Key_Space: "Space",
            Qt.Key_Backspace: "Backspace",
            Qt.Key_Delete: "Delete",
            Qt.Key_Home: "Home",
            Qt.Key_End: "End",
            Qt.Key_PageUp: "Page Up",
            Qt.Key_PageDown: "Page Down",
            Qt.Key_Tab: "Tab",
            Qt.Key_CapsLock: "Caps Lock",
            Qt.Key_Shift: "Shift",
            Qt.Key_Control: "Ctrl",
            Qt.Key_Alt: "Alt",
            Qt.Key_Meta: "Meta",
            Qt.Key_F1: "F1",
            Qt.Key_F2: "F2",
            # Add more function keys as needed
        }

        # Check if it's a standard ASCII key
        if 32 <= key_code <= 126:
            return chr(key_code)

        # Check our special key mapping
        return key_map.get(key_code, f"Key_{key_code}")

    def accept(self):
        """Save settings when dialog is accepted."""
        # Save selected device
        self.settings['hid_device_id'] = self.device_combo.currentData()
        super().accept()

class WPUrlGenerator:
    """Handles secure URL generation with shared secret"""

    def __init__(self, shared_secret):
        self.shared_secret = shared_secret

    def generate_url(self, base_url, file_path, access_code, app_mode=False, timestamp=None):
        """
        Generate a signed download URL.
        Format: {base_url}/?pta_schoolbooth_download={file}&code={code}&hash={hmac_sha256}
        """
        file_path = file_path.lstrip('/')
        message = f"{file_path}|{access_code}".encode()
        security_hash = hmac.new(
            self.shared_secret.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        url = (
            f"{base_url.rstrip('/')}/"
            f"?pta_schoolbooth_download={file_path}"
            f"&code={access_code}"
            f"&hash={security_hash}"
        )

        if app_mode:
            timestamp = str(timestamp or int(time.time()))
            app_message = f"{timestamp}|{file_path}|{access_code}|app-view".encode()
            app_signature = hmac.new(
                self.shared_secret.encode(),
                app_message,
                hashlib.sha256
            ).hexdigest()
            url += (
                f"&ptasb_app=1"
                f"&ptasb_ts={timestamp}"
                f"&ptasb_sig={app_signature}"
            )

        return url


class WPLinkSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("WordPress Link Settings")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout()

        # Enable Checkbox
        self.enable_cb = QCheckBox("Enable WordPress Integration")
        self.enable_cb.setChecked(self.parent.settings.get('wp_link_enabled', False))
        self.enable_cb.setToolTip("Enable/disable WordPress integration features")
        layout.addWidget(self.enable_cb)

        # Settings Group
        settings_group = QGroupBox("Connection Settings")
        form_layout = QFormLayout()

        self.url_edit = QLineEdit(self.parent.settings.get('wp_url', ''))
        self.url_edit.setToolTip("Your WordPress site URL\n(e.g., https://www.yoursite.com)")
        form_layout.addRow("WordPress URL:", self.url_edit)

        self.api_timeout_spin = QSpinBox()
        self.api_timeout_spin.setRange(5, 120)
        self.api_timeout_spin.setValue(int(self.parent.settings.get('wp_api_timeout', 20)))
        self.api_timeout_spin.setToolTip("Timeout in seconds for HTTPS API requests")
        form_layout.addRow("API Timeout (sec):", self.api_timeout_spin)

        self.enroll_username_edit = QLineEdit(self.parent.settings.get('wp_enroll_username', ''))
        self.enroll_username_edit.setPlaceholderText("WordPress admin username")
        self.enroll_username_edit.setToolTip("Used with a WordPress Application Password for one-time enrollment")
        form_layout.addRow("Enroll Username:", self.enroll_username_edit)

        self.enroll_app_password_edit = QLineEdit('')
        self.enroll_app_password_edit.setPlaceholderText("WordPress Application Password")
        self.enroll_app_password_edit.setEchoMode(QLineEdit.Password)
        self.enroll_app_password_edit.setToolTip("Use a WordPress Application Password. This is used for enrollment only and is not saved.")
        form_layout.addRow("Enroll App Password:", self.enroll_app_password_edit)

        self.enroll_btn = QPushButton("Enroll via WordPress Login")
        self.enroll_btn.clicked.connect(self.enroll_with_wordpress_login)
        self.enroll_btn.setToolTip("Authenticate with WordPress username + application password and provision API settings")
        form_layout.addRow("Enrollment:", self.enroll_btn)

        settings_group.setLayout(form_layout)
        layout.addWidget(settings_group)

        # Test Button
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_connection)
        self.test_btn.setToolTip("Test WordPress server connection with current settings")
        layout.addWidget(self.test_btn)

        # Dialog Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def test_connection(self):
        """Test WordPress HTTPS API connectivity"""
        try:
            self._test_api_connection()
            QMessageBox.information(self, "Success", "Connection verified: HTTPS API OK")
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Error: {str(e)}")

    def _test_api_connection(self):
        base_url = self.url_edit.text().rstrip('/')
        endpoint = self.parent.settings.get('wp_api_endpoint', '/wp-json/pta-schoolbooth/v1/ingest').strip()
        secret = self.parent.settings.get('wp_shared_secret', '')
        if not base_url:
            raise RuntimeError("WordPress URL is required for HTTPS API testing")
        if not endpoint:
            raise RuntimeError("API endpoint is required for HTTPS API testing")
        if len(secret) < 32:
            raise RuntimeError("No shared secret found — please enroll this device first")

        api_url = f"{base_url}{endpoint if endpoint.startswith('/') else '/' + endpoint}"
        ping_url = api_url.replace('/ingest', '/ping') if api_url.endswith('/ingest') else api_url.rstrip('/') + '/ping'
        timestamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode(),
            f"{timestamp}|ping".encode(),
            hashlib.sha256
        ).hexdigest()
        timeout = int(self.api_timeout_spin.value())

        ping_candidates = [ping_url]
        if '/pta-schoolbooth/' in ping_url:
            ping_candidates.append(ping_url.replace('/pta-schoolbooth/', '/nbpta/'))
        elif '/nbpta/' in ping_url:
            ping_candidates.append(ping_url.replace('/nbpta/', '/pta-schoolbooth/'))

        last_error = None
        for candidate in ping_candidates:
            try:
                req = urllib_request.Request(
                    candidate,
                    data=json.dumps({"probe": "ping"}).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/json',
                        'X-PTASB-Timestamp': timestamp,
                        'X-PTASB-Signature': signature,
                    },
                    method='POST'
                )
                with urllib_request.urlopen(req, timeout=timeout) as response:
                    if response.status < 200 or response.status >= 300:
                        raise RuntimeError(f"API ping failed with HTTP {response.status}")

                if candidate != ping_url:
                    # Keep future requests on the reachable namespace.
                    current = self.parent.settings.get('wp_api_endpoint', '')
                    if '/pta-schoolbooth/' in current:
                        self.parent.settings['wp_api_endpoint'] = current.replace('/pta-schoolbooth/', '/nbpta/')
                    else:
                        self.parent.settings['wp_api_endpoint'] = current.replace('/nbpta/', '/pta-schoolbooth/')
                return
            except urllib_error.HTTPError as http_err:
                last_error = http_err
                if http_err.code == 404:
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError('API ping failed for all supported endpoint variants')

    def enroll_with_wordpress_login(self):
        base_url = self.url_edit.text().rstrip('/')
        username = self.enroll_username_edit.text().strip()
        app_password = self.enroll_app_password_edit.text().strip()

        if not base_url:
            QMessageBox.warning(self, "Missing URL", "Enter your WordPress URL first.")
            return

        if not username:
            QMessageBox.warning(self, "Missing Username", "Enter a WordPress username for enrollment.")
            return

        if not app_password:
            QMessageBox.warning(self, "Missing App Password", "Enter a WordPress Application Password for enrollment.")
            return

        enroll_candidates = [
            f"{base_url}/wp-json/pta-schoolbooth/v1/enroll",
            f"{base_url}/wp-json/nbpta/v1/enroll",
        ]

        try:
            timeout = int(self.api_timeout_spin.value())
            basic_token = base64.b64encode(f"{username}:{app_password}".encode('utf-8')).decode('ascii')
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Basic {basic_token}',
            }

            # Ensure a stable per-device instance ID exists.
            instance_id = self.parent.settings.get('wp_app_instance_id', '')
            if not instance_id:
                import uuid
                instance_id = str(uuid.uuid4())
                self.parent.settings['wp_app_instance_id'] = instance_id
                self.parent.save_settings()

            payload = {
                'app_name': 'Schoolbooth App',
                'app_instance_id': instance_id,
            }

            data = None
            last_error = None
            chosen_endpoint = None
            for enroll_url in enroll_candidates:
                try:
                    req = urllib_request.Request(
                        enroll_url,
                        data=json.dumps(payload).encode('utf-8'),
                        headers=headers,
                        method='POST'
                    )
                    with urllib_request.urlopen(req, timeout=timeout) as response:
                        response_body = response.read().decode('utf-8')
                        data = json.loads(response_body) if response_body else {}
                    chosen_endpoint = enroll_url
                    break
                except urllib_error.HTTPError as http_err:
                    last_error = http_err
                    if http_err.code == 404:
                        continue
                    raise

            if data is None:
                if last_error is not None:
                    raise last_error
                raise RuntimeError('Could not reach any supported WordPress enrollment endpoint')

            if not data.get('success'):
                raise RuntimeError('WordPress returned an unsuccessful enrollment response')

            self.url_edit.setText(data.get('wp_url', base_url))
            enrolled_endpoint = data.get('wp_api_endpoint', '/wp-json/pta-schoolbooth/v1/ingest')
            if chosen_endpoint and '/nbpta/' in chosen_endpoint and '/pta-schoolbooth/' in enrolled_endpoint:
                enrolled_endpoint = enrolled_endpoint.replace('/pta-schoolbooth/', '/nbpta/')
            self.parent.settings['wp_api_endpoint'] = enrolled_endpoint
            self.parent.settings['wp_shared_secret'] = data.get('wp_shared_secret', '')
            self.api_timeout_spin.setValue(int(data.get('wp_api_timeout', 20)))
            self.enable_cb.setChecked(True)
            self.enroll_app_password_edit.clear()

            QMessageBox.information(self, "Enrollment Complete", "WordPress enrollment succeeded and API settings were provisioned.")

        except urllib_error.HTTPError as http_err:
            detail = ''
            try:
                detail = http_err.read().decode('utf-8')
            except Exception:
                detail = ''
            QMessageBox.critical(
                self,
                "Enrollment Failed",
                f"HTTP {http_err.code} during enrollment.\n{detail or str(http_err)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Enrollment Failed", f"Could not enroll with WordPress:\n{str(e)}")

    def accept(self):
        """Save settings on OK"""
        self.parent.settings.update({
            'wp_link_enabled': self.enable_cb.isChecked(),
            'wp_url': self.url_edit.text(),
            'wp_api_timeout': int(self.api_timeout_spin.value()),
            'wp_enroll_username': self.enroll_username_edit.text().strip()
        })
        super().accept()


class WatermarkSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Watermark Settings")
        self.setGeometry(300, 300, 450, 600)  # Increased size for new controls

        layout = QVBoxLayout()

        # Enable Checkbox
        self.enable_checkbox = QCheckBox("Enable Watermark")
        self.enable_checkbox.setChecked(True)
        layout.addWidget(self.enable_checkbox)

        # Interactive Mode Checkbox
        self.interactive_cb = QCheckBox("Interactive Editing Mode")
        self.interactive_cb.setChecked(True)
        self.interactive_cb.setToolTip("Enable click-and-drag editing of watermark\n"
                                         "Drag box: Move\nDrag bottom-right handle: Scale\n"
                                         "Drag top handle: Rotate")
        layout.addWidget(self.interactive_cb)

        self.interactive_hint = QLabel(
            "Live editing:\n"
            "- Drag watermark box to move\n"
            "- Drag bottom-right handle to scale\n"
            "- Drag top handle to rotate"
        )
        self.interactive_hint.setStyleSheet("color: #444;")
        layout.addWidget(self.interactive_hint)

        snap_group = QGroupBox("Snap Grid")
        snap_layout = QGridLayout()

        self.snap_grid_cb = QCheckBox("Enable Snap Grid")
        self.snap_grid_cb.setChecked(True)
        snap_layout.addWidget(self.snap_grid_cb, 0, 0, 1, 2)

        snap_layout.addWidget(QLabel("Grid Step (%):"), 1, 0)
        self.snap_grid_step_spin = QSpinBox()
        self.snap_grid_step_spin.setRange(1, 25)
        self.snap_grid_step_spin.setValue(5)
        self.snap_grid_step_spin.setSuffix("%")
        self.snap_grid_step_spin.setToolTip("Smaller step = finer snap grid")
        snap_layout.addWidget(self.snap_grid_step_spin, 1, 1)

        self.snap_center_cb = QCheckBox("Snap to Center Guides")
        self.snap_center_cb.setChecked(True)
        snap_layout.addWidget(self.snap_center_cb, 2, 0, 1, 2)

        snap_group.setLayout(snap_layout)
        layout.addWidget(snap_group)

        # Upload Button
        self.upload_btn = QPushButton("Upload Watermark (PNG)")
        layout.addWidget(self.upload_btn)

        # Position Group
        pos_group = QGroupBox("Position")
        pos_layout = QGridLayout()

        # Horizontal Position
        pos_layout.addWidget(QLabel("Left-Right:"), 0, 0)
        self.watermark_x_slider = QSlider(Qt.Horizontal)
        self.watermark_x_slider.setRange(0, 100)
        pos_layout.addWidget(self.watermark_x_slider, 0, 1)

        self.watermark_x_spin = QSpinBox()
        self.watermark_x_spin.setRange(0, 100)
        pos_layout.addWidget(self.watermark_x_spin, 0, 2)

        # Vertical Position
        pos_layout.addWidget(QLabel("Up-Down:"), 1, 0)
        self.watermark_y_slider = QSlider(Qt.Horizontal)
        self.watermark_y_slider.setRange(0, 100)
        pos_layout.addWidget(self.watermark_y_slider, 1, 1)

        self.watermark_y_spin = QSpinBox()
        self.watermark_y_spin.setRange(0, 100)
        pos_layout.addWidget(self.watermark_y_spin, 1, 2)

        pos_group.setLayout(pos_layout)
        self.pos_group = pos_group
        layout.addWidget(pos_group)

        # Size Group
        size_group = QGroupBox("Size")
        size_layout = QGridLayout()
        size_layout.addWidget(QLabel("Size:"), 0, 0)
        self.watermark_size_slider = QSlider(Qt.Horizontal)
        self.watermark_size_slider.setRange(1, 100)
        size_layout.addWidget(self.watermark_size_slider, 0, 1)

        self.watermark_size_spin = QSpinBox()
        self.watermark_size_spin.setRange(1, 100)
        size_layout.addWidget(self.watermark_size_spin, 0, 2)

        size_group.setLayout(size_layout)
        self.size_group = size_group
        layout.addWidget(size_group)

        # Opacity Group
        opacity_group = QGroupBox("Opacity")
        opacity_layout = QGridLayout()
        opacity_layout.addWidget(QLabel("Opacity:"), 0, 0)
        self.watermark_opacity_slider = QSlider(Qt.Horizontal)
        self.watermark_opacity_slider.setRange(0, 100)
        opacity_layout.addWidget(self.watermark_opacity_slider, 0, 1)

        self.watermark_opacity_spin = QSpinBox()
        self.watermark_opacity_spin.setRange(0, 100)
        opacity_layout.addWidget(self.watermark_opacity_spin, 0, 2)

        opacity_group.setLayout(opacity_layout)
        layout.addWidget(opacity_group)

        # Rotation Group
        rotation_group = QGroupBox("Rotation")
        rotation_layout = QGridLayout()
        rotation_layout.addWidget(QLabel("Rotation:"), 0, 0)
        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setRange(0, 360)
        rotation_layout.addWidget(self.rotation_slider, 0, 1)

        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 360)
        rotation_layout.addWidget(self.rotation_spin, 0, 2)

        rotation_group.setLayout(rotation_layout)
        self.rotation_group = rotation_group
        layout.addWidget(rotation_group)

        # Scale Group
        scale_group = QGroupBox("Scale")
        scale_layout = QGridLayout()
        scale_layout.addWidget(QLabel("Scale:"), 0, 0)
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(10, 300)
        scale_layout.addWidget(self.scale_slider, 0, 1)

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 300)
        scale_layout.addWidget(self.scale_spin, 0, 2)

        scale_group.setLayout(scale_layout)
        self.scale_group = scale_group
        layout.addWidget(scale_group)

        # Background Removal Checkbox
        self.bg_remove_cb = QCheckBox("Remove Background")
        layout.addWidget(self.bg_remove_cb)

        # Dialog Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Connect all signals
        self._connect_signals()
        self.interactive_cb.toggled.connect(self._toggle_manual_groups)
        self._toggle_manual_groups(self.interactive_cb.isChecked())

        self.setLayout(layout)

    def _connect_signals(self):
        """Connect all slider-spinbox pairs"""
        self.watermark_x_slider.valueChanged.connect(self.watermark_x_spin.setValue)
        self.watermark_x_spin.valueChanged.connect(self.watermark_x_slider.setValue)
        self.watermark_y_slider.valueChanged.connect(self.watermark_y_spin.setValue)
        self.watermark_y_spin.valueChanged.connect(self.watermark_y_slider.setValue)
        self.watermark_size_slider.valueChanged.connect(self.watermark_size_spin.setValue)
        self.watermark_size_spin.valueChanged.connect(self.watermark_size_slider.setValue)
        self.watermark_opacity_slider.valueChanged.connect(self.watermark_opacity_spin.setValue)
        self.watermark_opacity_spin.valueChanged.connect(self.watermark_opacity_slider.setValue)
        self.rotation_slider.valueChanged.connect(self.rotation_spin.setValue)
        self.rotation_spin.valueChanged.connect(self.rotation_slider.setValue)
        self.scale_slider.valueChanged.connect(self.scale_spin.setValue)
        self.scale_spin.valueChanged.connect(self.scale_slider.setValue)

    def _toggle_manual_groups(self, interactive_enabled):
        manual_enabled = not interactive_enabled
        self.pos_group.setEnabled(manual_enabled)
        self.size_group.setEnabled(manual_enabled)
        self.rotation_group.setEnabled(manual_enabled)
        self.scale_group.setEnabled(manual_enabled)
        self.interactive_hint.setVisible(interactive_enabled)


class WatermarkEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.preview_frame = None
        self._preview_rect = QRect()
        self._drag_mode = None
        self._drag_start_pos = QPoint()
        self._drag_start_state = None
        self._drag_center_pos = QPoint()
        self._suspend_refresh = False
        self._handle_radius = 12

        self.setWindowTitle("Watermark Editor")
        self.setGeometry(220, 140, 1100, 680)

        main_layout = QHBoxLayout()

        preview_layout = QVBoxLayout()
        preview_title = QLabel("Preview")
        preview_title.setStyleSheet("font-weight: 600;")
        self.preview_label = QLabel("Preview unavailable")
        self.preview_label.setMinimumSize(700, 500)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background:#1e1e1e; border:1px solid #444; color:#ddd;")
        self.preview_label.setMouseTracking(True)
        self.preview_label.mousePressEvent = self._preview_mouse_press
        self.preview_label.mouseMoveEvent = self._preview_mouse_move
        self.preview_label.mouseReleaseEvent = self._preview_mouse_release

        self.show_guides_cb = QCheckBox("Show Editor Guides")
        self.show_guides_cb.setChecked(True)
        self.show_guides_cb.setToolTip("Shows grid and handles in this editor preview only")

        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.preview_label, 1)
        preview_layout.addWidget(self.show_guides_cb)

        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(10)

        self.enable_checkbox = QCheckBox("Enable Watermark")
        controls_layout.addWidget(self.enable_checkbox)

        self.upload_btn = QPushButton("Upload Watermark (PNG)")
        controls_layout.addWidget(self.upload_btn)

        self.watermark_x_slider, self.watermark_x_spin = self._add_slider_row(controls_layout, "Left-Right", 0, 100)
        self.watermark_y_slider, self.watermark_y_spin = self._add_slider_row(controls_layout, "Up-Down", 0, 100)
        self.watermark_size_slider, self.watermark_size_spin = self._add_slider_row(controls_layout, "Base Size", 1, 100)
        self.scale_slider, self.scale_spin = self._add_slider_row(controls_layout, "Fine Scale", 10, 300, suffix="%")
        self.rotation_slider, self.rotation_spin = self._add_slider_row(controls_layout, "Rotation", 0, 360)
        self.watermark_opacity_slider, self.watermark_opacity_spin = self._add_slider_row(controls_layout, "Opacity", 0, 100)

        self.bg_remove_cb = QCheckBox("Remove Background")
        controls_layout.addWidget(self.bg_remove_cb)

        reset_btn = QPushButton("Reset to Defaults")
        controls_layout.addWidget(reset_btn)

        controls_layout.addStretch(1)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        controls_layout.addWidget(button_box)

        main_layout.addLayout(preview_layout, 7)
        main_layout.addLayout(controls_layout, 4)
        self.setLayout(main_layout)

        self._connect_controls()
        self._load_from_settings()
        self._capture_preview_frame()
        self.refresh_preview()

        self.upload_btn.clicked.connect(self._upload_watermark)
        self.show_guides_cb.toggled.connect(self.refresh_preview)
        reset_btn.clicked.connect(self._reset_defaults)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def _add_slider_row(self, parent_layout, label_text, min_val, max_val, suffix=""):
        group = QGroupBox(label_text)
        row = QGridLayout()
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        if suffix:
            spin.setSuffix(suffix)

        row.addWidget(slider, 0, 0)
        row.addWidget(spin, 0, 1)
        group.setLayout(row)
        parent_layout.addWidget(group)
        return slider, spin

    def _connect_controls(self):
        pairs = [
            (self.watermark_x_slider, self.watermark_x_spin),
            (self.watermark_y_slider, self.watermark_y_spin),
            (self.watermark_size_slider, self.watermark_size_spin),
            (self.scale_slider, self.scale_spin),
            (self.rotation_slider, self.rotation_spin),
            (self.watermark_opacity_slider, self.watermark_opacity_spin),
        ]
        for slider, spin in pairs:
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            slider.valueChanged.connect(self.refresh_preview)

        self.enable_checkbox.toggled.connect(self.refresh_preview)
        self.bg_remove_cb.toggled.connect(self.refresh_preview)

    def _load_from_settings(self):
        s = self.parent_app.settings
        self.enable_checkbox.setChecked(s.get('watermark_enabled', False))
        self.watermark_x_slider.setValue(int(s.get('watermark_x', 50)))
        self.watermark_y_slider.setValue(int(s.get('watermark_y', 50)))
        self.watermark_size_slider.setValue(int(s.get('watermark_size', 30)))
        self.scale_slider.setValue(int(float(s.get('watermark_scale', 1.0)) * 100))
        self.rotation_slider.setValue(int(s.get('watermark_rotation', 0)))
        self.watermark_opacity_slider.setValue(int(s.get('watermark_opacity', 70)))
        self.bg_remove_cb.setChecked(s.get('watermark_remove_bg', True))

    def _capture_preview_frame(self):
        frame = None
        if self.parent_app.cap and self.parent_app.cap.isOpened():
            ret, live = self.parent_app.cap.read()
            if ret:
                frame = live

        if frame is None:
            frame = np.full((720, 1280, 3), 40, dtype=np.uint8)
            cv2.putText(
                frame,
                "No live camera frame available",
                (40, 360),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (220, 220, 220),
                2,
                cv2.LINE_AA,
            )

        # Match the main camera preview orientation.
        rotation = int(self.parent_app.settings.get('rotation', 0))
        if rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        self.preview_frame = frame

    def _upload_watermark(self):
        self.parent_app.upload_watermark()
        self._capture_preview_frame()
        self.refresh_preview()

    def _reset_defaults(self):
        self.watermark_x_slider.setValue(50)
        self.watermark_y_slider.setValue(50)
        self.watermark_size_slider.setValue(30)
        self.scale_slider.setValue(100)
        self.rotation_slider.setValue(0)
        self.watermark_opacity_slider.setValue(70)
        self.bg_remove_cb.setChecked(True)

    def get_settings_update(self):
        return {
            'watermark_enabled': self.enable_checkbox.isChecked(),
            'watermark_x': float(self.watermark_x_slider.value()),
            'watermark_y': float(self.watermark_y_slider.value()),
            'watermark_size': float(self.watermark_size_slider.value()),
            'watermark_scale': float(self.scale_slider.value()) / 100.0,
            'watermark_rotation': float(self.rotation_slider.value()),
            'watermark_opacity': float(self.watermark_opacity_slider.value()),
            'watermark_remove_bg': self.bg_remove_cb.isChecked(),
            'watermark_interactive': False,
        }

    def _clamp_state(self, state):
        state['watermark_x'] = max(0.0, min(100.0, float(state['watermark_x'])))
        state['watermark_y'] = max(0.0, min(100.0, float(state['watermark_y'])))
        state['watermark_size'] = max(1.0, min(100.0, float(state['watermark_size'])))
        state['watermark_scale'] = max(0.1, min(3.0, float(state['watermark_scale'])))
        state['watermark_rotation'] = float(state['watermark_rotation']) % 360.0
        state['watermark_opacity'] = max(0.0, min(100.0, float(state['watermark_opacity'])))
        return state

    def _set_controls_from_state(self, state):
        state = self._clamp_state(state)
        self._suspend_refresh = True
        try:
            self.watermark_x_slider.setValue(int(round(state['watermark_x'])))
            self.watermark_y_slider.setValue(int(round(state['watermark_y'])))
            self.watermark_size_slider.setValue(int(round(state['watermark_size'])))
            self.scale_slider.setValue(int(round(state['watermark_scale'] * 100.0)))
            self.rotation_slider.setValue(int(round(state['watermark_rotation'])) % 360)
            self.watermark_opacity_slider.setValue(int(round(state['watermark_opacity'])))
        finally:
            self._suspend_refresh = False

        self.refresh_preview()

    def _get_watermark_rect_in_frame(self, state):
        if self.preview_frame is None:
            return QRect()

        wm = self.parent_app.get_transformed_watermark(state)
        if wm is None:
            return QRect()

        frame_h, frame_w = self.preview_frame.shape[:2]
        wm_h, wm_w = wm.shape[:2]
        x, y = self.parent_app._compute_watermark_top_left(frame_w, frame_h, wm_w, wm_h, {
            'x': state['watermark_x'],
            'y': state['watermark_y'],
        })
        return QRect(x, y, wm_w, wm_h)

    def _frame_point_to_label(self, point):
        if self.preview_rect_is_invalid():
            return QPoint()
        frame_h, frame_w = self.preview_frame.shape[:2]
        px = self._preview_rect.x() + int(point.x() / max(1, frame_w) * self._preview_rect.width())
        py = self._preview_rect.y() + int(point.y() / max(1, frame_h) * self._preview_rect.height())
        return QPoint(px, py)

    def _label_point_to_frame(self, point):
        if self.preview_rect_is_invalid():
            return QPoint()
        frame_h, frame_w = self.preview_frame.shape[:2]
        px = int((point.x() - self._preview_rect.x()) / max(1, self._preview_rect.width()) * frame_w)
        py = int((point.y() - self._preview_rect.y()) / max(1, self._preview_rect.height()) * frame_h)
        return QPoint(px, py)

    def preview_rect_is_invalid(self):
        return self._preview_rect.isNull() or self.preview_frame is None

    def _get_handles_in_label(self, state):
        rect = self._get_watermark_rect_in_frame(state)
        if rect.isNull():
            return None, None, None

        tl = self._frame_point_to_label(rect.topLeft())
        br = self._frame_point_to_label(rect.bottomRight())
        mapped = QRect(tl, br).normalized()
        resize_handle = mapped.bottomRight()
        rotate_handle = QPoint(mapped.center().x(), mapped.top())
        return mapped, resize_handle, rotate_handle

    def _update_hover_cursor(self, pos):
        state = self.get_settings_update()
        wm_rect, resize_handle, rotate_handle = self._get_handles_in_label(state)
        if wm_rect is None:
            self.preview_label.unsetCursor()
            return

        if (pos - rotate_handle).manhattanLength() <= self._handle_radius * 2:
            self.preview_label.setCursor(Qt.CrossCursor)
        elif (pos - resize_handle).manhattanLength() <= self._handle_radius * 2:
            self.preview_label.setCursor(Qt.SizeFDiagCursor)
        elif wm_rect.contains(pos):
            self.preview_label.setCursor(Qt.OpenHandCursor)
        else:
            self.preview_label.unsetCursor()

    def _preview_mouse_press(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.enable_checkbox.isChecked() or self.preview_frame is None:
            return

        state = self.get_settings_update()
        wm_rect, resize_handle, rotate_handle = self._get_handles_in_label(state)
        if wm_rect is None:
            return

        pos = event.pos()
        if (pos - rotate_handle).manhattanLength() <= self._handle_radius * 2:
            self._drag_mode = 'rotate'
            self.preview_label.setCursor(Qt.CrossCursor)
            self._drag_center_pos = wm_rect.center()
        elif (pos - resize_handle).manhattanLength() <= self._handle_radius * 2:
            self._drag_mode = 'scale'
            self.preview_label.setCursor(Qt.SizeFDiagCursor)
        elif wm_rect.contains(pos):
            self._drag_mode = 'move'
            self.preview_label.setCursor(Qt.ClosedHandCursor)
        else:
            self._drag_mode = None
            return

        self._drag_start_pos = pos
        self._drag_start_state = state

    def _preview_mouse_move(self, event):
        if self._drag_mode is None:
            self._update_hover_cursor(event.pos())
            return

        if self._drag_start_state is None:
            return

        state = dict(self._drag_start_state)
        delta = event.pos() - self._drag_start_pos

        if self._drag_mode == 'move':
            state['watermark_x'] = self._drag_start_state['watermark_x'] + (delta.x() / max(1, self._preview_rect.width()) * 100.0)
            state['watermark_y'] = self._drag_start_state['watermark_y'] + (delta.y() / max(1, self._preview_rect.height()) * 100.0)
        elif self._drag_mode == 'scale':
            state['watermark_scale'] = self._drag_start_state['watermark_scale'] + (delta.x() * 0.01)
        elif self._drag_mode == 'rotate':
            start_vec = self._drag_start_pos - self._drag_center_pos
            cur_vec = event.pos() - self._drag_center_pos
            start_angle = math.degrees(math.atan2(start_vec.y(), start_vec.x()))
            cur_angle = math.degrees(math.atan2(cur_vec.y(), cur_vec.x()))
            state['watermark_rotation'] = self._drag_start_state['watermark_rotation'] + (cur_angle - start_angle)

        self._set_controls_from_state(state)

    def _preview_mouse_release(self, event):
        self._drag_mode = None
        self._drag_start_state = None
        self.preview_label.unsetCursor()

    def refresh_preview(self):
        if self._suspend_refresh:
            return
        if self.preview_frame is None:
            return

        preview = self.preview_frame.copy()
        state = self.get_settings_update()
        preview = self.parent_app.apply_watermark_with_state(
            preview,
            state,
            show_editor_overlay=self.show_guides_cb.isChecked()
        )

        rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.preview_label.setPixmap(pix)

        offset_x = (self.preview_label.width() - pix.width()) // 2
        offset_y = (self.preview_label.height() - pix.height()) // 2
        self._preview_rect = QRect(offset_x, offset_y, pix.width(), pix.height())

class ImageSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Settings")
        self.setGeometry(280, 180, 720, 760)
        self.setMinimumSize(640, 700)
        self.setSizeGripEnabled(True)

        self.setStyleSheet("""
            QDialog {
                background: #f7f9fc;
            }
            QGroupBox {
                font-size: 16px;
                font-weight: 600;
                border: 1px solid #d9e0ea;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 14px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLabel {
                font-size: 15px;
            }
            QCheckBox {
                spacing: 10px;
                font-size: 15px;
                min-height: 36px;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
            }
            QSlider::groove:horizontal {
                height: 10px;
                border-radius: 5px;
                background: #d4dbe6;
            }
            QSlider::handle:horizontal {
                width: 28px;
                margin: -9px 0;
                border-radius: 14px;
                background: #2a82da;
            }
            QComboBox, QSpinBox {
                min-height: 44px;
                font-size: 15px;
                padding: 6px 10px;
            }
            QPushButton {
                min-height: 44px;
                padding: 6px 14px;
                font-size: 15px;
            }
            QDialogButtonBox QPushButton {
                min-width: 136px;
                min-height: 44px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hint = QLabel("Adjust settings and watch the live preview update in real time. Use Reset if you want to start over.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #4b5d73;")
        layout.addWidget(hint)

        def slider_row(slider, value_text_fn=lambda v: str(v)):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            value_label = QLabel(value_text_fn(slider.value()))
            value_label.setMinimumWidth(74)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setStyleSheet("font-weight: 600; color: #1f2f46;")
            slider.valueChanged.connect(lambda v, lbl=value_label, fmt=value_text_fn: lbl.setText(fmt(v)))
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(value_label, 0)
            return row

        # Image Correction Group
        correction_group = QGroupBox("Image Correction")
        correction_layout = QFormLayout()

        # Auto Settings
        self.auto_wb_cb = QCheckBox("Auto White Balance")
        self.auto_wb_cb.setToolTip("Automatically adjust white balance for accurate colors")
        correction_layout.addRow(self.auto_wb_cb)

        self.auto_color_cb = QCheckBox("Auto Color Correction")
        self.auto_color_cb.setToolTip("Automatically enhance color balance and contrast")
        correction_layout.addRow(self.auto_color_cb)

        # Manual White Balance
        self.wb_temp_slider = QSlider(Qt.Horizontal)
        self.wb_temp_slider.setRange(2500, 10000)
        self.wb_temp_slider.setValue(6500)
        self.wb_temp_slider.setToolTip("Manual white balance temperature (2500-10000K)")

        self.wb_temp_spin = QSpinBox()
        self.wb_temp_spin.setRange(2500, 10000)
        self.wb_temp_spin.setValue(6500)
        self.wb_temp_spin.setToolTip("Exact white balance temperature in Kelvin")

        self.wb_temp_slider.valueChanged.connect(self.wb_temp_spin.setValue)
        self.wb_temp_spin.valueChanged.connect(self.wb_temp_slider.setValue)

        correction_layout.addRow("White Balance Temperature:", slider_row(self.wb_temp_slider, lambda v: f"{v}K"))
        correction_layout.addRow("Exact Value:", self.wb_temp_spin)

        # Brightness/Contrast
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.setToolTip("Adjust overall image brightness (-100 to +100)")
        correction_layout.addRow("Brightness:", slider_row(self.brightness_slider))

        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setRange(-100, 100)
        self.contrast_slider.setValue(0)
        self.contrast_slider.setToolTip("Adjust image contrast (-100 to +100)")
        correction_layout.addRow("Contrast:", slider_row(self.contrast_slider))

        # Saturation
        self.saturation_slider = QSlider(Qt.Horizontal)
        self.saturation_slider.setRange(0, 200)
        self.saturation_slider.setValue(100)
        self.saturation_slider.setToolTip("Adjust color intensity (0=grayscale, 100=normal, 200=extra vibrant)")
        correction_layout.addRow("Saturation:", slider_row(self.saturation_slider))

        # Sharpness
        self.sharpness_slider = QSlider(Qt.Horizontal)
        self.sharpness_slider.setRange(0, 100)
        self.sharpness_slider.setValue(0)
        self.sharpness_slider.setToolTip("Enhance image details (0=off, 100=max)")
        correction_layout.addRow("Sharpness:", slider_row(self.sharpness_slider))

        # Skin smoothing
        self.skin_smoothing_slider = QSlider(Qt.Horizontal)
        self.skin_smoothing_slider.setRange(0, 100)
        self.skin_smoothing_slider.setValue(0)
        self.skin_smoothing_slider.setToolTip("Subtle skin smoothing on detected skin tones (0=off, 100=max)")
        correction_layout.addRow("Skin Smoothing:", slider_row(self.skin_smoothing_slider))

        # Gamma
        self.gamma_slider = QSlider(Qt.Horizontal)
        self.gamma_slider.setRange(10, 300)
        self.gamma_slider.setValue(100)
        self.gamma_slider.setToolTip("Adjust midtone brightness (10=darkest, 100=normal, 300=lightest)")
        correction_layout.addRow("Gamma:", slider_row(self.gamma_slider))

        correction_group.setLayout(correction_layout)
        layout.addWidget(correction_group)

        # Crop Size Group
        crop_group = QGroupBox("Crop Size")
        crop_layout = QVBoxLayout()
        self.crop_combo = QComboBox()
        self.crop_combo.addItems(["4x6", "5x7", "8x10", "11x14"])
        self.crop_combo.setToolTip("Standard photo print sizes for automatic cropping")
        crop_layout.addWidget(self.crop_combo)
        crop_group.setLayout(crop_layout)
        layout.addWidget(crop_group)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.reset_btn = button_box.addButton("Reset", QDialogButtonBox.ResetRole)
        self.reset_btn.clicked.connect(self.reset_defaults)

        def _dialog_icon(name, fallback):
            try:
                from qt_material_icons import MaterialIcon
                for icon_size in (20, 24, 48):
                    try:
                        icon = MaterialIcon(name, size=icon_size)
                        if not icon.isNull():
                            return icon
                    except Exception:
                        continue
            except Exception:
                pass
            return self.style().standardIcon(fallback)

        ok_btn = button_box.button(QDialogButtonBox.Ok)
        cancel_btn = button_box.button(QDialogButtonBox.Cancel)
        if ok_btn is not None:
            ok_btn.setText("Apply")
            ok_btn.setIcon(_dialog_icon("check_circle", QStyle.SP_DialogApplyButton))
            ok_btn.setIconSize(QSize(20, 20))
        if cancel_btn is not None:
            cancel_btn.setIcon(_dialog_icon("close", QStyle.SP_DialogCancelButton))
            cancel_btn.setIconSize(QSize(20, 20))
        self.reset_btn.setIcon(_dialog_icon("refresh", QStyle.SP_BrowserReload))
        self.reset_btn.setIconSize(QSize(20, 20))

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def reset_defaults(self):
        self.auto_wb_cb.setChecked(False)
        self.auto_color_cb.setChecked(False)
        self.wb_temp_slider.setValue(6500)
        self.wb_temp_spin.setValue(6500)
        self.brightness_slider.setValue(0)
        self.contrast_slider.setValue(0)
        self.saturation_slider.setValue(100)
        self.sharpness_slider.setValue(0)
        self.skin_smoothing_slider.setValue(0)
        self.gamma_slider.setValue(100)
        self.crop_combo.setCurrentText("4x6")

class PhotoPrintSettingsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_instance = parent
        self.setWindowTitle("Photo Printing Settings")
        self.setGeometry(300, 300, 500, 550)
        self.settings = self.parent_instance.settings  # Access settings via parent

        layout = QVBoxLayout()

        # Photo Printing Section
        photo_group = QGroupBox("Photo Printing")
        photo_layout = QFormLayout()

        self.photo_printing_cb = QCheckBox("Enable Photo Printing")
        self.photo_printing_cb.setToolTip("Enable printing of the photo itself")
        photo_layout.addRow("Enable Photo Printing:", self.photo_printing_cb)
        self.photo_printing_cb.setChecked(self.settings.get('photo_printing_enabled', True))  # Initialize

        self.auto_print_photo_cb = QCheckBox("Auto-Print Photo After Capture")
        self.auto_print_photo_cb.setToolTip("Automatically print the photo after each photo capture")
        photo_layout.addRow("Auto-Print Photo:", self.auto_print_photo_cb)
        self.auto_print_photo_cb.setChecked(self.settings.get('auto_print_photo', False)) #Init

        self.photo_access_code_cb = QCheckBox("Print website access code on photo")
        self.photo_access_code_cb.setToolTip("Overlay the website retrieval code on printed photos")
        photo_layout.addRow("Print Access Code:", self.photo_access_code_cb)
        self.photo_access_code_cb.setChecked(self.settings.get('photo_print_access_code', False))

        self.borderless_cb = QCheckBox("Borderless Photo Printing (Zero Margin)")
        self.borderless_cb.setToolTip("Print photos without borders (requires printer support)")
        photo_layout.addRow("Borderless Printing:", self.borderless_cb)
        self.borderless_cb.setChecked(self.settings.get('borderless_photo', False))#Init

        self.printer_combo = self.add_printer_combo()
        photo_layout.addRow("Printer:", self.printer_combo)

        # Paper settings group
        paper_group = QGroupBox("Paper Settings")
        paper_layout = QFormLayout()

        # Paper size
        self.paper_size_combo = QComboBox()
        self.paper_size_combo.addItems(["4x6", "5x7", "8x10", "11x14"])
        self.paper_size_combo.setCurrentText(self.settings.get('photo_paper_size', '4x6'))
        self.paper_size_combo.setToolTip("Select paper size for photo printing")
        paper_layout.addRow("Paper Size:", self.paper_size_combo)

        quality_layout = QHBoxLayout()
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(50, 100)
        self.quality_slider.setValue(self.settings.get('photo_quality', 90))
        self.quality_label = QLabel(f"{self.quality_slider.value()}%")
        self.quality_slider.valueChanged.connect(lambda v: self.quality_label.setText(f"{v}%"))
        quality_layout.addWidget(self.quality_slider)
        quality_layout.addWidget(self.quality_label)
        paper_layout.addRow("Print Quality:", quality_layout)

        self.template_combo = QComboBox()
        self.template_combo.addItems(["Default", "Minimal", "Detailed"])
        self.template_combo.setToolTip("Print layout template style")
        paper_layout.addRow("Template:", self.template_combo)
        self.template_combo.setCurrentText(self.settings.get('print_template', 'Default')) # Init with existing setting

        photo_group.setLayout(photo_layout)
        layout.addWidget(photo_group)

        paper_group.setLayout(paper_layout)
        layout.addWidget(paper_group)

        #Add a button box for the OK and Cancel options
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def add_printer_combo(self):
        printer_layout = QHBoxLayout()
        printer_combo = QComboBox()
        if sys.platform == 'win32':
            printers = [win32print.GetDefaultPrinter()]
            printers += [printer[2] for printer in win32print.EnumPrinters(2)]
            printer_combo.addItems(printers)
            default_printer = self.settings.get('photo_printer', win32print.GetDefaultPrinter())
            index = printer_combo.findText(default_printer)
            if index >= 0:
                printer_combo.setCurrentIndex(index)
        printer_combo.setToolTip("Select default printer for photo output")
        printer_layout.addWidget(printer_combo)
        return printer_combo

    def accept(self):
        """Save settings on OK"""
        self.settings['photo_printing_enabled'] = self.photo_printing_cb.isChecked()
        self.settings['auto_print_photo'] = self.auto_print_photo_cb.isChecked()
        self.settings['photo_print_access_code'] = self.photo_access_code_cb.isChecked()
        self.settings['borderless_photo'] = self.borderless_cb.isChecked()

        # Saves combo text here
        if sys.platform == 'win32':
            self.settings['photo_printer'] = self.printer_combo.currentText()

        self.settings['print_template'] = self.template_combo.currentText()
        self.settings['photo_paper_size'] = self.paper_size_combo.currentText()
        self.settings['photo_quality'] = self.quality_slider.value()
        self.parent_instance.save_settings() # saves the photo setting to main app
        super().accept()


class LocalStorageSettingsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_instance = parent
        self.settings = self.parent_instance.settings

        self.setWindowTitle("Local Storage Settings")
        self.setGeometry(300, 300, 520, 260)

        layout = QVBoxLayout()

        info_label = QLabel(
            "Schoolbooth keeps recent local captures for reprints and upload workflows. "
            "Auto-purge deletes only old dated capture folders created by the app."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        settings_group = QGroupBox("Auto Purge")
        settings_layout = QFormLayout()

        self.auto_purge_cb = QCheckBox("Automatically delete old local captures")
        self.auto_purge_cb.setChecked(self.settings.get('output_auto_purge_enabled', False))
        settings_layout.addRow("Enable Auto Purge:", self.auto_purge_cb)

        self.retention_days_spin = QSpinBox()
        self.retention_days_spin.setRange(1, 365)
        self.retention_days_spin.setValue(int(self.settings.get('output_auto_purge_days', 30)))
        self.retention_days_spin.setSuffix(" days")
        settings_layout.addRow("Keep Local Captures For:", self.retention_days_spin)

        output_dir = os.path.abspath(os.path.expanduser(self.settings.get('output_dir', os.path.expanduser('~/Pictures'))))
        self.output_dir_label = QLabel(output_dir)
        self.output_dir_label.setWordWrap(True)
        settings_layout.addRow("Output Folder:", self.output_dir_label)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        button_row = QHBoxLayout()

        purge_now_button = QPushButton("Purge Now")
        purge_now_button.clicked.connect(self.purge_now)
        button_row.addWidget(purge_now_button)

        button_row.addStretch()
        layout.addLayout(button_row)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def purge_now(self):
        self._apply_pending_settings()
        result = self.parent_instance.purge_local_storage(manual=True)

        if result['enabled']:
            QMessageBox.information(
                self,
                "Auto Purge Complete",
                f"Deleted {result['deleted_count']} old folder(s).\n"
                f"Skipped {result['skipped_count']} folder(s) with unexpected contents."
            )
        else:
            QMessageBox.information(
                self,
                "Auto Purge Disabled",
                "Enable auto purge first to run retention cleanup."
            )

    def _apply_pending_settings(self):
        self.settings['output_auto_purge_enabled'] = self.auto_purge_cb.isChecked()
        self.settings['output_auto_purge_days'] = self.retention_days_spin.value()

    def accept(self):
        self._apply_pending_settings()
        self.parent_instance.save_settings()
        super().accept()

import sys
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QLineEdit, QPushButton, QDialogButtonBox,
                             QMessageBox, QApplication, QFormLayout, QGroupBox,
                             QSpinBox, QCheckBox, QTextEdit)  # Import QTextEdit
from PyQt5.QtCore import Qt

class QRPrintSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_instance = parent
        self.setWindowTitle("QR Label Printing Settings")
        self.setGeometry(300, 300, 620, 780)

        self.settings = self.parent_instance.settings

        layout = QVBoxLayout()

        # 1. General Settings
        general_group = QGroupBox("General Settings")
        general_layout = QFormLayout()

        self.qr_printing_cb = QCheckBox("Enable QR Code Printing")
        self.qr_printing_cb.setChecked(self.settings.get('qr_printing_enabled', True))
        general_layout.addRow("Enable QR Printing:", self.qr_printing_cb)

        self.auto_print_qr_cb = QCheckBox("Auto-Print QR After Capture")
        self.auto_print_qr_cb.setChecked(self.settings.get('auto_print_qr', False))
        general_layout.addRow("Auto-Print QR:", self.auto_print_qr_cb)

        self.show_qr_print_preview_cb = QCheckBox("Show QR Print Preview")
        self.show_qr_print_preview_cb.setChecked(self.settings.get('show_qr_print_preview', False))
        general_layout.addRow("Show Preview:", self.show_qr_print_preview_cb)

        self.qr_access_code_cb = QCheckBox("Print website access code on QR labels")
        self.qr_access_code_cb.setChecked(self.settings.get('qr_print_access_code', True))
        general_layout.addRow("Print Access Code:", self.qr_access_code_cb)

        general_group.setLayout(general_layout)
        layout.addWidget(general_group)

        # 2. Printer Selection
        printer_group = QGroupBox("Printer Selection")
        printer_layout = QFormLayout()

        self.print_mode_combo = QComboBox()
        self.print_mode_combo.addItems(["Standard Printer", "Thermal Printer"])
        self.print_mode_combo.setCurrentText(self.settings.get('qr_print_mode', "Standard Printer"))
        self.print_mode_combo.currentTextChanged.connect(self.update_visibility)
        printer_layout.addRow("Print Mode:", self.print_mode_combo)

        self.mode_help_label = QLabel()
        self.mode_help_label.setWordWrap(True)
        self.mode_help_label.setStyleSheet("color: #555;")
        printer_layout.addRow("Mode Notes:", self.mode_help_label)

        # Standard Printer Selection
        self.standard_printer_combo = QComboBox()
        if sys.platform == 'win32':
            printers = [win32print.GetDefaultPrinter()]
            printers += [printer[2] for printer in win32print.EnumPrinters(2)]
            self.standard_printer_combo.addItems(printers)
        self.standard_printer_combo.setCurrentText(self.settings.get('qr_printer', win32print.GetDefaultPrinter()))
        self.standard_printer_label = QLabel("Standard Printer:")
        printer_layout.addRow(self.standard_printer_label, self.standard_printer_combo)

        # Thermal Printer Settings
        self.com_port_combo = QComboBox()
        self.populate_com_ports()
        self.com_port_label = QLabel("Thermal COM Port:")
        printer_layout.addRow(self.com_port_label, self.com_port_combo)

        printer_group.setLayout(printer_layout)
        layout.addWidget(printer_group)

        # 3. Thermal Printer Settings
        thermal_group = QGroupBox("Thermal Receipt Printer (ESC/POS)")
        self.thermal_group = thermal_group
        thermal_layout = QFormLayout()

        self.thermal_limit_label = QLabel(
            "Thermal mode is limited: receipt formatting only, no standard page margins, minimal typography."
        )
        self.thermal_limit_label.setWordWrap(True)
        self.thermal_limit_label.setStyleSheet("color: #666;")
        thermal_layout.addRow(self.thermal_limit_label)

        self.qr_size_spin = QSpinBox()
        self.qr_size_spin.setRange(1, 8)
        self.qr_size_spin.setValue(self.settings.get('qr_module_size', 3))
        self.qr_size_spin.setToolTip("Thermal-friendly QR density. Higher values may fail on low-resolution heads.")
        thermal_layout.addRow("QR Module Size:", self.qr_size_spin)

        self.qr_error_correction_combo = QComboBox()
        self.qr_error_correction_combo.addItems(["L", "M", "Q", "H"])
        self.qr_error_correction_combo.setCurrentText(self.settings.get('qr_error_correction', "M"))
        thermal_layout.addRow("Error Correction:", self.qr_error_correction_combo)

        self.advanced_thermal_cb = QCheckBox("Show Advanced Thermal Options")
        self.advanced_thermal_cb.setChecked(self.settings.get('thermal_advanced_options', False))
        thermal_layout.addRow(self.advanced_thermal_cb)

        advanced_thermal_group = QGroupBox("Advanced Thermal Formatting")
        self.advanced_thermal_group = advanced_thermal_group
        advanced_thermal_layout = QFormLayout()

        self.text_font_combo = QComboBox()
        self.text_font_combo.addItems(["A", "B"])
        saved_font = self.settings.get('text_font_type', "A")
        self.text_font_combo.setCurrentText(saved_font if saved_font in ["A", "B"] else "A")
        advanced_thermal_layout.addRow("Receipt Font:", self.text_font_combo)

        self.header_bold_cb = QCheckBox("Header Bold")
        self.header_bold_cb.setChecked(self.settings.get('qr_header_bold', False))
        advanced_thermal_layout.addRow("Header Bold:", self.header_bold_cb)

        self.footer_bold_cb = QCheckBox("Footer Bold")
        self.footer_bold_cb.setChecked(self.settings.get('qr_footer_bold', False))
        advanced_thermal_layout.addRow("Footer Bold:", self.footer_bold_cb)

        self.header_ul_cb = QCheckBox("Header Underline")
        self.header_ul_cb.setChecked(self.settings.get('qr_header_ul', False))
        advanced_thermal_layout.addRow("Header Underline:", self.header_ul_cb)

        self.footer_ul_cb = QCheckBox("Footer Underline")
        self.footer_ul_cb.setChecked(self.settings.get('qr_footer_ul', False))
        advanced_thermal_layout.addRow("Footer Underline:", self.footer_ul_cb)

        advanced_thermal_group.setLayout(advanced_thermal_layout)
        thermal_layout.addRow(advanced_thermal_group)

        thermal_group.setLayout(thermal_layout)
        layout.addWidget(thermal_group)

        # 4. Design Space
        design_group = QGroupBox("Design Settings")
        design_layout = QFormLayout()

        self.header_edit = QTextEdit(self.settings.get('qr_header', ""))
        design_layout.addRow("Header Text:", self.header_edit)

        self.footer_edit = QTextEdit(self.settings.get('qr_footer', ""))
        design_layout.addRow("Footer Text:", self.footer_edit)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 36)
        self.font_size_spin.setValue(self.settings.get('qr_font_size', 12))
        design_layout.addRow("Font Size:", self.font_size_spin)

        design_group.setLayout(design_layout)
        layout.addWidget(design_group)

        # 5. Standard Print Settings
        standard_group = QGroupBox("Standard Printer Layout")
        self.standard_group = standard_group
        standard_layout = QFormLayout()

        self.paper_size_combo = QComboBox()
        self.paper_size_combo.addItems(["4x6", "5x7", "8.5x11", "A4"])
        self.paper_size_combo.setCurrentText(self.settings.get('qr_paper_size', '4x6'))
        standard_layout.addRow("Paper Size:", self.paper_size_combo)

        self.margin_top_spin = QSpinBox()
        self.margin_top_spin.setRange(0, 50)
        self.margin_top_spin.setValue(self.settings.get('qr_margin_top', 10))
        standard_layout.addRow("Margin Top (pixels):", self.margin_top_spin)

        self.margin_left_spin = QSpinBox()
        self.margin_left_spin.setRange(0, 50)
        self.margin_left_spin.setValue(self.settings.get('qr_margin_left', 10))
        standard_layout.addRow("Margin Left (pixels):", self.margin_left_spin)

        self.margin_right_spin = QSpinBox()
        self.margin_right_spin.setRange(0, 50)
        self.margin_right_spin.setValue(self.settings.get('qr_margin_right', 10))
        standard_layout.addRow("Margin Right (pixels):", self.margin_right_spin)

        self.margin_bottom_spin = QSpinBox()
        self.margin_bottom_spin.setRange(0, 50)
        self.margin_bottom_spin.setValue(self.settings.get('qr_margin_bottom', 10))
        standard_layout.addRow("Margin Bottom (pixels):", self.margin_bottom_spin)

        standard_group.setLayout(standard_layout)
        layout.addWidget(standard_group)

        # 6. Button Layout
        button_layout = QHBoxLayout()

        self.test_print_btn = QPushButton("Test Print")
        self.test_print_btn.clicked.connect(self.test_print)
        button_layout.addWidget(self.test_print_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

        # 7. Button Box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

        self.advanced_thermal_cb.toggled.connect(self._toggle_thermal_advanced)
        self._toggle_thermal_advanced(self.advanced_thermal_cb.isChecked())

        # Load Settings
        self.header_bold_cb.setChecked(self.settings.get('qr_header_bold', False))
        self.footer_bold_cb.setChecked(self.settings.get('qr_footer_bold', False))
        self.header_ul_cb.setChecked(self.settings.get('qr_header_ul', False))
        self.footer_ul_cb.setChecked(self.settings.get('qr_footer_ul', False))

        # Initial Visibility - MOST IMPORTANT
        self.update_visibility()

    def populate_com_ports(self):
        """Populate the COM port combo box with available ports."""
        ports = self.get_serial_ports()
        self.com_port_combo.clear()
        self.com_port_combo.addItems(ports)

        # Set the current COM port, if it exists in the settings
        current_port = self.settings.get('com_port', '')
        if current_port in ports:
            self.com_port_combo.setCurrentText(current_port)

    def get_serial_ports(self):
        """Lists serial port names

            :raises EnvironmentError:
                On unsupported or unknown platforms

            :returns:
                A list of the serial ports available on the system
        """
        import serial.tools.list_ports
        ports = [port.device for port in serial.tools.list_ports.comports()]
        return ports

    def save_settings(self):
        """Save all settings, handling potential COM port errors"""
        try:
            com_port = self.com_port_combo.currentText()
            mode = self.print_mode_combo.currentText()

            # Validate COM port presence (only if Thermal Printer is selected)
            if mode == "Thermal Printer":
                ports = self.get_serial_ports()  # Get available ports
                if ports and com_port not in ports:
                    raise ValueError(
                        f"COM port '{com_port}' not found. Please select a valid port."
                    )
                if not com_port:
                    raise ValueError("Select a COM port for thermal printing.")

            module_size = self.qr_size_spin.value()
            if not 1 <= module_size <= 8:
                raise ValueError("QR Module Size must be between 1 and 8 for thermal mode.")

            error_correction = self.qr_error_correction_combo.currentText()
            if error_correction not in ["L", "M", "Q", "H"]:
                raise ValueError("Invalid Error Correction Level.")

            font_type = self.text_font_combo.currentText()
            if font_type not in ["A", "B"]:
                raise ValueError("Invalid Text Font.")

            self.settings.update({
                'qr_printing_enabled': self.qr_printing_cb.isChecked(),
                'qr_print_access_code': self.qr_access_code_cb.isChecked(),
                'auto_print_qr': self.auto_print_qr_cb.isChecked(),
                'show_qr_print_preview': self.show_qr_print_preview_cb.isChecked() if mode == "Standard Printer" else False,

                # Printer settings
                'qr_print_mode': self.print_mode_combo.currentText(),
                'qr_printer': self.standard_printer_combo.currentText(),
                'com_port': com_port,

                # Thermal printer settings
                'qr_module_size': module_size,
                'qr_error_correction': error_correction,
                'text_font_type': font_type,
                'thermal_advanced_options': self.advanced_thermal_cb.isChecked(),
                'qr_header_bold': self.header_bold_cb.isChecked(),
                'qr_footer_bold': self.footer_bold_cb.isChecked(),
                'qr_header_ul': self.header_ul_cb.isChecked(),
                'qr_footer_ul': self.footer_ul_cb.isChecked(),

                # Design settings
                'qr_header': self.header_edit.toPlainText(),
                'qr_footer': self.footer_edit.toPlainText(),
                'qr_font_size': self.font_size_spin.value(),

                # Standard print settings
                'qr_paper_size': self.paper_size_combo.currentText(),
                'qr_margin_top': self.margin_top_spin.value(),
                'qr_margin_left': self.margin_left_spin.value(),
                'qr_margin_right': self.margin_right_spin.value(),
                'qr_margin_bottom': self.margin_bottom_spin.value(),
            })
            self.parent_instance.save_settings()  # Save to main settings
            QMessageBox.information(self, "Settings Saved", "Settings saved successfully.")

        except ValueError as ve:
            QMessageBox.critical(self, "Settings Error", str(ve))  # More descriptive error
        except Exception as e:
            QMessageBox.critical(self, "Settings Error", f"Error saving settings: {str(e)}")

    def accept(self):
        """Save all settings when OK is clicked"""
        self.save_settings()
        super().accept()

    def _toggle_thermal_advanced(self, enabled):
        self.advanced_thermal_group.setVisible(enabled)

    def update_visibility(self):
        """Show/hide settings based on print mode."""
        mode = self.print_mode_combo.currentText()
        thermal_visible = mode == "Thermal Printer"
        standard_visible = mode == "Standard Printer"

        self.com_port_label.setVisible(thermal_visible)
        self.com_port_combo.setVisible(thermal_visible)
        self.standard_printer_label.setVisible(standard_visible)
        self.standard_printer_combo.setVisible(standard_visible)

        self.thermal_group.setVisible(thermal_visible)
        self.standard_group.setVisible(standard_visible)

        self.show_qr_print_preview_cb.setEnabled(standard_visible)
        if thermal_visible:
            self.show_qr_print_preview_cb.setChecked(False)

        self.advanced_thermal_cb.setVisible(thermal_visible)
        self.advanced_thermal_group.setVisible(thermal_visible and self.advanced_thermal_cb.isChecked())

        # Font size only affects standard page layout output.
        self.font_size_spin.setEnabled(standard_visible)

        if thermal_visible:
            self.mode_help_label.setText(
                "Thermal mode prints compact ESC/POS receipts. Essentials are COM port + QR module size + error correction."
            )
        else:
            self.mode_help_label.setText(
                "Standard mode prints full-page layouts using a Windows printer with paper size and margin controls."
            )

    def test_print(self):
        """Test print function with fake data."""
        print_mode = self.print_mode_combo.currentText()
        if print_mode == "Thermal Printer":
            try:
                # Thermal printer test
                com_port = self.com_port_combo.currentText()
                header_text = self.header_edit.toPlainText()
                footer_text = self.footer_edit.toPlainText()

                # Fake data for testing
                capture_label = self.parent_instance.settings.get('capture_label', 'Session')
                access_code = "AB7K-4M2Q"
                test_url = "https://www.example.com/test"

                self.parent_instance.print_qr_code_thermal(test_url, capture_label, access_code, header_text,
                                                           footer_text, com_port)  # Pass settings
            except Exception as e:
                QMessageBox.critical(self, "Connection Failed", f"Error: {str(e)}")

        else:
            # Standard printer test (PDF)
            qr_header = self.header_edit.toPlainText()
            qr_footer = self.footer_edit.toPlainText()
            qr_font_size = self.font_size_spin.value()
            paper_size = self.paper_size_combo.currentText()
            qr_margin_top = self.margin_top_spin.value()
            qr_margin_left = self.margin_left_spin.value()
            qr_margin_right = self.margin_right_spin.value()
            qr_margin_bottom = self.margin_bottom_spin.value()
            printer_name = self.standard_printer_combo.currentText()
            capture_label = self.parent_instance.settings.get('capture_label', 'Session')
            access_code = "AB7K-4M2Q"
            test_url = "https://www.example.com/test"
            self.parent_instance.print_qr_code_standard(test_url, capture_label, printer_name, qr_header, qr_footer,
                                                        qr_font_size, paper_size, qr_margin_top, qr_margin_left,
                                                        qr_margin_right, qr_margin_bottom, access_code)


class UpdateCheckWorker(QThread):
    """Background thread that queries the GitHub Releases API."""
    update_available = pyqtSignal(str, str)   # (latest_version, release_url)
    up_to_date       = pyqtSignal(str)         # (current_version,)
    check_error      = pyqtSignal(str)         # (error_message,)

    def run(self):
        api_url = (
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        )
        try:
            req = urllib_request.Request(
                api_url,
                headers={"User-Agent": f"Schoolbooth/{APP_VERSION}"}
            )
            with urllib_request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            latest_tag = data.get("tag_name", "").lstrip("v")
            html_url   = data.get("html_url", "")
        except Exception as exc:
            self.check_error.emit(str(exc))
            return

        def _ver(v):
            parts = [p for p in v.split(".") if p.isdigit()]
            return tuple(int(p) for p in parts)

        if _ver(latest_tag) > _ver(APP_VERSION):
            self.update_available.emit(latest_tag, html_url)
        else:
            self.up_to_date.emit(APP_VERSION)


class HealthCheckWorker(QThread):
    """Background thread that checks camera, internet, WordPress, and printer health."""
    results_ready = pyqtSignal(dict)

    def __init__(self, settings, cap=None, parent=None):
        super().__init__(parent)
        # Snapshot the raw data dict for thread-safe access
        raw = settings._data if hasattr(settings, '_data') else settings
        self.settings = dict(raw)
        self.cap = cap

    def run(self):
        import socket
        results = {}

        # --- Camera ---
        if self.cap and self.cap.isOpened():
            results['camera'] = ('ok', 'Ready')
        else:
            results['camera'] = ('error', 'Not connected')

        # --- Internet ---
        try:
            sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
            sock.close()
            results['internet'] = ('ok', 'Connected')
        except Exception:
            results['internet'] = ('error', 'No internet')

        # --- WordPress ---
        wp_url = self.settings.get('wp_url', '').strip()
        if not wp_url:
            results['wordpress'] = ('warn', 'Not configured')
        else:
            try:
                import hmac as _hmac, hashlib as _hashlib, json as _json, time as _time
                ping_url = wp_url.rstrip('/') + '/wp-json/pta-schoolbooth/v1/ping'
                secret = self.settings.get('wp_shared_secret', '').strip()
                timestamp = str(int(_time.time()))
                if len(secret) >= 32:
                    sig = _hmac.new(secret.encode(), (timestamp + '|ping').encode(), _hashlib.sha256).hexdigest()
                    headers = {
                        "User-Agent": f"Schoolbooth/{APP_VERSION}",
                        "Content-Type": "application/json",
                        "X-PTASB-Timestamp": timestamp,
                        "X-PTASB-Signature": sig,
                    }
                else:
                    # No secret configured — still try, expect 401/500 but confirms reachability
                    headers = {
                        "User-Agent": f"Schoolbooth/{APP_VERSION}",
                        "Content-Type": "application/json",
                    }
                body = _json.dumps({}).encode()
                req = urllib_request.Request(ping_url, data=body, headers=headers, method='POST')
                with urllib_request.urlopen(req, timeout=6) as resp:
                    results['wordpress'] = (
                        ('ok', 'Reachable') if resp.getcode() == 200
                        else ('warn', f'HTTP {resp.getcode()}')
                    )
            except urllib_error.HTTPError as e:
                if e.code in (401, 403, 500):
                    # Auth failure but server is reachable
                    results['wordpress'] = ('warn', f'Reachable (HTTP {e.code})')
                else:
                    results['wordpress'] = ('warn', f'HTTP {e.code}')
            except Exception:
                results['wordpress'] = ('error', 'Unreachable')

        # --- Photo printer ---
        photo_printer = self.settings.get('photo_printer', '').strip()
        if not photo_printer:
            results['photo_printer'] = ('warn', 'Not selected')
        elif win32print is None:
            results['photo_printer'] = ('warn', 'N/A')
        else:
            results['photo_printer'] = self._check_win32_printer(photo_printer)

        # --- QR / receipt printer ---
        qr_print_mode = self.settings.get('qr_print_mode', 'Standard Printer')
        if qr_print_mode == 'Thermal Printer':
            com_port = self.settings.get('com_port', '').strip()
            if not com_port:
                results['qr_printer'] = ('warn', 'COM port not set')
            else:
                try:
                    import serial
                    s = serial.Serial(com_port, timeout=0.3)
                    s.close()
                    results['qr_printer'] = ('ok', f'Thermal {com_port}')
                except Exception:
                    results['qr_printer'] = ('error', f'{com_port} unavailable')
        else:
            qr_printer = self.settings.get('qr_printer', '').strip()
            if not qr_printer:
                results['qr_printer'] = ('warn', 'Not selected')
            elif win32print is None:
                results['qr_printer'] = ('warn', 'N/A')
            else:
                results['qr_printer'] = self._check_win32_printer(qr_printer)

        self.results_ready.emit(results)

    @staticmethod
    def _check_win32_printer(name):
        try:
            handle = win32print.OpenPrinter(name)
            info = win32print.GetPrinter(handle, 2)
            win32print.ClosePrinter(handle)
            status = info.get('Status', 0)
            if status == 0:
                return ('ok', 'Ready')
            elif status & 0x00000080:
                return ('error', 'Offline')
            elif status & 0x00000020:
                return ('error', 'Paper out')
            elif status & 0x00000008:
                return ('error', 'Error')
            elif status & 0x00000001:
                return ('warn', 'Paused')
            return ('warn', f'Status {status:#x}')
        except Exception:
            return ('error', 'Not found')


class CameraApp(QMainWindow):

    def __init__(self):
        super().__init__()
        print("CameraApp __init__ called.")

        # Initialize settings manager (single source of truth)
        self.settings = SettingsManager('camera_settings.json')
        
        self.setWindowTitle("Schoolbooth")
        self.setGeometry(100, 100, 1400, 800)

        # Initialize data and state
        self.unsaved_changes = False
        self.last_captured = None
        self.last_capture_name = self.settings.get('capture_label', 'Session')
        self.last_access_code = ''
        self.settings['capture_label'] = self.last_capture_name
        self.update_check_status = "Not checked yet"
        self.latest_release_version = APP_VERSION
        self._update_check_silent = False

        # Initialize available cameras
        self.available_cameras = self.get_available_cameras()

        # Initialize camera_index from settings
        self.camera_index = self.settings.get('camera_index', 0)

        # Initialize the camera *after* settings are loaded
        self.cap = self.initialize_camera()

        # Watermark interaction state
        self.watermark_dragging = False
        self.watermark_resizing = False
        self.watermark_rotating = False
        self.watermark_start_pos = QPoint()
        self.watermark_start_x = 0
        self.watermark_start_y = 0
        self.watermark_start_rotation = 0
        self.watermark_start_scale = 1.0
        self.watermark_handle_radius = 12
        self._watermark_edit_state = None
        self.current_frame_size = (0, 0)
        self.settings['watermark_interactive'] = self.settings.get('watermark_interactive', False)
        self.settings['watermark_snap_grid'] = self.settings.get('watermark_snap_grid', True)
        self.settings['watermark_snap_grid_step'] = int(self.settings.get('watermark_snap_grid_step', 5))
        self.settings['watermark_snap_center'] = self.settings.get('watermark_snap_center', True)

        self.watermark_original = None
        self.watermark_processed = None
        self.watermark_img = None
        self.overlay_buttons = {}
        self.active_overlay_key = None  # currently selected frame: FRAME_1..FRAME_4, CUSTOM, or None
        self._overlay_frame_settings = self._load_overlay_frame_settings()

        # Initialize menu before other UI elements
        self.create_menu()

        # Initialize UI
        self.init_ui()

        # Load button icons after UI is created
        self.load_button_icons()

        # Setup touch UI
        self.setup_touch_ui(enable=self.settings['touch_mode'])

        # Load watermark if path exists, restoring its per-frame settings first
        watermark_path = self.settings['watermark_path']
        if watermark_path and os.path.exists(watermark_path):
            self.active_overlay_key = self._path_to_overlay_key(watermark_path)
            if self.active_overlay_key:
                self._apply_frame_settings(self.active_overlay_key)
            self.load_watermark(watermark_path)

        self.purge_local_storage()

        # Initialize timers now that everything is set up
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

        # Health status — initial check after 2s, then every 30s
        self._health_worker = None
        QTimer.singleShot(2000, self._run_health_check)
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._run_health_check)
        self._health_timer.start(30000)

    def toggle_touch_mode(self):
        self.settings["touch_mode"] = self.touch_mode_btn.isChecked()
        self.setup_touch_ui(enable=self.settings["touch_mode"])
        status = "ON" if self.settings["touch_mode"] else "OFF"
        self.touch_mode_btn.setText(f"Touch Mode: {status}")
        self.touch_mode_btn.setToolTip(f"Touch-friendly interface is {status}")

    # ------------------------------------------------------------------
    # Health status panel
    # ------------------------------------------------------------------
    def _run_health_check(self):
        """Spawn background check for all health items; show pending state."""
        # Show button as pending (grey with "Checking...")
        self._status_btn.setText("Checking…")
        self._status_btn.setIcon(self._get_action_icon("refresh", QStyle.SP_BrowserReload, size=20))
        self._status_btn.setIconSize(QSize(20, 20))
        self._status_btn.setStyleSheet("""
            QPushButton {
                background-color: #aaa;
                color: white;
                font-weight: bold;
                font-size: 15px;
                border: none;
                border-radius: 8px;
            }
        """)

        try:
            if self._health_worker and self._health_worker.isRunning():
                return  # already in progress
        except RuntimeError:
            self._health_worker = None

        worker = HealthCheckWorker(self.settings, cap=self.cap)
        worker.results_ready.connect(self._on_health_results)
        worker.start()
        self._health_worker = worker

    def _on_health_results(self, results):
        # Store results for detail popup
        self._last_health_results = results
        
        # Count errors and warnings
        checks = ['camera', 'internet', 'wordpress', 'photo_printer', 'qr_printer']
        error_count = 0
        warn_count = 0
        for check in checks:
            state, _ = results.get(check, ('warn', '?'))
            if state == 'error':
                error_count += 1
            elif state == 'warn':
                warn_count += 1
        
        # Determine overall status: green if all ok, red if any errors, orange if warnings
        total_checks = len(checks)
        if error_count > 0:
            color = '#e74c3c'  # red
            text = f"{error_count} of {total_checks} Errors"
        elif warn_count > 0:
            color = '#f39c12'  # orange
            text = f"{warn_count} of {total_checks} Warnings"
        else:
            color = '#2ecc71'  # green
            text = "Ready"
        
        # Update button
        self._status_btn.setText(text)
        if error_count > 0:
            self._status_btn.setIcon(self._get_action_icon("error", QStyle.SP_MessageBoxCritical, size=20))
        elif warn_count > 0:
            self._status_btn.setIcon(self._get_action_icon("warning", QStyle.SP_MessageBoxWarning, size=20))
        else:
            self._status_btn.setIcon(self._get_action_icon("check_circle", QStyle.SP_DialogApplyButton, size=20))
        self._status_btn.setIconSize(QSize(20, 20))
        self._status_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                font-weight: bold;
                font-size: 15px;
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: {self._darken_color(color)};
            }}
            QPushButton:pressed {{
                background-color: {self._darken_color(color, 2)};
            }}
        """)
        self._health_worker = None  # allow next run

    @staticmethod
    def _darken_color(hex_color, amount=1):
        """Darken a hex color by reducing RGB values."""
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        r = max(0, r - (20 * amount))
        g = max(0, g - (20 * amount))
        b = max(0, b - (20 * amount))
        return f'#{r:02x}{g:02x}{b:02x}'

    def _show_status_details(self):
        """Show detailed status in a popup dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("System Health Status")
        dialog.setMinimumWidth(440)
        self.apply_modern_settings_dialog_style(dialog)
        self.center_dialog(dialog)
        
        layout = QVBoxLayout()
        layout.setSpacing(12)
        
        # Title
        title = QLabel("System Health Details")
        title.setStyleSheet("font-weight: 700; font-size: 16px;")
        layout.addWidget(title)
        
        # Status rows
        checks_info = [
            ('camera', 'Camera', self._last_health_results.get('camera', ('warn', '?'))),
            ('internet', 'Internet', self._last_health_results.get('internet', ('warn', '?'))),
            ('wordpress', 'WordPress', self._last_health_results.get('wordpress', ('warn', '?'))),
            ('photo_printer', 'Photo Printer', self._last_health_results.get('photo_printer', ('warn', '?'))),
            ('qr_printer', 'QR Printer', self._last_health_results.get('qr_printer', ('warn', '?'))),
        ]
        
        for _, name, (state, message) in checks_info:
            row = QHBoxLayout()
            color = {'ok': '#2ecc71', 'warn': '#f39c12', 'error': '#e74c3c'}.get(state, '#aaa')
            
            # Dot
            dot = QLabel("●")
            dot.setFixedWidth(18)
            dot.setStyleSheet(f"color: {color}; font-size: 16px;")
            
            # Name
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size: 14px; font-weight: 700; min-width: 110px;")
            
            # Status
            status_lbl = QLabel(message)
            status_lbl.setStyleSheet(f"color: {color}; font-size: 14px;")
            
            row.addWidget(dot)
            row.addWidget(name_lbl)
            row.addWidget(status_lbl)
            row.addStretch()
            layout.addLayout(row)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.setLayout(layout)
        dialog.exec()

    def setup_touch_ui(self, enable=True):
        """Configure UI elements for better touch screen compatibility"""
        if not enable:
            self.setStyleSheet("")  # Clear custom styles
            return

        self.setStyleSheet("""
            QPushButton {
                min-width: 100px;
                min-height: 50px;
                font-size: 16px;
                padding: 10px;
            }
            QMenuBar {
                font-size: 18px;
            }
            QMenuBar::item {
                padding: 10px 15px;
            }
            QMenu {
                font-size: 16px;
            }
            QComboBox, QLineEdit, QSpinBox {
                min-height: 40px;
                font-size: 16px;
            }
            QLabel {
                font-size: 16px;
            }
        """)

        # Make main capture button larger
        self.capture_btn.setMinimumSize(200, 80)
        self.capture_btn.setStyleSheet("font-size: 24px; padding: 15px;")

        # Add touch-friendly scroll areas
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.centralWidget())
        self.setCentralWidget(scroll)

    def create_menu(self):
        menu_bar = self.menuBar()
        menu_bar.clear()

        file_menu = menu_bar.addMenu("File")
        open_output_action = file_menu.addAction("Open Output Folder", self.open_output_dir)
        file_menu.addSeparator()
        save_config_action = file_menu.addAction("Save Configuration", self.save_settings)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit", self.close)

        capture_menu = menu_bar.addMenu("Capture")
        capture_photo_action = capture_menu.addAction("Capture Photo", self.capture_image)

        camera_menu = menu_bar.addMenu("Camera")
        camera_select_action = camera_menu.addAction("Select Camera", self.select_camera)
        camera_menu.addSeparator()
        rotate_left_action = camera_menu.addAction("Rotate Left 90°", lambda: self.rotate_image(-90))
        rotate_right_action = camera_menu.addAction("Rotate Right 90°", lambda: self.rotate_image(90))

        image_menu = menu_bar.addMenu("Image")
        image_settings_action = image_menu.addAction("Image Settings", self.open_image_settings)
        watermark_settings_action = image_menu.addAction("Watermark Settings", self.open_watermark_settings)
        remove_watermark_action = image_menu.addAction("Remove Watermark", self.remove_watermark)

        print_menu = menu_bar.addMenu("Print")
        photo_print_settings_action = print_menu.addAction("Photo Print Settings", self.open_photo_print_settings)
        qr_label_settings_action = print_menu.addAction("QR Label Settings", self.open_qr_print_settings)

        settings_menu = menu_bar.addMenu("Settings")
        local_storage_action = settings_menu.addAction("Local Storage", self.open_local_storage_settings)
        wordpress_action = settings_menu.addAction("WordPress", self.open_wp_settings)
        hid_mapping_action = settings_menu.addAction("HID Mapping", self.open_hid_mapping_dialog)

        view_menu = menu_bar.addMenu("View")
        self.crop_lines_action = view_menu.addAction("Show Crop Guides")
        self.crop_lines_action.setCheckable(True)
        self.crop_lines_action.setChecked(self.settings["show_crop_overlay"])
        self.crop_lines_action.triggered.connect(self.toggle_crop_overlay)

        help_menu = menu_bar.addMenu("Help")
        check_updates_action = help_menu.addAction("Check for Updates", self.check_for_updates)
        help_menu.addSeparator()
        about_action = help_menu.addAction("About", self.show_about)

        # Icon pass for clearer touch targets and faster menu scanning.
        action_icons = [
            (open_output_action, "folder_open", QStyle.SP_DirOpenIcon),
            (save_config_action, "save", QStyle.SP_DialogSaveButton),
            (exit_action, "close", QStyle.SP_DialogCloseButton),
            (capture_photo_action, "photo_camera", QStyle.SP_DialogOpenButton),
            (camera_select_action, "photo_camera", QStyle.SP_ComputerIcon),
            (rotate_left_action, "rotate_left", QStyle.SP_BrowserReload),
            (rotate_right_action, "rotate_right", QStyle.SP_BrowserReload),
            (image_settings_action, "tune", QStyle.SP_FileDialogDetailedView),
            (watermark_settings_action, "settings", QStyle.SP_FileDialogInfoView),
            (remove_watermark_action, "delete", QStyle.SP_TrashIcon),
            (photo_print_settings_action, "print", QStyle.SP_DialogSaveButton),
            (qr_label_settings_action, "qr_code", QStyle.SP_DialogSaveButton),
            (local_storage_action, "settings", QStyle.SP_FileDialogContentsView),
            (wordpress_action, "settings", QStyle.SP_DirIcon),
            (hid_mapping_action, "settings", QStyle.SP_TitleBarMenuButton),
            (self.crop_lines_action, "crop", QStyle.SP_FileDialogListView),
            (check_updates_action, "refresh", QStyle.SP_BrowserReload),
            (about_action, "info", QStyle.SP_MessageBoxInformation),
        ]
        for action, material_name, fallback in action_icons:
            action.setIcon(self._get_action_icon(material_name, fallback, size=22))

    def open_hid_mapping_dialog(self):
        dialog = HIDMappingDialog(self, settings=self.settings)
        self.apply_modern_settings_dialog_style(dialog)
        self.center_dialog(dialog)
        dialog.exec_()

    def apply_modern_settings_dialog_style(self, dialog):
        """Apply a touch/mouse-friendly visual layer to settings dialogs."""
        if dialog is None:
            return
        dialog.setStyleSheet("""
            QDialog {
                background: #f7f9fc;
            }
            QGroupBox {
                font-size: 16px;
                font-weight: 600;
                border: 1px solid #d9e0ea;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 14px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLabel {
                font-size: 15px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QListWidget {
                min-height: 44px;
                font-size: 15px;
                padding: 6px 10px;
            }
            QCheckBox {
                spacing: 10px;
                font-size: 15px;
                min-height: 36px;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
            }
            QPushButton {
                min-height: 44px;
                padding: 6px 14px;
                font-size: 15px;
            }
            QDialogButtonBox QPushButton {
                min-width: 136px;
                min-height: 44px;
            }
            QSlider::groove:horizontal {
                height: 10px;
                border-radius: 5px;
                background: #d4dbe6;
            }
            QSlider::handle:horizontal {
                width: 28px;
                margin: -9px 0;
                border-radius: 14px;
                background: #2a82da;
            }
        """)

    def keyPressEvent(self, event):
        # Check if a HID device is selected and this event comes from it
        device_id = self.settings.get('hid_device_id')
        # Check if this key event matches the Capture Image mapping
        capture_mapping = self.settings.get('hid_map_capture_image')
        if capture_mapping:
            key_name, key_code = capture_mapping.split('(')
            key_code = key_code[:-1]  # Remove the closing parenthesis
            if str(event.key()) == key_code:
                self.capture_image()
        else:
            super().keyPressEvent(event)  # call normal keypress

    def open_output_dir(self):
        output_dir = self.settings.get("output_dir", os.path.expanduser("~/Pictures"))
        output_dir = os.path.abspath(os.path.expanduser(output_dir))
        os.makedirs(output_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(output_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", output_dir])
        else:
            subprocess.Popen(["xdg-open", output_dir])

    def select_photo_printer(self):
        if sys.platform == 'win32':
            printers = [win32print.GetDefaultPrinter()]
            printers += [printer[2] for printer in win32print.EnumPrinters(2)]
            printer, ok = QInputDialog.getItem(
                self, "Select Photo Printer",
                "Available Printers:", printers, 0, False
            )
            if ok and printer:
                self.photo_printer = printer
                self.settings['photo_printer'] = printer
                QMessageBox.information(self, "Printer Selected",
                                        f"Photo printer set to: {printer}")
                self.save_settings()

    def remove_watermark(self):
        """Remove watermark via the Image menu (clears + notifies user)."""
        self.clear_overlay()
        QMessageBox.information(self, "Watermark Removed", "Watermark has been removed from the system.")

    def check_for_updates(self, silent=False):
        """Query GitHub Releases for a newer version (runs in background thread)."""
        self._update_check_silent = bool(silent)
        self.update_check_status = "Checking GitHub..."
        self._update_worker = UpdateCheckWorker()
        self._update_worker.update_available.connect(
            self._on_update_available
        )
        self._update_worker.up_to_date.connect(
            self._on_update_up_to_date
        )
        self._update_worker.check_error.connect(
            self._on_update_check_error
        )
        self._update_worker.start()

    def _on_update_up_to_date(self, ver):
        self.latest_release_version = ver
        self.update_check_status = f"Up to date (v{ver})"
        if not self._update_check_silent:
            QMessageBox.information(
                self, "Up to Date",
                f"You are running the latest version (v{ver})."
            )

    def _on_update_check_error(self, err):
        self.update_check_status = f"Check failed: {err}"
        if not self._update_check_silent:
            QMessageBox.warning(
                self, "Update Check Failed",
                f"Could not reach GitHub:\n{err}"
            )

    def _on_update_available(self, latest_tag, html_url):
        import webbrowser
        self.latest_release_version = latest_tag
        self.update_check_status = f"Update available: v{latest_tag}"
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setText(
            f"A new version is available: v{latest_tag}\n"
            f"You are running: v{APP_VERSION}"
        )
        msg.setInformativeText("Open the GitHub release page to download the update?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)
        if msg.exec_() == QMessageBox.Yes:
            webbrowser.open(html_url)

    def show_about(self):
        about_text = (
            f"Schoolbooth  v{APP_VERSION}\n"
            "Offered to school PTAs for limited use by IKAP Systems\n"
            "\n"
            "A passion project by Anthony Webb\n"
            "\n"
            "Our mission is to bring an inexpensive solution that allows\n"
            "parents to connect with their kids\u2019 special moments at school\n"
            "without compromising security.\n"
            "\n"
            "Campus has become more closed off from parents, but with the\n"
            "help of your local PTA and the support of school and district\n"
            "administrators, we can bring those special memories home.\n"
            "\n"
            "\u00a9 2026 IKAP Systems \u2014 All Rights Reserved\n"
            "\n"
            f"Software Update v: {APP_VERSION}\n"
            f"Update Check Status: {self.update_check_status}"
        )
        QMessageBox.about(self, "About Schoolbooth", about_text)

    def open_wp_settings(self):
        """WordPress-specific settings dialog"""
        dialog = WPLinkSettingsDialog(self)
        self.apply_modern_settings_dialog_style(dialog)
        self.center_dialog(dialog)
        dialog.exec_()

    def open_photo_print_settings(self):
        dialog = PhotoPrintSettingsDialog(self)
        self.apply_modern_settings_dialog_style(dialog)
        self.center_dialog(dialog)
        dialog.exec_()

    def open_qr_print_settings(self):
        dialog = QRPrintSettingsDialog(self)
        self.apply_modern_settings_dialog_style(dialog)
        self.center_dialog(dialog)
        dialog.exec_()

    def open_local_storage_settings(self):
        dialog = LocalStorageSettingsDialog(self)
        self.apply_modern_settings_dialog_style(dialog)
        self.center_dialog(dialog)
        dialog.exec_()

    def _is_purgeable_capture_folder(self, folder_path):
        allowed_extensions = {'.jpg', '.jpeg', '.png'}

        for root, dirnames, filenames in os.walk(folder_path):
            if dirnames:
                return False

            for filename in filenames:
                lower_name = filename.lower()
                base_name, extension = os.path.splitext(lower_name)
                if not base_name.startswith('capture_') or extension not in allowed_extensions:
                    return False

        return True

    def purge_local_storage(self, manual=False):
        result = {
            'enabled': bool(self.settings.get('output_auto_purge_enabled', False)),
            'deleted_count': 0,
            'skipped_count': 0,
        }

        if not result['enabled']:
            return result

        output_dir = os.path.abspath(os.path.expanduser(self.settings.get('output_dir', os.path.expanduser('~/Pictures'))))
        retention_days = max(1, int(self.settings.get('output_auto_purge_days', 30)))

        if not os.path.isdir(output_dir):
            return result

        cutoff_date = (datetime.now() - timedelta(days=retention_days)).date()

        for entry_name in os.listdir(output_dir):
            entry_path = os.path.join(output_dir, entry_name)
            if not os.path.isdir(entry_path):
                continue

            try:
                entry_date = datetime.strptime(entry_name, '%Y-%m-%d').date()
            except ValueError:
                continue

            if entry_date >= cutoff_date:
                continue

            if not self._is_purgeable_capture_folder(entry_path):
                result['skipped_count'] += 1
                print(f"Auto purge skipped folder with unexpected contents: {entry_path}")
                continue

            try:
                shutil.rmtree(entry_path)
                result['deleted_count'] += 1
                print(f"Auto purge deleted old capture folder: {entry_path}")
            except Exception as exc:
                result['skipped_count'] += 1
                print(f"Auto purge failed for {entry_path}: {exc}")

        if manual:
            self.save_settings()

        return result

    def set_output_size(self):
        """Dialog to set output image size"""
        sizes = ["4x6", "5x7", "8x10", "11x14"]
        size, ok = QInputDialog.getItem(
            self, "Output Size", "Select image output size:",
            sizes, sizes.index(self.settings['crop_size']), False
        )
        if ok and size:
            self.settings['crop_size'] = size

    def validate_wp_settings(self):
        """Check if WordPress settings are complete"""
        required = [
            ('wp_url', "WordPress URL"),
            ('wp_api_endpoint', "API Endpoint"),
            ('wp_shared_secret', "Security Secret"),
        ]

        missing = [name for key, name in required if not self.settings.get(key)]
        if missing:
            QMessageBox.warning(
                self,
                "Missing Settings",
                f"Required WordPress settings missing:\n- " + "\n- ".join(missing)
            )
            return False

        if not self.settings.get('wp_shared_secret'):
            QMessageBox.warning(
                self,
                "Shared Secret Missing",
                "Use 'Enroll via WordPress Login' or 'Pull from WordPress' to auto-configure the shared secret, or enable Advanced mode to set it manually."
            )
            return False

        if len(self.settings['wp_shared_secret']) < 32:
            QMessageBox.warning(
                self,
                "Weak Secret",
                "Security secret must be at least 32 characters"
            )
            return False

        return True

    def get_available_cameras(self):
        cameras = []
        max_cameras_to_check = 3  # Reduced from 10 to avoid excessive errors
        for i in range(max_cameras_to_check):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)  # Use DSHOW on Windows
            if cap.isOpened():
                cameras.append(i)
                cap.release()
            else:
                cap.release()
        return cameras

    def initialize_camera(self):
        try:
            # Try preferred camera first
            if hasattr(self, 'camera_index'):
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                if self.cap.isOpened():
                    return self.cap

            # Fall back to any available camera
            for i in self.available_cameras:
                self.cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if self.cap.isOpened():
                    self.settings['camera_index'] = i
                    return self.cap

            # If no cameras work - continue without camera, show placeholder in UI
            print("No cameras available - running without camera")
            return None

        except Exception as e:
            print(f"Camera initialization failed: {e} - running without camera")
            return None

    def init_ui(self):
        print("Initializing UI components, self.qr_size_inches exists:",
              hasattr(self, 'qr_size_inches'))  # added closing parenthesis here

        main_widget = QWidget()
        main_layout = QHBoxLayout()

        # Left panel - camera view
        left_panel = QVBoxLayout()

        # Create qr_size_inches widget here
        self.qr_size_inches = QDoubleSpinBox()
        self.qr_size_inches.setRange(1.0, 10.0)
        self.qr_size_inches.setSingleStep(0.5)
        self.qr_size_inches.setValue(2.0)

        # Camera view
        self.camera_label = QLabel()
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumSize(640, 480)
        self.camera_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.camera_label.setToolTip("Live camera preview - ensure subject is framed within the crop guides")
        self.camera_label.setMouseTracking(True)
        self.camera_label.mousePressEvent = self.watermark_mouse_press
        self.camera_label.mouseMoveEvent = self.watermark_mouse_move
        self.camera_label.mouseReleaseEvent = self.watermark_mouse_release

        left_panel.addWidget(self.camera_label, stretch=1)

        # Capture button - prominent primary action
        self.capture_btn = QPushButton("CAPTURE")
        self.capture_btn.clicked.connect(self.capture_image)
        self.capture_btn.setMinimumHeight(70)
        self.capture_btn.setStyleSheet("""
            QPushButton {
                font-size: 20px;
                font-weight: bold;
                padding: 15px;
                background-color: #2a82da;
                color: white;
                border: none;
                border-radius: 6px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background-color: #1e5fa0;
            }
            QPushButton:pressed {
                background-color: #164478;
            }
        """)
        self.capture_btn.setToolTip("Capture the current camera image and process it")
        left_panel.addWidget(self.capture_btn, stretch=0)

        main_layout.addLayout(left_panel, stretch=2)

        # Right panel - reorganized for better UX
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(16, 12, 12, 12)
        right_panel.setSpacing(12)

        panel_group_style = """
            QGroupBox {
                font-size: 15px;
                font-weight: 700;
                border: 1px solid #d7e0eb;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 12px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
                color: #3b4d63;
            }
        """

        # ========== 1. OVERLAY SECTION ==========
        overlay_section = QGroupBox("Overlays")
        overlay_section.setStyleSheet(panel_group_style)
        overlay_layout = QGridLayout()
        overlay_layout.setSpacing(8)
        self.overlay_grid_layout = overlay_layout
        overlay_section.setLayout(overlay_layout)
        self.populate_overlay_buttons()
        right_panel.addWidget(overlay_section)

        # ========== 2. PHOTO PREVIEW SECTION ==========
        photo_section = QGroupBox("Last Capture")
        photo_section.setStyleSheet(panel_group_style)
        photo_layout = QVBoxLayout()
        photo_layout.setSpacing(8)

        # Photo display
        self.last_capture_label = QLabel()
        self.last_capture_label.setAlignment(Qt.AlignCenter)
        self.last_capture_label.setMinimumSize(320, 260)
        self.last_capture_label.setStyleSheet("""
            QLabel {
                background-color: #f8f8f8;
                border: 2px dashed #ccc;
                border-radius: 8px;
            }
        """)
        
        self.placeholder = QLabel("No capture yet")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("""
            color: #999;
            font-style: italic;
            font-size: 14px;
        """)
        photo_layout.addWidget(self.placeholder)
        photo_layout.addWidget(self.last_capture_label)
        
        photo_section.setLayout(photo_layout)
        right_panel.addWidget(photo_section, stretch=1)

        # ========== 3. QUICK ACTIONS SECTION ==========
        actions_section = QGroupBox("Quick Actions")
        actions_section.setStyleSheet(panel_group_style)
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(8)

        # Open Photo Link button (secondary)
        self.open_link_btn = QPushButton("View Online")
        self.open_link_btn.setMinimumHeight(46)
        self.open_link_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 15px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.open_link_btn.setIcon(self._get_action_icon("link", QStyle.SP_DialogOpenButton, size=20))
        self.open_link_btn.setIconSize(QSize(20, 20))
        self.open_link_btn.hide()
        self.open_link_btn.clicked.connect(self.open_last_photo_link)
        self.open_link_btn.setToolTip("Open photo in web browser")
        actions_layout.addWidget(self.open_link_btn)

        # Reprint buttons
        reprint_layout = QHBoxLayout()
        reprint_layout.setSpacing(8)

        self.print_photo_btn = QPushButton("Print Photo")
        self.print_photo_btn.setMinimumHeight(46)
        self.print_photo_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 15px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #e68900;
            }
            QPushButton:pressed {
                background-color: #cc7700;
            }
        """)
        self.print_photo_btn.setIcon(self._get_action_icon("print", QStyle.SP_DialogSaveButton, size=20))
        self.print_photo_btn.setIconSize(QSize(20, 20))
        self.print_photo_btn.hide()
        self.print_photo_btn.clicked.connect(self.reprint_photo)
        self.print_photo_btn.setToolTip("Reprint last photo")
        reprint_layout.addWidget(self.print_photo_btn)

        self.print_qr_btn = QPushButton("Print QR Code")
        self.print_qr_btn.setMinimumHeight(46)
        self.print_qr_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 15px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QPushButton:pressed {
                background-color: #0a66c2;
            }
        """)
        self.print_qr_btn.setIcon(self._get_action_icon("qr_code", QStyle.SP_DialogSaveButton, size=20))
        self.print_qr_btn.setIconSize(QSize(20, 20))
        self.print_qr_btn.hide()
        self.print_qr_btn.clicked.connect(self.reprint_qr_code)
        self.print_qr_btn.setToolTip("Reprint last QR code")
        reprint_layout.addWidget(self.print_qr_btn)

        actions_layout.addLayout(reprint_layout)
        actions_section.setLayout(actions_layout)
        right_panel.addWidget(actions_section)

        # ========== 4. STATUS SECTION ==========
        status_section = QGroupBox("Status")
        status_section.setStyleSheet(panel_group_style)
        status_layout = QVBoxLayout()
        status_layout.setSpacing(10)

        # Single status button - shows overall health
        self._status_btn = QPushButton("Ready")
        self._status_btn.setFixedHeight(46)
        self._status_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-weight: bold;
                font-size: 15px;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:pressed {
                background-color: #229954;
            }
        """)
        self._status_btn.clicked.connect(self._show_status_details)
        status_layout.addWidget(self._status_btn)

        # Store detailed status for popup
        self._last_health_results = {}

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setFixedHeight(34)
        refresh_btn.setStyleSheet("font-size: 14px; padding: 4px 10px;")
        refresh_btn.setIcon(self._get_action_icon("refresh", QStyle.SP_BrowserReload, size=18))
        refresh_btn.setIconSize(QSize(18, 18))
        refresh_btn.clicked.connect(self._run_health_check)
        status_layout.addWidget(refresh_btn, alignment=Qt.AlignRight)

        status_section.setLayout(status_layout)
        right_panel.addWidget(status_section)

        # Add stretch to push everything up
        right_panel.addStretch()

        main_layout.addLayout(right_panel, stretch=1)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Initialize toolbar
        self.toolbar = self.addToolBar("Main Toolbar")

        # Store the last photo URL
        self.last_photo_url = ""
        self.last_app_photo_url = ""

        # Visual Feedback Overlay
        self.feedback_overlay = QLabel(self)
        self.feedback_overlay.setAlignment(Qt.AlignCenter)
        self.feedback_overlay.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0);
                color: white;
                font-size: 72px;
                font-weight: bold;
                border-radius: 20px;
            }
        """)
        self.feedback_overlay.hide()
        self.feedback_overlay.setFixedSize(300, 200)
        self.feedback_overlay.move(
            self.width() // 2 - 150,
            self.height() // 2 - 100
        )
        self.feedback_overlay.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

    def show_feedback(self, text, color):
        """Show fullscreen feedback message"""
        self.feedback_overlay.setText(text)
        self.feedback_overlay.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                font-size: 72px;
                font-weight: bold;
                border-radius: 20px;
                padding: 20px;
            }}
        """)

        # Center on screen
        self.feedback_overlay.move(
            self.width() // 2 - self.feedback_overlay.width() // 2,
            self.height() // 2 - self.feedback_overlay.height() // 2
        )

        self.feedback_overlay.show()
        self.feedback_overlay.raise_()

        # Animate fade out
        self.feedback_animation = QPropertyAnimation(self.feedback_overlay, b"windowOpacity")
        self.feedback_animation.setDuration(1000)
        self.feedback_animation.setStartValue(1.0)
        self.feedback_animation.setEndValue(0.0)
        self.feedback_animation.finished.connect(self.feedback_overlay.hide)
        self.feedback_animation.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Force an immediate frame update to adjust to new size
        self.update_frame()
        # Keep feedback centered
        if hasattr(self, 'feedback_overlay'):
            self.feedback_overlay.move(
                self.width() // 2 - self.feedback_overlay.width() // 2,
                self.height() // 2 - self.feedback_overlay.height() // 2
            )

    def open_last_photo_link(self):
        target_url = self.last_app_photo_url or self.last_photo_url
        if target_url:
            try:
                import webbrowser
                webbrowser.open(target_url)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not open link: {str(e)}")
        else:
            QMessageBox.warning(self, "No Link", "No web link available for this photo")

    def rotate_image(self, angle):
        self.settings['rotation'] = (self.settings['rotation'] + angle) % 360
        print(f"Rotation set to: {self.settings['rotation']}Â°")

    def toggle_color_correction(self, state):
        self.settings['auto_color'] = (state == Qt.Checked)
        print(f"Auto Color Correction: {'ON' if self.settings['auto_color'] else 'OFF'}")

    def toggle_white_balance(self, state):
        self.settings['auto_wb'] = (state == Qt.Checked)
        print(f"Auto White Balance: {'ON' if self.settings['auto_wb'] else 'OFF'}")

    def set_crop_size(self, size):
        self.settings['crop_size'] = size
        print(f"Crop size set to: {size}")

    def set_watermark_x(self, x):
        self.settings['watermark_x'] = x
        print(f"Watermark X: {x}%")

    def set_watermark_y(self, y):
        self.settings['watermark_y'] = y
        print(f"Watermark Y: {y}%")

    def set_watermark_size(self, size):
        self.settings['watermark_size'] = max(1, size)
        print(f"Watermark size: {self.settings['watermark_size']}%")
        self.update_watermark_size()

    def set_watermark_opacity(self, opacity):
        self.settings['watermark_opacity'] = opacity
        print(f"Watermark opacity: {opacity}%")

    def toggle_bg_removal(self, state):
        self.settings['watermark_remove_bg'] = (state == Qt.Checked)
        print(f"Background removal: {'ON' if self.settings['watermark_remove_bg'] else 'OFF'}")
        self.process_watermark()

    def set_output_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            self.settings["output_dir"]
        )
        if directory:
            self.settings["output_dir"] = directory
            print(f"Output directory set to: {directory}")

    def toggle_crop_overlay(self, state):
        self.settings["show_crop_overlay"] = state
        print(f"Crop overlay: {'ON' if self.settings['show_crop_overlay'] else 'OFF'}")
        self.update_frame()

    def upload_watermark(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Watermark Image", "",
            "PNG Files (*.png);;All Files (*)"
        )
        if file_name:
            self.load_watermark(file_name)

    def load_watermark(self, file_path):
        try:
            # Load with unchanged channels (including alpha if present)
            self.watermark_original = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
            if self.watermark_original is None:
                raise ValueError("Failed to load image")

            # Ensure watermark has 4 channels (BGRA)
            if self.watermark_original.shape[2] == 3:
                b, g, r = cv2.split(self.watermark_original)
                alpha = np.ones(b.shape, dtype=np.uint8) * 255
                self.watermark_original = cv2.merge((b, g, r, alpha))

            print(f"Watermark loaded. Dimensions: {self.watermark_original.shape}")
            self.settings["watermark_path"] = file_path
            self.settings["watermark_enabled"] = True
            self.process_watermark()
            self.update_overlay_button_states(file_path)

        except Exception as e:
            print(f"Load failed: {str(e)}")
            self.watermark_original = None

    def get_overlay_directory(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for folder_name in ("overlays", "watermarks"):
            candidate = os.path.join(base_dir, folder_name)
            if os.path.isdir(candidate):
                return candidate
        return os.path.join(base_dir, "watermarks")

    def get_overlay_frame_paths(self):
        overlay_dir = self.get_overlay_directory()
        frame_paths = []
        for frame_number in range(1, 5):
            frame_name = f"FRAME_{frame_number}"
            matched_path = ""
            for extension in (".png", ".jpg", ".jpeg", ".webp"):
                candidate = os.path.join(overlay_dir, f"{frame_name}{extension}")
                if os.path.exists(candidate):
                    matched_path = candidate
                    break
            frame_paths.append((frame_name, matched_path))
        return frame_paths

    def populate_overlay_buttons(self):
        if not hasattr(self, 'overlay_grid_layout'):
            return

        while self.overlay_grid_layout.count():
            item = self.overlay_grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.overlay_buttons = {}
        frame_entries = self.get_overlay_frame_paths()

        # 3 columns x 2 rows; portrait buttons sized for 4x6 frame preview thumbnails
        _NUM_COLS = 3
        _BTN_MIN_W = 90
        _BTN_MIN_H = 130        # portrait aspect for 4x6 frames
        _ICON_W = 80
        _ICON_H = 115

        _frame_style = """
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #c8c8c8;
                border-radius: 5px;
                padding: 3px;
            }
            QPushButton:hover {
                border: 2px solid #2a82da;
                background-color: #e8f2ff;
            }
            QPushButton:checked {
                border: 3px solid #2a82da;
                background-color: #cce0ff;
            }
            QPushButton:disabled {
                background-color: #e8e8e8;
                border: 1px dashed #b0b0b0;
            }
        """

        # FRAME 1-4 buttons  (row 0: cols 0-2 = FRAME 1/2/3; row 1 col 0 = FRAME 4)
        for index, (frame_name, frame_path) in enumerate(frame_entries):
            button = QPushButton("")          # icon-only; label via tooltip
            button.setCheckable(True)
            button.setMinimumSize(_BTN_MIN_W, _BTN_MIN_H)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            button.setStyleSheet(_frame_style)

            if frame_path:
                button.setIcon(QIcon(frame_path))
                button.setIconSize(QSize(_ICON_W, _ICON_H))
                button.setToolTip(frame_name.replace("_", " "))
                button.clicked.connect(lambda checked, fn=frame_name, fp=frame_path: self.select_overlay(fn, fp))
            else:
                button.setEnabled(False)
                button.setToolTip(f"{frame_name.replace('_', ' ')} (not found)")

            row = index // _NUM_COLS
            col = index % _NUM_COLS
            self.overlay_grid_layout.addWidget(button, row, col)
            self.overlay_buttons[frame_name] = (button, frame_path)

        # CUSTOM button  (row 1, col 1)
        custom_btn = QPushButton("")
        custom_btn.setCheckable(True)
        custom_btn.setMinimumSize(_BTN_MIN_W, _BTN_MIN_H)
        custom_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        custom_btn.setStyleSheet(_frame_style)
        custom_info = self._overlay_frame_settings.get('CUSTOM', {})
        custom_path = custom_info.get('path', '')
        if custom_path and os.path.exists(custom_path):
            custom_btn.setIcon(QIcon(custom_path))
            custom_btn.setIconSize(QSize(_ICON_W, _ICON_H))
            custom_btn.setToolTip("Custom overlay")
        else:
            custom_btn.setText("+")
            custom_btn.setToolTip("Load a custom overlay image")
        custom_btn.clicked.connect(self.select_custom_overlay)
        self.overlay_grid_layout.addWidget(custom_btn, 1, 1)
        self.overlay_buttons['CUSTOM'] = (custom_btn, custom_path)

        # CLEAR button  (row 1, col 2) — not checkable, shows 'x' text
        clear_btn = QPushButton("✕")
        clear_btn.setCheckable(False)
        clear_btn.setMinimumSize(_BTN_MIN_W, _BTN_MIN_H)
        clear_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #fff0f0;
                border: 1px solid #d09090;
                border-radius: 5px;
                font-size: 22px;
                font-weight: bold;
                color: #c00000;
                padding: 3px;
            }
            QPushButton:hover {
                border: 2px solid #c00000;
                background-color: #ffe0e0;
            }
        """)
        clear_btn.setToolTip("Remove active overlay")
        clear_btn.clicked.connect(self.clear_overlay)
        self.overlay_grid_layout.addWidget(clear_btn, 1, 2)

        self.update_overlay_button_states()

    def select_overlay(self, frame_name, file_path):
        """Select a named frame overlay, saving current frame settings first."""
        self._save_active_frame_settings()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Overlay Missing", f"{frame_name} overlay file is not available.")
            return
        self.active_overlay_key = frame_name
        self._apply_frame_settings(frame_name)
        self.load_watermark(file_path)

    def select_custom_overlay(self):
        """Open a file picker to load a custom overlay image."""
        self._save_active_frame_settings()
        custom_info = self._overlay_frame_settings.get('CUSTOM', {})
        initial_dir = os.path.dirname(custom_info.get('path', '')) or ''
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Custom Overlay Image", initial_dir,
            "Image Files (*.png *.jpg *.jpeg *.webp);;All Files (*)"
        )
        if not file_name:
            # User cancelled — restore button state
            self.update_overlay_button_states()
            return
        # Persist the chosen path into CUSTOM's settings slot
        if 'CUSTOM' not in self._overlay_frame_settings:
            self._overlay_frame_settings['CUSTOM'] = {}
        self._overlay_frame_settings['CUSTOM']['path'] = file_name
        # Update the CUSTOM button icon
        if 'CUSTOM' in self.overlay_buttons:
            btn, _ = self.overlay_buttons['CUSTOM']
            btn.setIcon(QIcon(file_name))
            btn.setIconSize(QSize(110, 62))
            self.overlay_buttons['CUSTOM'] = (btn, file_name)
        self.active_overlay_key = 'CUSTOM'
        self._apply_frame_settings('CUSTOM')
        self.load_watermark(file_name)
        self._persist_overlay_frame_settings()

    def clear_overlay(self):
        """Remove the active overlay silently (called by the CLEAR button)."""
        self._save_active_frame_settings()
        self.active_overlay_key = None
        self.settings['watermark_enabled'] = False
        self.watermark_original = None
        self.watermark_processed = None
        self.watermark_img = None
        self.settings['watermark_path'] = ''
        self.update_overlay_button_states()

    def update_overlay_button_states(self, selected_path=None):
        """Highlight whichever overlay button matches the active overlay key."""
        active_key = self.active_overlay_key
        for btn_key, (button, _frame_path) in self.overlay_buttons.items():
            button.blockSignals(True)
            button.setChecked(btn_key == active_key)
            button.blockSignals(False)

    # ------------------------------------------------------------------
    # Per-frame overlay settings helpers
    # ------------------------------------------------------------------

    def _overlay_settings_path(self):
        """Return path to the sidecar JSON that stores per-frame watermark settings."""
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, 'overlay_frame_settings.json')

    def _load_overlay_frame_settings(self):
        """Load per-frame settings from the sidecar file, or return empty dict."""
        path = self._overlay_settings_path()
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Could not load overlay frame settings: {e}")
        return {}

    def _persist_overlay_frame_settings(self):
        """Write per-frame settings to the sidecar JSON file."""
        path = self._overlay_settings_path()
        try:
            with open(path, 'w') as f:
                json.dump(self._overlay_frame_settings, f, indent=2)
        except Exception as e:
            print(f"Could not save overlay frame settings: {e}")

    def _get_frame_settings(self, key):
        """Return per-frame watermark settings for *key*, merged over defaults."""
        defaults = {
            'watermark_x': 50.0, 'watermark_y': 50.0,
            'watermark_size': 30.0, 'watermark_opacity': 70.0,
            'watermark_rotation': 0.0, 'watermark_scale': 1.0,
            'watermark_remove_bg': True,
        }
        stored = self._overlay_frame_settings.get(key, {})
        for k in list(defaults):
            if k in stored:
                defaults[k] = stored[k]
        return defaults

    def _capture_current_watermark_settings(self):
        """Return current active watermark settings as a plain dict."""
        return {
            'watermark_x': float(self.settings.get('watermark_x', 50.0)),
            'watermark_y': float(self.settings.get('watermark_y', 50.0)),
            'watermark_size': float(self.settings.get('watermark_size', 30.0)),
            'watermark_opacity': float(self.settings.get('watermark_opacity', 70.0)),
            'watermark_rotation': float(self.settings.get('watermark_rotation', 0.0)),
            'watermark_scale': float(self.settings.get('watermark_scale', 1.0)),
            'watermark_remove_bg': bool(self.settings.get('watermark_remove_bg', True)),
        }

    def _save_active_frame_settings(self):
        """Persist the current watermark transform settings to the active frame slot."""
        if not self.active_overlay_key or self.watermark_original is None:
            return
        current = self._capture_current_watermark_settings()
        if self.active_overlay_key not in self._overlay_frame_settings:
            self._overlay_frame_settings[self.active_overlay_key] = {}
        self._overlay_frame_settings[self.active_overlay_key].update(current)
        self._persist_overlay_frame_settings()

    def _apply_frame_settings(self, key):
        """Load per-frame watermark settings into self.settings."""
        frame_settings = self._get_frame_settings(key)
        for k, v in frame_settings.items():
            self.settings[k] = v

    def _path_to_overlay_key(self, path):
        """Return the overlay key ('FRAME_1' etc.) that matches *path*, or None."""
        if not path:
            return None
        abs_path = os.path.abspath(path)
        for frame_name, frame_path in self.get_overlay_frame_paths():
            if frame_path and os.path.abspath(frame_path) == abs_path:
                return frame_name
        custom_path = self._overlay_frame_settings.get('CUSTOM', {}).get('path', '')
        if custom_path and os.path.abspath(custom_path) == abs_path:
            return 'CUSTOM'
        return None

    def process_watermark(self):
        if self.watermark_original is None:
            return

        try:
            # Convert to BGRA if needed
            if self.watermark_original.shape[2] == 3:
                b, g, r = cv2.split(self.watermark_original)
                alpha = np.ones(b.shape, dtype=np.uint8) * 255
                self.watermark_processed = cv2.merge((b, g, r, alpha))
            else:
                self.watermark_processed = self.watermark_original.copy()

            # Apply background removal mask if enabled
            if self.settings['watermark_remove_bg']:
                alpha = self.watermark_processed[:, :, 3]
                _, mask = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
                self.watermark_processed[:, :, 3] = mask

            # Keep an untransformed working copy; size/scale/rotation are applied at render time.
            self.watermark_img = self.watermark_processed.copy()

        except Exception as e:
            print(f"Processing watermark failed: {str(e)}")
            self.watermark_processed = None
            self.watermark_img = None

    def update_watermark_size(self):
        if self.watermark_processed is None:
            return
        try:
            # Legacy compatibility: keep this method, but do not pre-scale.
            self.watermark_img = self.watermark_processed.copy()
        except Exception as e:
            print(f"Resize error: {str(e)}")
            self.watermark_img = None

    def _get_active_watermark_state(self):
        source = self._watermark_edit_state if self._watermark_edit_state is not None else self.settings
        return {
            'x': float(source.get('watermark_x', 50.0)),
            'y': float(source.get('watermark_y', 50.0)),
            'size': float(source.get('watermark_size', 30.0)),
            'scale': float(source.get('watermark_scale', 1.0)),
            'rotation': float(source.get('watermark_rotation', 0.0)),
            'opacity': float(source.get('watermark_opacity', 70.0)),
        }

    def _rotate_bound_bgra(self, image, angle):
        if image is None:
            return None
        if abs(angle) < 1e-6:
            return image

        h, w = image.shape[:2]
        center = (w / 2.0, h / 2.0)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        cos = abs(rot_mat[0, 0])
        sin = abs(rot_mat[0, 1])

        new_w = max(1, int((h * sin) + (w * cos)))
        new_h = max(1, int((h * cos) + (w * sin)))

        rot_mat[0, 2] += (new_w / 2.0) - center[0]
        rot_mat[1, 2] += (new_h / 2.0) - center[1]

        return cv2.warpAffine(
            image,
            rot_mat,
            (new_w, new_h),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0)
        )

    def get_transformed_watermark(self, state=None):
        if self.watermark_processed is None:
            return None

        if state is None:
            wm_state = self._get_active_watermark_state()
        else:
            wm_state = {
                'x': float(state.get('x', state.get('watermark_x', self.settings.get('watermark_x', 50.0)))),
                'y': float(state.get('y', state.get('watermark_y', self.settings.get('watermark_y', 50.0)))),
                'size': float(state.get('size', state.get('watermark_size', self.settings.get('watermark_size', 30.0)))),
                'scale': float(state.get('scale', state.get('watermark_scale', self.settings.get('watermark_scale', 1.0)))),
                'rotation': float(state.get('rotation', state.get('watermark_rotation', self.settings.get('watermark_rotation', 0.0)))),
                'opacity': float(state.get('opacity', state.get('watermark_opacity', self.settings.get('watermark_opacity', 70.0)))),
            }
        base_scale = max(0.01, wm_state['size'] / 100.0)
        fine_scale = max(0.1, min(3.0, wm_state['scale']))
        total_scale = max(0.01, base_scale * fine_scale)

        # Apply total scale first.
        scaled = cv2.resize(
            self.watermark_processed,
            None,
            fx=total_scale,
            fy=total_scale,
            interpolation=cv2.INTER_AREA if total_scale < 1.0 else cv2.INTER_LANCZOS4
        )

        # Rotate in expanded bounds so watermark is never clipped by the transform canvas.
        return self._rotate_bound_bgra(scaled, wm_state['rotation'])

    def _compute_watermark_top_left(self, frame_w, frame_h, wm_w, wm_h, state):
        x = int((state['x'] / 100.0) * max(1, frame_w - wm_w))
        y = int((state['y'] / 100.0) * max(1, frame_h - wm_h))
        x = max(0, min(x, max(0, frame_w - wm_w)))
        y = max(0, min(y, max(0, frame_h - wm_h)))
        return x, y

    def apply_watermark(self, frame, show_editor_overlay=False):
        if not self.settings['watermark_enabled'] or self.watermark_processed is None:
            return frame

        try:
            wm_state = self._get_active_watermark_state()

            # Get transformed watermark (with rotation and scaling applied)
            watermark = self.get_transformed_watermark(wm_state)
            if watermark is None:
                return frame

            # Convert frame to BGRA to support alpha blending
            frame_rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            h_frame, w_frame = frame.shape[:2]
            h_wm, w_wm = watermark.shape[:2]

            # Full-frame overlays can be larger than the preview/capture frame.
            # Scale them down so the blend ROI always matches the frame bounds.
            if h_wm > h_frame or w_wm > w_frame:
                fit_scale = min(w_frame / max(1, w_wm), h_frame / max(1, h_wm))
                fit_scale = max(0.01, min(1.0, fit_scale))
                watermark = cv2.resize(
                    watermark,
                    None,
                    fx=fit_scale,
                    fy=fit_scale,
                    interpolation=cv2.INTER_AREA
                )
                h_wm, w_wm = watermark.shape[:2]

            x, y = self._compute_watermark_top_left(w_frame, h_frame, w_wm, h_wm, wm_state)

            # Extract the region of interest from the frame
            roi = frame_rgba[y:y + h_wm, x:x + w_wm]

            # Split watermark into color and alpha channels
            wm_bgra = watermark
            if wm_bgra.shape[2] == 3:  # If no alpha channel, add one
                b, g, r = cv2.split(wm_bgra)
                alpha = np.ones(b.shape, dtype=np.uint8) * 255
                wm_bgra = cv2.merge((b, g, r, alpha))

            # Normalize alpha channel and apply opacity
            wm_alpha = wm_bgra[:, :, 3].astype(float) / 255.0
            wm_alpha = wm_alpha * (max(0.0, min(100.0, wm_state['opacity'])) / 100.0)

            # Blend the watermark with the frame
            for c in range(0, 3):
                roi[:, :, c] = roi[:, :, c] * (1 - wm_alpha) + wm_bgra[:, :, c] * wm_alpha

            output = cv2.cvtColor(frame_rgba, cv2.COLOR_BGRA2BGR)
            if show_editor_overlay:
                self.draw_watermark_controls(output, x, y, w_wm, h_wm)
            return output
        except Exception as e:
            print(f"Error applying watermark: {str(e)}")
            return frame

    def apply_watermark_with_state(self, frame, state, show_editor_overlay=False):
        previous_state = self._watermark_edit_state
        previous_enabled = self.settings.get('watermark_enabled', False)
        previous_remove_bg = self.settings.get('watermark_remove_bg', True)

        self._watermark_edit_state = {
            'watermark_x': float(state.get('watermark_x', self.settings.get('watermark_x', 50.0))),
            'watermark_y': float(state.get('watermark_y', self.settings.get('watermark_y', 50.0))),
            'watermark_size': float(state.get('watermark_size', self.settings.get('watermark_size', 30.0))),
            'watermark_scale': float(state.get('watermark_scale', self.settings.get('watermark_scale', 1.0))),
            'watermark_rotation': float(state.get('watermark_rotation', self.settings.get('watermark_rotation', 0.0))),
            'watermark_opacity': float(state.get('watermark_opacity', self.settings.get('watermark_opacity', 70.0))),
        }

        self.settings['watermark_enabled'] = bool(state.get('watermark_enabled', previous_enabled))

        requested_remove_bg = bool(state.get('watermark_remove_bg', previous_remove_bg))
        if requested_remove_bg != previous_remove_bg:
            self.settings['watermark_remove_bg'] = requested_remove_bg
            if self.watermark_original is not None:
                self.process_watermark()

        try:
            return self.apply_watermark(frame, show_editor_overlay=show_editor_overlay)
        finally:
            self._watermark_edit_state = previous_state
            self.settings['watermark_enabled'] = previous_enabled
            if self.settings.get('watermark_remove_bg', True) != previous_remove_bg:
                self.settings['watermark_remove_bg'] = previous_remove_bg
                if self.watermark_original is not None:
                    self.process_watermark()

    def draw_watermark_controls(self, frame, x, y, w_wm, h_wm):
        """Draw interactive handles over the watermark in the preview frame."""
        if self.settings.get('watermark_snap_grid', True):
            step_pct = max(1, int(self.settings.get('watermark_snap_grid_step', 5)))
            step_x = max(1, int(frame.shape[1] * (step_pct / 100.0)))
            step_y = max(1, int(frame.shape[0] * (step_pct / 100.0)))
            grid_color = (70, 70, 70)
            for gx in range(0, frame.shape[1], step_x):
                cv2.line(frame, (gx, 0), (gx, frame.shape[0]), grid_color, 1)
            for gy in range(0, frame.shape[0], step_y):
                cv2.line(frame, (0, gy), (frame.shape[1], gy), grid_color, 1)

        if self.settings.get('watermark_snap_center', True):
            cx = frame.shape[1] // 2
            cy = frame.shape[0] // 2
            center_color = (180, 180, 180)
            cv2.line(frame, (cx, 0), (cx, frame.shape[0]), center_color, 1)
            cv2.line(frame, (0, cy), (frame.shape[1], cy), center_color, 1)

        color = (0, 220, 255)
        cv2.rectangle(frame, (x, y), (x + w_wm, y + h_wm), color, 2)

        resize_handle = (x + w_wm, y + h_wm)
        rotate_handle = (x + (w_wm // 2), y)

        cv2.circle(frame, resize_handle, 8, (0, 180, 0), -1)
        cv2.circle(frame, rotate_handle, 8, (0, 80, 255), -1)
        cv2.putText(
            frame,
            "Drag box=Move | BR handle=Scale | Top handle=Rotate | Snap Grid ON",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )

    def process_frame(self, frame, show_editor_overlay=False):
        try:
            # Apply rotation first
            if self.settings['rotation'] == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.settings['rotation'] == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.settings['rotation'] == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # Convert to float32 for processing
            frame = frame.astype('float32') / 255.0

            # Apply auto white balance if enabled
            if self.settings['auto_wb']:
                frame = self.auto_white_balance(frame)
            else:
                frame = self.manual_white_balance(frame, self.settings['wb_temp'])

            # Auto color correction
            if self.settings['auto_color']:
                frame = self.auto_color_correction(frame)

            # Manual adjustments
            frame = self.apply_manual_adjustments(frame)

            # Convert back to 8-bit
            frame = (frame * 255).clip(0, 255).astype('uint8')

            # Apply watermark if enabled
            if self.settings['watermark_enabled']:
                frame = self.apply_watermark(frame, show_editor_overlay=show_editor_overlay)

            # Draw crop overlay if enabled
            if self.settings["show_crop_overlay"]:
                frame = self.draw_crop_overlay(frame)

            return frame
        except Exception as e:
            print(f"Error in process_frame: {e}")
            return frame

    def apply_manual_adjustments(self, frame):
        # Guard against NaN/Inf propagating from upstream camera/filter math.
        frame = np.nan_to_num(frame, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)
        frame = np.clip(frame, 0.0, 1.0)

        # Brightness
        brightness = self.settings['brightness'] / 100.0
        frame = frame + brightness

        # Contrast
        contrast = self.settings['contrast'] / 100.0 + 1.0
        frame = (frame - 0.5) * contrast + 0.5

        # Saturation (convert to HSV space)
        if self.settings['saturation'] != 100:
            frame = np.clip(np.nan_to_num(frame, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0).astype(np.float32)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hsv[..., 1] = hsv[..., 1] * (self.settings['saturation'] / 100.0)
            frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        # Gamma correction
        if self.settings['gamma'] != 100:
            gamma = self.settings['gamma'] / 100.0
            # Slider semantics: lower=darken, higher=lighten
            frame = np.clip(np.nan_to_num(frame, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)
            frame = np.power(np.maximum(frame, 0.0), 1.0 / max(gamma, 0.1))

        # Skin smoothing before sharpness to avoid sharpening skin texture noise
        frame = self.apply_skin_smoothing(frame)

        # Sharpness (unsharp masking)
        if self.settings['sharpness'] > 0:
            blurred = cv2.GaussianBlur(frame, (0, 0), 3)
            frame = cv2.addWeighted(frame, 1.0 + self.settings['sharpness'] / 100.0,
                                    blurred, -self.settings['sharpness'] / 100.0, 0)

        return frame.clip(0, 1)

    def apply_skin_smoothing(self, frame):
        """Apply gentle skin smoothing only on likely skin regions."""
        try:
            strength = int(self.settings.get('skin_smoothing', 0))
            if strength <= 0:
                return frame

            # Work in uint8 for stable OpenCV filtering and skin masking.
            safe_frame = np.nan_to_num(frame, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)
            safe_frame = np.clip(safe_frame, 0.0, 1.0)
            frame_u8 = (safe_frame * 255).clip(0, 255).astype(np.uint8)
            ycrcb = cv2.cvtColor(frame_u8, cv2.COLOR_BGR2YCrCb)

            # Broad skin threshold; intentionally conservative to avoid background smearing.
            skin_mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
            skin_mask = cv2.GaussianBlur(skin_mask, (0, 0), 2)

            # Keep this path lightweight for live preview stability.
            sigma = 0.6 + (strength / 100.0) * 2.0
            smoothed_u8 = cv2.GaussianBlur(frame_u8, (0, 0), sigmaX=sigma, sigmaY=sigma)

            alpha = min(0.50, strength / 100.0)
            mask = (skin_mask.astype(np.float32) / 255.0)[..., None]
            blended = frame_u8.astype(np.float32) * (1.0 - alpha * mask) + smoothed_u8.astype(np.float32) * (alpha * mask)
            return (blended / 255.0).clip(0, 1)
        except Exception as e:
            # Never let cosmetic enhancement break the camera pipeline.
            print(f"Skin smoothing error: {e}")
            return frame

    def manual_white_balance(self, frame, temp):
        """
        Manual white balance using temperature in Kelvin
        Based on Tanner Helland's algorithm: http://www.tannerhelland.com/4435/translate-temperature-rgb-algorithm-code/
        """
        temp = temp / 100.0

        # Calculate red
        if temp <= 66:
            red = 255
        else:
            red = temp - 60
            red = 329.698727446 * (red ** -0.1332047592)
            red = max(0, min(255, red))

        # Calculate green
        if temp <= 66:
            green = temp
            green = 99.4708025861 * np.log(green) - 161.1195681661
        else:
            green = temp - 60
            green = 288.1221695283 * (green ** -0.0755148492)
        green = max(0, min(255, green))

        # Calculate blue
        if temp >= 66:
            blue = 255
        elif temp <= 19:
            blue = 0
        else:
            blue = temp - 10
            blue = 138.5177312231 * np.log(blue) - 305.0447927307
            blue = max(0, min(255, blue))

        # Normalize and apply
        rgb = np.array([blue, green, red]) / 255.0
        frame = frame * rgb

        return frame

    def auto_white_balance(self, frame):
        """Auto white balance using gray-world correction in uint8 LAB space."""
        frame_u8 = (frame * 255).clip(0, 255).astype(np.uint8)
        lab = cv2.cvtColor(frame_u8, cv2.COLOR_BGR2LAB).astype(np.float32)

        avg_a = np.mean(lab[:, :, 1])
        avg_b = np.mean(lab[:, :, 2])

        # Use luminance-weighted correction with gentle strength.
        luma = lab[:, :, 0] / 255.0
        lab[:, :, 1] -= (avg_a - 128.0) * luma * 0.35
        lab[:, :, 2] -= (avg_b - 128.0) * luma * 0.35

        corrected_u8 = cv2.cvtColor(lab.clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
        return corrected_u8.astype(np.float32) / 255.0

    def auto_color_correction(self, frame):
        """Gentle auto color correction that preserves natural tones."""
        frame_u8 = (frame * 255).clip(0, 255).astype(np.uint8)
        lab = cv2.cvtColor(frame_u8, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
        l = clahe.apply(l)

        # Pull chroma slightly toward neutral to avoid oversaturation and color cast.
        a = cv2.addWeighted(a, 0.92, np.full_like(a, 128), 0.08, 0)
        b = cv2.addWeighted(b, 0.92, np.full_like(b, 128), 0.08, 0)

        corrected_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        return corrected_u8.astype(np.float32) / 255.0

    def get_crop_rect(self, img, size):
        h, w = img.shape[:2]
        ratios = {
            "4x6": (4 / 6, 6 / 4),
            "5x7": (5 / 7, 7 / 5),
            "8x10": (8 / 10, 10 / 8),
            "11x14": (11 / 14, 14 / 11)
        }

        target_ratio = ratios[size][0]
        current_ratio = w / h

        if current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            start_x = (w - new_w) // 2
            return (start_x, 0, start_x + new_w, h)
        else:
            new_h = int(w / target_ratio)
            start_y = (h - new_h) // 2
            return (0, start_y, w, start_y + new_h)

    def crop_to_size(self, img, size):
        x1, y1, x2, y2 = self.get_crop_rect(img, size)
        return img[y1:y2, x1:x2]

    def draw_crop_overlay(self, frame):
        try:
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = self.get_crop_rect(frame, self.settings['crop_size'])

            color = (0, 255, 0)
            thickness = 2

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2

            cv2.line(frame, (x1, center_y), (x2, center_y), color, 1)
            cv2.line(frame, (center_x, y1), (center_x, y2), color, 1)

            marker_size = 15
            cv2.line(frame, (x1, y1), (x1 + marker_size, y1), color, thickness)
            cv2.line(frame, (x1, y1), (x1, y1 + marker_size), color, thickness)
            cv2.line(frame, (x2, y1), (x2 - marker_size, y1), color, thickness)
            cv2.line(frame, (x2, y1), (x2, y1 + marker_size), color, thickness)
            cv2.line(frame, (x1, y2), (x1 + marker_size, y2), color, thickness)
            cv2.line(frame, (x1, y2), (x1, y2 - marker_size), color, thickness)
            cv2.line(frame, (x2, y2), (x2 - marker_size, y2), color, thickness)
            cv2.line(frame, (x2, y2), (x2, y2 - marker_size), color, thickness)

        except Exception as e:
            print(f"Error drawing crop overlay: {str(e)}")

        return frame

    def save_access_code(self, filename, code):
        try:
            # Store JSON in the program's directory
            program_dir = os.path.dirname(os.path.abspath(__file__))
            codes_file = os.path.join(program_dir, "access_codes.json")

            # Debug output
            print(f"[DEBUG] Saving access codes to: {codes_file}")
            print(f"[DEBUG] Directory exists: {os.path.exists(program_dir)}")
            print(f"[DEBUG] Directory writable: {os.access(program_dir, os.W_OK)}")

            # Load existing codes or initialize new dict
            codes = {}
            if os.path.exists(codes_file):
                try:
                    with open(codes_file, "r") as f:
                        codes = json.load(f)
                    print("[DEBUG] Successfully loaded existing access codes")
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[DEBUG] Error loading access codes: {str(e)}")
                    codes = {}

            # Update codes with new entry
            codes[filename] = {
                "code": code,
                "downloads": 0,
                "created": datetime.now().isoformat(),
                "path": filename,
                "filename": os.path.basename(filename),
                "directory": os.path.dirname(filename)
            }

            # Write back to file (using atomic write)
            temp_file = codes_file + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(codes, f, indent=2)

            # Atomic replace
            try:
                os.replace(temp_file, codes_file)
            except Exception as e:
                print(f"[WARNING] Could not do atomic replace: {str(e)}")
                os.rename(temp_file, codes_file)

            print(f"[DEBUG] Successfully saved access codes to {codes_file}")
            return True

        except Exception as e:
            error_msg = f"Failed to save access code:\n{str(e)}\n\n"
            error_msg += f"Attempted path: {codes_file if 'codes_file' in locals() else 'unknown'}\n"
            error_msg += f"Directory exists: {os.path.exists(program_dir) if 'program_dir' in locals() else 'unknown'}\n"
            error_msg += f"Directory writable: {os.access(program_dir, os.W_OK) if 'program_dir' in locals() else 'unknown'}"

            print(f"[ERROR] {error_msg}")
            QMessageBox.warning(
                self,
                "Access Code Error",
                error_msg
            )
            return False

    def upload_to_wordpress(self, image_path, capture_label):
        """Handle WordPress upload using HTTPS API transport."""
        if not self.validate_wp_settings():
            return None
        return self.upload_to_wordpress_api(image_path, capture_label, show_errors=True)

    def upload_to_wordpress_api(self, image_path, capture_label, show_errors=True):
        """Upload to WordPress through HTTPS ingest API."""
        try:
            access_code = generate_secure_access_code()
            # Use normalized code for API auth/signature consistency.
            access_code_api = ''.join(ch for ch in access_code.upper() if ch.isalnum())
            today = datetime.now().strftime("%Y/%m")
            safe_label = ''.join(ch for ch in capture_label if ch.isalnum() or ch in ('-', '_')).strip() or 'Capture'
            remote_filename = f"{safe_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            file_rel_path = f"{today}/{remote_filename}"

            with open(image_path, 'rb') as f:
                image_bytes = f.read()

            payload_hash = hashlib.sha256(image_bytes).hexdigest()
            timestamp = str(int(time.time()))
            signature_message = f"{timestamp}|{file_rel_path}|{access_code_api}|{payload_hash}"
            signature = hmac.new(
                self.settings['wp_shared_secret'].encode(),
                signature_message.encode(),
                hashlib.sha256
            ).hexdigest()

            base_url = self.settings['wp_url'].rstrip('/')
            timeout = int(self.settings.get('wp_api_timeout', 20))
            endpoint = self.settings.get('wp_api_endpoint', '/wp-json/pta-schoolbooth/v1/ingest').strip()
            endpoint = endpoint if endpoint.startswith('/') else '/' + endpoint

            endpoint_candidates = [endpoint]
            if '/pta-schoolbooth/' in endpoint:
                endpoint_candidates.append(endpoint.replace('/pta-schoolbooth/', '/nbpta/'))
            elif '/nbpta/' in endpoint:
                endpoint_candidates.append(endpoint.replace('/nbpta/', '/pta-schoolbooth/'))

            payload = json.dumps({
                'file_rel_path': file_rel_path,
                'access_code': access_code_api,
                'image_b64': base64.b64encode(image_bytes).decode('ascii'),
            }).encode('utf-8')

            headers = {
                'Content-Type': 'application/json',
                'X-PTASB-Timestamp': timestamp,
                'X-PTASB-Signature': signature,
            }

            data = None
            last_error = None
            chosen_endpoint = endpoint
            for candidate in endpoint_candidates:
                try:
                    api_url = f"{base_url}{candidate}"
                    req = urllib_request.Request(
                        api_url,
                        data=payload,
                        headers=headers,
                        method='POST'
                    )
                    with urllib_request.urlopen(req, timeout=timeout) as response:
                        response_body = response.read().decode('utf-8')
                        data = json.loads(response_body) if response_body else {}
                    chosen_endpoint = candidate
                    break
                except urllib_error.HTTPError as http_err:
                    last_error = http_err
                    if http_err.code == 404:
                        continue
                    raise

            if data is None:
                if last_error is not None:
                    raise last_error
                raise RuntimeError('WordPress API did not return a response')

            if chosen_endpoint != endpoint:
                self.settings['wp_api_endpoint'] = chosen_endpoint
                self.save_settings()
                print(f"[DEBUG] Switched WordPress API endpoint to: {chosen_endpoint}")

            download_url = data.get('download_url')
            if not download_url:
                raise RuntimeError('WordPress API response did not include download_url')

            app_download_url = data.get('app_download_url') or download_url
            returned_code = data.get('code', access_code)

            print(f"[DEBUG] Uploaded via HTTPS API: {download_url}")
            return {
                'public_url': download_url,
                'app_url': app_download_url,
                'access_code': returned_code,
            }

        except (urllib_error.URLError, urllib_error.HTTPError, ValueError, RuntimeError, OSError) as e:
            if show_errors:
                QMessageBox.critical(
                    self,
                    "Upload Failed",
                    f"WordPress HTTPS API upload failed:\n{str(e)}"
                )
            return None
            return None

    def generate_qr_code(self, url, capture_label):
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            pil_img = img.get_image()

            temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            pil_img.save(temp_file.name)

            return temp_file.name

        except Exception as e:
            QMessageBox.warning(self, "QR Error", f"Failed to generate QR code: {str(e)}")
            return None

    def print_label(self, qr_img_path, capture_label, image_url):
        """Print QR label using ESC/POS commands"""
        if not self.settings.get('qr_printer'):
            QMessageBox.warning(self, "No Printer", "Please select a QR printer first")
            return

        try:
            # Extract access code from URL
            access_code = "Unknown"
            if image_url and 'code=' in image_url:
                access_code = image_url.split('code=')[1].split('&')[0] if '&' in image_url else \
                    image_url.split('code=')[1]

            try:
                # Initialize thermal ESC/POS printer connection.
                com_port = (self.settings.get('com_port') or self.settings.get('qr_printer') or '').strip()
                if not com_port:
                    raise RuntimeError("No COM port configured for thermal printer")

                printer = p.Serial(
                    devfile=com_port,
                    baudrate=9600,
                    bytesize=8,
                    parity="N",
                    stopbits=1,
                    timeout=1,
                    dsrdtr=False,
                )

                printer.hw_init()

                # Set justification to center
                printer.align = 'center'

                # Set header command
                if self.settings.get('qr_header'):
                    printer.text(self.settings['qr_header'] + "\n")

                # Set name command
                printer.text(capture_label + "\n")
                printer.text(f"Code: {access_code}\n")

                # Set image URL code
                qr_data = image_url or "https://iknowapro.net"

                # QR code and all other settings related to the ESC commands
                printer.qr(qr_data,
                           ec=self.settings.get('qr_error_correction'),
                           size=self.settings.get('qr_module_size'))

                # Footer set code
                if self.settings.get('qr_footer'):
                    printer.text(self.settings['qr_footer'] + "\n")

                # Cut command
                printer.cut()

                # Close command
                printer.close()

            except Exception as e:
                error_msg = f"Error during thermal process{e}\n"
                QMessageBox.critical(self, "Print Error", f"Failed to print photo:\n{error_msg}")

        except Exception as e:
            error_msg = f"Print Error: {str(e)}"
            print(error_msg)
            if self.settings['attendant_mode']:
                self.show_feedback("Oops!", "#F44336")
            else:
                QMessageBox.critical(self, "Print Error", error_msg)

    def print_photo(self, image_path, access_code=''):
        """Print photo using the configured photo printer"""
        if not self.settings.get('photo_printer'):
            QMessageBox.warning(self, "No Printer", "Please select a photo printer first")
            return

        try:
            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=letter)

            page_width, page_height = letter

            if self.settings.get('borderless_photo', False):
                img_x = 0
                img_y = 0
                img_width = page_width
                img_height = page_height
            else:
                # Calculate size based on selected paper size
                paper_size = self.settings.get('photo_paper_size', '4x6')
                if paper_size == '4x6':
                    img_width = 4 * 72
                    img_height = 6 * 72
                elif paper_size == '5x7':
                    img_width = 5 * 72
                    img_height = 7 * 72
                elif paper_size == '8x10':
                    img_width = 8 * 72
                    img_height = 10 * 72
                elif paper_size == '11x14':
                    img_width = 11 * 72
                    img_height = 14 * 72

                img_x = (page_width - img_width) / 2
                img_y = (page_height - img_height) / 2

            # Draw image with quality setting
            quality = self.settings.get('photo_quality', 90)
            c.drawImage(image_path, img_x, img_y,
                        width=img_width, height=img_height,
                        preserveAspectRatio=True, anchor='c',
                        mask='auto')

            if self.settings.get('photo_print_access_code', False) and access_code:
                overlay_height = 28
                overlay_margin = 12
                overlay_width = min(img_width - (overlay_margin * 2), 220)
                overlay_x = img_x + (img_width - overlay_width) / 2
                overlay_y = img_y + overlay_margin
                c.setFillColorRGB(1, 1, 1)
                c.roundRect(overlay_x, overlay_y, overlay_width, overlay_height, 6, fill=1, stroke=0)
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica-Bold", 14)
                c.drawCentredString(img_x + (img_width / 2), overlay_y + 9, f"Access Code: {access_code}")

            c.save()

            # Windows printing
            if sys.platform == 'win32':
                temp_pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                temp_pdf.write(pdf_buffer.getvalue())
                temp_pdf.close()

                try:
                    printer_name = self.settings["photo_printer"]
                    print(f"Attempting to print to: {printer_name}")
                    hprinter = win32print.OpenPrinter(printer_name)
                    try:
                        with open(temp_pdf.name, 'rb') as f:
                            raw_data = f.read()
                        win32print.StartDocPrinter(hprinter, 1, ("Photo Print", None, "RAW"))
                        win32print.StartPagePrinter(hprinter)
                        win32print.WritePrinter(hprinter, raw_data)
                        win32print.EndPagePrinter(hprinter)
                        win32print.EndDocPrinter(hprinter)
                        print("Printing completed successfully")
                    except Exception as e2:
                        error_msg = f"Error during RAW printing: {e2}\n"
                        QMessageBox.critical(self, "Print Error", f"Failed to print photo:\n{error_msg}")
                    finally:
                        win32print.ClosePrinter(hprinter)
                except Exception as e3:
                    error_msg = f"Error opening printer: {e3}\n"
                    QMessageBox.critical(self, "Print Error", f"Failed to print photo:\n{error_msg}")

                os.unlink(temp_pdf.name)

            # It's imperative that we remove the indent here
            if self.settings['attendant_mode']:
                self.show_feedback("OK", "#4CAF50")
        except Exception as e:
            if self.settings['attendant_mode']:
                self.show_feedback("Oops!", "#F44336")
            else:
                QMessageBox.critical(self, "Print Error", f"Failed to print photo: {str(e)}")

    def create_qr_label_image(self, qr_img_path, capture_label, access_code):
        """Create a PNG image of the QR code label using PIL."""
        try:
            # Load QR image
            qr_img = Image.open(qr_img_path)

            # Get all Thermal Printer Values
            header_text = self.settings.get('qr_header', '')
            footer_text = self.settings.get('qr_footer', '')
            font_size = int(self.settings.get('qr_font_size', 12))  # Added Int
            image_width = self.settings.get('thermal_qr_imagewidth', 2)
            bg_color = self.settings.get('qr_bg_color', '#FFFFFF')

            # Calculate the paper

            image_width_in_pixel = image_width * 72

            # Create a blank canvas (3" width, dynamic height)
            width_px = int(image_width_in_pixel)  # 3 inches at 72 DPI #Added INt
            margin = int(10)  # added int
            header_height = int(40) if self.settings.get('qr_header') else 0  # added Int
            footer_height = int(40) if self.settings.get('qr_footer') else 0  # added int
            qr_size = int(min(width_px - 2 * margin, qr_img.width))  # added int
            total_height = int(header_height + qr_size + 60 + footer_height)  # 60 for name + code # added int

            # Create composite image
            composite = Image.new('RGB', (width_px, total_height), bg_color)
            draw = ImageDraw.Draw(composite)
            font = ImageFont.truetype("arial.ttf", font_size)  # or use a custom font

            # Add header
            y_pos = 0
            if self.settings.get('qr_header'):
                draw.text((width_px // 2, y_pos + 10),
                          header_text,
                          fill="black",
                          font=font,
                          anchor="mt")
                y_pos += header_height

            # Add QR (centered)
            qr_img = qr_img.resize((qr_size, qr_size))
            composite.paste(qr_img, ((width_px - qr_size) // 2, y_pos))
            y_pos += qr_size

            # Add capture label + code
            draw.text((width_px // 2, y_pos + 10),
                      capture_label,
                      fill="black",
                      font=font,
                      anchor="mt")
            draw.text((width_px // 2, y_pos + 30),
                      f"Code: {access_code}",
                      fill="black",
                      font=font,
                      anchor="mt")
            y_pos += 60

            # Add footer
            if self.settings.get('qr_footer'):
                draw.text((width_px // 2, y_pos + 10),
                          self.settings['qr_footer'],
                          fill="black",
                          font=font,
                          anchor="mt")

            # Save temporary image
            temp_path = os.path.join(tempfile.gettempdir(), "qr_print_temp.png")
            composite.save(temp_path)
            return temp_path

        except Exception as e:
            raise RuntimeError(f"Thermal print failed: {str(e)}")

    def _wrap_text(self, canvas, text, max_width, font_name, font_size):
        """Helper method to wrap text to specified width"""
        lines = []
        words = text.split()

        while words:
            line = []
            while words:
                # Temporarily add the next word to see if it fits
                test_line = ' '.join(line + [words[0]])
                test_width = canvas.stringWidth(test_line, font_name, font_size)

                if test_width <= max_width:
                    line.append(words.pop(0))
                else:
                    break

            lines.append(' '.join(line))

        return lines

    def show_print_preview(self, qr_path, capture_label, image_url):
        dialog = QDialog(self)
        self.center_dialog(dialog)
        dialog.setWindowTitle("Print Preview")
        dialog.setGeometry(400, 400, 400, 500)
        self.apply_modern_settings_dialog_style(dialog)

        layout = QVBoxLayout()
        layout.setSpacing(12)

        pixmap = QPixmap(qr_path)
        label = QLabel()
        label.setPixmap(pixmap.scaled(300, 300, Qt.KeepAspectRatio))
        layout.addWidget(label, 0, Qt.AlignCenter)

        info_label = QLabel(f"Label: {capture_label}\nURL: {image_url}")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        btn_print = QPushButton("Print Label")
        btn_print.setIcon(self._get_action_icon("print", QStyle.SP_DialogSaveButton, size=20))
        btn_print.setIconSize(QSize(20, 20))
        btn_print.clicked.connect(lambda: self.print_label(qr_path, capture_label, image_url))
        layout.addWidget(btn_print)

        btn_close = QPushButton("Close")
        btn_close.setIcon(self._get_action_icon("close", QStyle.SP_DialogCloseButton, size=20))
        btn_close.setIconSize(QSize(20, 20))
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)

        dialog.setLayout(layout)
        dialog.exec_()

    def capture_image(self):
        print(f"Show QR Preview: {self.settings.get('show_qr_print_preview')}")
        print("capture_image: Starting capture process...")
        if not self.cap or not self.cap.isOpened():
            QMessageBox.warning(self, "Camera Error", "Camera not available")
            return

        try:
            print("capture_image: Attempting to read frame...")
            ret, frame = self.cap.read()
            if not ret:
                raise RuntimeError("Failed to capture image")

            # Process frame with crop lines for preview
            processed = self.process_frame(frame)

            # Process frame without crop lines for saving
            show_crop = self.settings["show_crop_overlay"]
            self.settings["show_crop_overlay"] = False
            processed_for_save = self.process_frame(frame)
            self.settings["show_crop_overlay"] = show_crop

            cropped = self.crop_to_size(processed_for_save, self.settings['crop_size'])

            self.last_captured = cropped.copy()
            self.update_last_capture_display()

            capture_label = self.settings.get('capture_label', 'Session')
            self.last_capture_name = capture_label

            base_dir = self.settings["output_dir"]
            today = datetime.now().strftime("%Y-%m-%d")
            save_folder = os.path.join(base_dir, today)
            os.makedirs(save_folder, exist_ok=True)

            timestamp = datetime.now().strftime("%H%M%S")
            filename = os.path.join(save_folder, f"capture_{today}_{timestamp}.jpg")

            cv2.imwrite(filename, cropped)
            print(f"capture_image: Image saved to {filename}")
            self.last_filepath = filename  # Track the filepath
            self.purge_local_storage()
            self.print_photo_btn.show()  # Show re-print buttons
            self.print_qr_btn.show()

            # Check conditions for simplified saving
            if not self.settings['wp_link_enabled'] and \
                    not self.settings['photo_printing_enabled'] and \
                    not self.settings['qr_printing_enabled']:

                if self.settings['attendant_mode']:
                    self.show_feedback("Saved", "#4CAF50")
                else:
                    QMessageBox.information(self, "Saved", f"Image saved to:\n{filename}")

            else:
                # All WP/Printing functions here
                print("capture_image: Starting WP/Printing functions...")

                self.last_photo_url = ""
                self.last_app_photo_url = ""
                self.last_access_code = ""
                if self.settings['wp_link_enabled']:
                    upload_result = self.upload_to_wordpress(filename, capture_label)
                    if not upload_result:
                        print("capture_image: WP upload failed, aborting printing...")
                        return

                    if isinstance(upload_result, dict):
                        self.last_photo_url = upload_result.get('public_url', '')
                        self.last_app_photo_url = upload_result.get('app_url') or self.last_photo_url
                        self.last_access_code = format_access_code_for_display(upload_result.get('access_code', ''))
                    else:
                        self.last_photo_url = upload_result
                        self.last_app_photo_url = upload_result

                if self.last_app_photo_url or self.last_photo_url:
                    self.open_link_btn.show()
                else:
                    self.open_link_btn.hide()

                if self.settings['qr_printing_enabled']:
                    if not self.last_photo_url:
                        QMessageBox.warning(
                            self,
                            "WordPress Required for QR",
                            "QR printing requires WordPress upload to be enabled and successful."
                        )
                        return

                    qr_code_path = self.generate_qr_code(self.last_photo_url, capture_label)
                    if not qr_code_path:
                        print("capture_image: QR code generation failed.")
                        return

                    try:
                        # Generate access code
                        access_code = self.last_access_code or ''
                        if self.settings['qr_print_mode'] == "Thermal Printer":
                            com_port = self.settings.get('com_port')
                            header_text = self.settings.get('qr_header', '')
                            footer_text = self.settings.get('qr_footer', '')
                            self.print_qr_code_thermal(self.last_photo_url, capture_label, access_code,
                                                       header_text, footer_text, com_port)
                        else:
                            printer_name = self.settings.get('qr_printer')
                            qr_header = self.settings.get('qr_header', '')
                            qr_footer = self.settings.get('qr_footer', '')
                            qr_font_size = self.settings.get('qr_font_size', 12)
                            paper_size = self.settings.get('qr_paper_size', "4x6")
                            qr_margin_top = self.settings.get('qr_margin_top', 10)
                            qr_margin_left = self.settings.get('qr_margin_left', 10)
                            qr_margin_right = self.settings.get('qr_margin_right', 10)
                            qr_margin_bottom = self.settings.get('qr_margin_bottom', 10)
                            self.print_qr_code_standard(self.last_photo_url, capture_label, printer_name,
                                                        qr_header, qr_footer, qr_font_size, paper_size, qr_margin_top,
                                                        qr_margin_left, qr_margin_right, qr_margin_bottom, access_code)
                    finally:
                        try:
                            os.unlink(qr_code_path)  # Clean up temp QR code file
                        except Exception as e:
                            print(f"capture_image: Error deleting temp QR code: {e}")

                if self.settings.get('photo_printing_enabled', False):
                    print("capture_image: photo_printing_enabled is True")  # debug
                    print("capture_image: Attempting to print photo...")
                    self.print_photo(filename, self.last_access_code)
                    print("capture_image: Printing photo should have trigger")

                if self.settings['attendant_mode']:
                    self.show_feedback("OK", "#4CAF50")  # Green success
                else:
                    # Original success message
                    success_msg = QMessageBox(self)
                    success_msg.setIcon(QMessageBox.Information)
                    success_msg.setWindowTitle("Success")
                    success_msg.setText(
                        f"Image saved and processed!\nLocal: {filename}\nURL: {self.last_photo_url if self.last_photo_url else 'Not uploaded'}")

                    QTimer.singleShot(3000, success_msg.close)
                    success_msg.exec_()

        except Exception as e:
            print(f"capture_image: Main try block error: {str(e)}")

    def update_last_capture_display(self):
        if self.last_captured is None:
            return

        self.placeholder.hide()

        rgb = cv2.cvtColor(self.last_captured, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w

        qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)

        pixmap = QPixmap.fromImage(qt_img)
        pixmap = pixmap.scaled(
            self.last_capture_label.width(),
            self.last_capture_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.last_capture_label.setPixmap(pixmap)

    def update_frame(self):
        if not self.cap or not self.cap.isOpened():
            # Show camera error placeholder
            placeholder = QPixmap(self.camera_label.width(), self.camera_label.height())
            placeholder.fill(Qt.gray)
            error_text = QLabel("Camera Not Available")
            error_text.setAlignment(Qt.AlignCenter)
            error_text.setStyleSheet("color: white; font-size: 24px;")

            layout = QVBoxLayout()
            layout.addWidget(error_text)

            widget = QWidget()
            widget.setLayout(layout)
            widget.render(placeholder)

            self.camera_label.setPixmap(placeholder)
            return

        try:
            ret, frame = self.cap.read()
            if not ret:
                raise RuntimeError("Failed to capture frame")

            processed = self.process_frame(frame)

            rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            self.current_frame_size = (w, h)
            bytes_per_line = ch * w
            qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)

            # Scale the pixmap to fit the label while maintaining aspect ratio
            pixmap = QPixmap.fromImage(qt_img)
            pixmap = pixmap.scaled(
                self.camera_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.camera_label.setPixmap(pixmap)
        except Exception as e:
            print(f"Camera error: {str(e)}")


    def save_settings(self):
        """Save all current settings to JSON file."""
        try:
            self.settings.save()
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save settings: {str(e)}")

    def load_settings(self):
        """Settings are loaded automatically by SettingsManager in __init__.
        This method is kept for compatibility but does nothing.
        """
        pass

    def load_logo(self):
        """Loads the logo image, handles potential errors, and sets the pixmap."""
        try:
            logo_pixmap = QPixmap("logo_PB.png")  # Assumes logo is in the same directory
            if not logo_pixmap.isNull():
                logo_pixmap = logo_pixmap.scaledToWidth(300, Qt.SmoothTransformation)
                self.logo_label.setPixmap(logo_pixmap)
            else:
                self.logo_label.setText("Logo Image Missing")
                self.logo_label.setStyleSheet("font-size: 16px; color: #666;")
        except Exception as e:
            print(f"Error loading logo: {e}")
            self.logo_label.setText("Logo Image Error")
            self.logo_label.setStyleSheet("font-size: 16px; color: #ff0000;")

    def load_button_icons(self):
        """Load and apply icons to action buttons."""
        try:
            icon = self._get_material_icon("photo_camera", size=48)
            if icon.isNull():
                # Fallback to bundled app icon if material icon package is unavailable.
                icon_path = "app.png"
                if os.path.exists(icon_path):
                    icon = QIcon(icon_path)

            if not icon.isNull() and hasattr(self, 'capture_btn'):
                self.capture_btn.setIcon(icon)
                self.capture_btn.setIconSize(QSize(48, 48))
        except Exception as e:
            print(f"Warning: Could not load button icons: {e}")

    def _get_material_icon(self, name, size=24):
        """Load a Material icon, trying common available sizes before giving up."""
        try:
            from qt_material_icons import MaterialIcon
            # Common packaged resource buckets are usually 24/48; try requested size first.
            candidate_sizes = []
            for candidate in (size, 24, 48, 20):
                if isinstance(candidate, int) and candidate > 0 and candidate not in candidate_sizes:
                    candidate_sizes.append(candidate)

            for icon_size in candidate_sizes:
                try:
                    icon = MaterialIcon(name, size=icon_size)
                    if not icon.isNull():
                        return icon
                except Exception:
                    continue

            return QIcon()
        except Exception:
            return QIcon()

    def _get_action_icon(self, material_name, fallback_standard_icon, size=22):
        """Return a material icon when available, otherwise a native Qt standard icon."""
        icon = self._get_material_icon(material_name, size=size)
        if not icon.isNull():
            return icon
        return self.style().standardIcon(fallback_standard_icon)

    def select_camera(self):
            if not self.available_cameras:
                QMessageBox.warning(self, "Camera Selection", "No cameras available")
                return

            dialog = QDialog(self)
            self.apply_modern_settings_dialog_style(dialog)
            self.center_dialog(dialog)
            dialog.setWindowTitle("Select Camera")
            dialog.setGeometry(400, 400, 300, 150)

            layout = QVBoxLayout()
            layout.addWidget(QLabel("Available Cameras:"))

            camera_combo = QComboBox()
            for i, camera in enumerate(self.available_cameras):
                camera_combo.addItem(f"Camera {i}", i)

            camera_combo.setCurrentIndex(self.camera_index)
            layout.addWidget(camera_combo)

            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            ok_btn = button_box.button(QDialogButtonBox.Ok)
            cancel_btn = button_box.button(QDialogButtonBox.Cancel)
            if ok_btn is not None:
                ok_btn.setText("Use Camera")
                ok_btn.setIcon(self._get_action_icon("check_circle", QStyle.SP_DialogApplyButton, size=20))
                ok_btn.setIconSize(QSize(20, 20))
            if cancel_btn is not None:
                cancel_btn.setIcon(self._get_action_icon("close", QStyle.SP_DialogCancelButton, size=20))
                cancel_btn.setIconSize(QSize(20, 20))
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)

            dialog.setLayout(layout)

            if dialog.exec_() == QDialog.Accepted:
                new_index = camera_combo.currentData()
                if new_index != self.camera_index:
                    self.switch_camera(new_index)

    def switch_camera(self, index):
            if self.cap:
                self.cap.release()

            try:
                if index >= len(self.available_cameras):
                    index = 0

                self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                    if self.cap.isOpened():
                        index = 0
                    else:
                        raise RuntimeError("No cameras available")

                self.camera_index = index
                self.settings["camera_index"] = index
                print(f"Switched to camera {index}")
            except Exception as e:
                QMessageBox.warning(self, "Camera Error",
                                    f"Failed to switch cameras: {str(e)}")
                try:
                    self.cap = cv2.VideoCapture(self.settings["camera_index"], cv2.CAP_DSHOW)
                    if not self.cap.isOpened():
                        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                except:
                    self.cap = None

    def reprint_photo(self):
        """Re-print the last captured photo."""
        if self.last_captured is None:
            QMessageBox.warning(self, "No Photo", "No photo available to reprint.")
            return

        try:
            if hasattr(self, 'last_filepath') and self.last_filepath:  # Check path
                filename = self.last_filepath
                if not os.path.exists(filename):
                    QMessageBox.critical(self, "Error", f"File not found: {filename}")
                    return
            else:
                QMessageBox.critical(self, "Error", "No File Path available.  Please capture a new image.")
                return  # Exit

            try:
                self.print_photo(filename, self.last_access_code)  # re-runs the printing.
            except Exception as e:
                QMessageBox.critical(self, "Reprint Error", f"Failed to reprint photo: {str(e)}")

        except Exception as e:
            QMessageBox.critical(self, "Reprint Error", f"An error occurred: {str(e)}")

    def reprint_qr_code(self):
        """Re-print the QR code for the last captured photo."""
        if not self.last_photo_url:
            QMessageBox.warning(self, "No QR Code", "No QR code available to reprint.")
            return

        try:
            capture_label = getattr(self, 'last_capture_name', self.settings.get('capture_label', 'Session'))

            if self.settings['qr_printing_enabled']:
                qr_code_path = self.generate_qr_code(self.last_photo_url, capture_label)
                if not qr_code_path:
                    print("reprint_qr_code: QR code generation failed.")
                    return

                try:
                    # Generate access code
                    access_code = self.last_access_code or ''
                    if self.settings['qr_print_mode'] == "Thermal Printer":
                        com_port = self.settings.get('com_port')
                        header_text = self.settings.get('qr_header', '')
                        footer_text = self.settings.get('qr_footer', '')
                        self.print_qr_code_thermal(self.last_photo_url, capture_label, access_code,
                                                   header_text, footer_text, com_port)
                    else:
                        printer_name = self.settings.get('qr_printer')
                        qr_header = self.settings.get('qr_header', '')
                        qr_footer = self.settings.get('qr_footer', '')
                        qr_font_size = self.settings.get('qr_font_size', 12)
                        paper_size = self.settings.get('qr_paper_size', "4x6")
                        qr_margin_top = self.settings.get('qr_margin_top', 10)
                        qr_margin_left = self.settings.get('qr_margin_left', 10)
                        qr_margin_right = self.settings.get('qr_margin_right', 10)
                        qr_margin_bottom = self.settings.get('qr_margin_bottom', 10)
                        self.print_qr_code_standard(self.last_photo_url, capture_label, printer_name,
                                                    qr_header, qr_footer, qr_font_size, paper_size, qr_margin_top,
                                                    qr_margin_left, qr_margin_right, qr_margin_bottom, access_code)

                except Exception as e:
                    QMessageBox.critical(self, "Reprint Error", f"Failed to print QR code: {str(e)}")

        except Exception as e:
            QMessageBox.critical(self, "Reprint Error", f"An error occurred: {str(e)}")

    def _get_preview_rect(self):
        pixmap = self.camera_label.pixmap()
        if pixmap is None:
            return None
        offset_x = (self.camera_label.width() - pixmap.width()) // 2
        offset_y = (self.camera_label.height() - pixmap.height()) // 2
        return QRect(offset_x, offset_y, pixmap.width(), pixmap.height())

    def get_watermark_rect(self):
        preview_rect = self._get_preview_rect()
        wm_state = self._get_active_watermark_state()
        watermark = self.get_transformed_watermark(wm_state)
        if preview_rect is None or watermark is None:
            return QRect()

        frame_w, frame_h = self.current_frame_size
        if frame_w <= 0 or frame_h <= 0:
            return QRect()

        scale_x = preview_rect.width() / float(frame_w)
        scale_y = preview_rect.height() / float(frame_h)

        wm_h, wm_w = watermark.shape[:2]
        wm_display_w = max(1, int(wm_w * scale_x))
        wm_display_h = max(1, int(wm_h * scale_y))

        x = preview_rect.x() + int(wm_state['x'] / 100.0 * max(1, preview_rect.width() - wm_display_w))
        y = preview_rect.y() + int(wm_state['y'] / 100.0 * max(1, preview_rect.height() - wm_display_h))
        return QRect(x, y, wm_display_w, wm_display_h)

    def _get_watermark_handles(self):
        rect = self.get_watermark_rect()
        if rect.isNull():
            return None, None
        resize_handle = QPoint(rect.right(), rect.bottom())
        rotate_handle = QPoint(rect.center().x(), rect.top())
        return resize_handle, rotate_handle

    def _snap_percent(self, value, step):
        if step <= 0:
            return value
        return round(value / step) * step

    def watermark_mouse_press(self, event):
        if not self.settings.get('watermark_interactive', True):
            return
        if self.watermark_processed is None or not self.settings.get('watermark_enabled', False):
            return

        watermark_rect = self.get_watermark_rect()
        resize_handle, rotate_handle = self._get_watermark_handles()
        if resize_handle is None:
            return

        click_pos = event.pos()
        if (click_pos - rotate_handle).manhattanLength() <= self.watermark_handle_radius * 2:
            self.watermark_rotating = True
            self.camera_label.setCursor(Qt.CrossCursor)
        elif (click_pos - resize_handle).manhattanLength() <= self.watermark_handle_radius * 2:
            self.watermark_resizing = True
            self.camera_label.setCursor(Qt.SizeFDiagCursor)
        elif watermark_rect.contains(click_pos):
            self.watermark_dragging = True
            self.camera_label.setCursor(Qt.ClosedHandCursor)
        else:
            return

        self.watermark_start_pos = click_pos
        self._watermark_edit_state = {
            'watermark_x': float(self.settings.get('watermark_x', 50.0)),
            'watermark_y': float(self.settings.get('watermark_y', 50.0)),
            'watermark_rotation': float(self.settings.get('watermark_rotation', 0.0)),
            'watermark_scale': float(self.settings.get('watermark_scale', 1.0)),
            'watermark_size': float(self.settings.get('watermark_size', 30.0)),
            'watermark_opacity': float(self.settings.get('watermark_opacity', 70.0)),
        }
        self.watermark_start_x = self._watermark_edit_state['watermark_x']
        self.watermark_start_y = self._watermark_edit_state['watermark_y']
        self.watermark_start_rotation = self._watermark_edit_state['watermark_rotation']
        self.watermark_start_scale = self._watermark_edit_state['watermark_scale']

    def watermark_mouse_move(self, event):
        if not (self.watermark_dragging or self.watermark_resizing or self.watermark_rotating):
            if not self.settings.get('watermark_interactive', True):
                return
            watermark_rect = self.get_watermark_rect()
            resize_handle, rotate_handle = self._get_watermark_handles()
            if resize_handle and (event.pos() - resize_handle).manhattanLength() <= self.watermark_handle_radius * 2:
                self.camera_label.setCursor(Qt.SizeFDiagCursor)
            elif rotate_handle and (event.pos() - rotate_handle).manhattanLength() <= self.watermark_handle_radius * 2:
                self.camera_label.setCursor(Qt.CrossCursor)
            elif watermark_rect.contains(event.pos()):
                self.camera_label.setCursor(Qt.OpenHandCursor)
            else:
                self.camera_label.unsetCursor()
            return

        preview_rect = self._get_preview_rect()
        if preview_rect is None:
            return

        delta = event.pos() - self.watermark_start_pos

        if self.watermark_dragging:
            x_pct = max(0.0, min(100.0, self.watermark_start_x + (delta.x() / max(1, preview_rect.width()) * 100.0)))
            y_pct = max(0.0, min(100.0, self.watermark_start_y + (delta.y() / max(1, preview_rect.height()) * 100.0)))

            if self.settings.get('watermark_snap_grid', True):
                step = max(1, int(self.settings.get('watermark_snap_grid_step', 5)))
                x_pct = self._snap_percent(x_pct, step)
                y_pct = self._snap_percent(y_pct, step)

            if self.settings.get('watermark_snap_center', True):
                center_threshold = 2.0
                if abs(x_pct - 50.0) <= center_threshold:
                    x_pct = 50.0
                if abs(y_pct - 50.0) <= center_threshold:
                    y_pct = 50.0

            self._watermark_edit_state['watermark_x'] = max(0.0, min(100.0, x_pct))
            self._watermark_edit_state['watermark_y'] = max(0.0, min(100.0, y_pct))
        elif self.watermark_resizing:
            scale_delta = delta.x() * 0.01
            self._watermark_edit_state['watermark_scale'] = max(0.1, min(3.0, self.watermark_start_scale + scale_delta))
        elif self.watermark_rotating:
            self._watermark_edit_state['watermark_rotation'] = (self.watermark_start_rotation + delta.x()) % 360

        self.update_frame()

    def watermark_mouse_release(self, event):
        if self.watermark_dragging or self.watermark_resizing or self.watermark_rotating:
            if self._watermark_edit_state is not None:
                self.settings['watermark_x'] = self._watermark_edit_state['watermark_x']
                self.settings['watermark_y'] = self._watermark_edit_state['watermark_y']
                self.settings['watermark_rotation'] = self._watermark_edit_state['watermark_rotation']
                self.settings['watermark_scale'] = self._watermark_edit_state['watermark_scale']
            self.save_settings()
            self._save_active_frame_settings()
        self._watermark_edit_state = None
        self.watermark_dragging = False
        self.watermark_resizing = False
        self.watermark_rotating = False
        self.camera_label.unsetCursor()

    def force_watermark_visibility(self):
            """Temporary debug function"""
            self.settings['watermark_enabled'] = True
            self.settings['watermark_opacity'] = 100
            self.settings['watermark_x'] = 50
            self.settings['watermark_y'] = 50
            self.settings['watermark_size'] = 30
            print("WATERMARK VISIBILITY FORCED VIA MENU")
            self.update_frame()  # Refresh display

    def open_watermark_settings(self):
            dialog = WatermarkEditorDialog(self)
            self.apply_modern_settings_dialog_style(dialog)
            self.center_dialog(dialog)

            if dialog.exec_() == QDialog.Accepted:
                updated = dialog.get_settings_update()
                self.settings.update(updated)
                self.settings['watermark_interactive'] = False

                if self.watermark_original is not None:
                    self.process_watermark()

                self.save_settings()
                self._save_active_frame_settings()
                self.update_frame()

    def open_image_settings(self):
            """Open the image settings dialog"""
            dialog = ImageSettingsDialog(self)
            self.apply_modern_settings_dialog_style(dialog)
            self.center_dialog(dialog)

            # Keep a snapshot so Cancel can restore previous values.
            original_settings = {
                'auto_wb': self.settings['auto_wb'],
                'auto_color': self.settings['auto_color'],
                'wb_temp': self.settings['wb_temp'],
                'brightness': self.settings['brightness'],
                'contrast': self.settings['contrast'],
                'saturation': self.settings['saturation'],
                'sharpness': self.settings['sharpness'],
                'skin_smoothing': self.settings.get('skin_smoothing', 0),
                'gamma': self.settings['gamma'],
                'crop_size': self.settings['crop_size']
            }

            def _dialog_values():
                return {
                    'auto_wb': dialog.auto_wb_cb.isChecked(),
                    'auto_color': dialog.auto_color_cb.isChecked(),
                    'wb_temp': dialog.wb_temp_slider.value(),
                    'brightness': dialog.brightness_slider.value(),
                    'contrast': dialog.contrast_slider.value(),
                    'saturation': dialog.saturation_slider.value(),
                    'sharpness': dialog.sharpness_slider.value(),
                    'skin_smoothing': dialog.skin_smoothing_slider.value(),
                    'gamma': dialog.gamma_slider.value(),
                    'crop_size': dialog.crop_combo.currentText()
                }

            def _apply_live_preview(*_args):
                self.settings.update(_dialog_values())

            # Set current values
            dialog.auto_wb_cb.setChecked(self.settings['auto_wb'])
            dialog.auto_color_cb.setChecked(self.settings['auto_color'])
            dialog.wb_temp_slider.setValue(self.settings['wb_temp'])
            dialog.brightness_slider.setValue(self.settings['brightness'])
            dialog.contrast_slider.setValue(self.settings['contrast'])
            dialog.saturation_slider.setValue(self.settings['saturation'])
            dialog.sharpness_slider.setValue(self.settings['sharpness'])
            dialog.skin_smoothing_slider.setValue(self.settings.get('skin_smoothing', 0))
            dialog.gamma_slider.setValue(self.settings['gamma'])
            dialog.crop_combo.setCurrentText(self.settings['crop_size'])

            # Live preview wiring
            dialog.auto_wb_cb.toggled.connect(_apply_live_preview)
            dialog.auto_color_cb.toggled.connect(_apply_live_preview)
            dialog.wb_temp_slider.valueChanged.connect(_apply_live_preview)
            dialog.brightness_slider.valueChanged.connect(_apply_live_preview)
            dialog.contrast_slider.valueChanged.connect(_apply_live_preview)
            dialog.saturation_slider.valueChanged.connect(_apply_live_preview)
            dialog.sharpness_slider.valueChanged.connect(_apply_live_preview)
            dialog.skin_smoothing_slider.valueChanged.connect(_apply_live_preview)
            dialog.gamma_slider.valueChanged.connect(_apply_live_preview)
            dialog.crop_combo.currentTextChanged.connect(_apply_live_preview)

            # Show current settings immediately in preview while dialog is open.
            _apply_live_preview()

            if dialog.exec_() == QDialog.Accepted:
                # Save settings when OK is clicked
                self.settings.update(_dialog_values())
                self.save_settings()
            else:
                # Cancel: revert preview-only edits.
                self.settings.update(original_settings)
                self.update_frame()

    def open_wp_link_settings(self):
        dialog = WPLinkSettingsDialog(self)
        self.apply_modern_settings_dialog_style(dialog)
        self.center_dialog(dialog)
        dialog.exec_()

    def set_default_print_message(self):
        msg, ok = QInputDialog.getMultiLineText(
            self,
            "Default Print Message",
            "Enter default message for printouts:",
            self.default_print_message
        )
        if ok:
            self.default_print_message = msg

    def select_qr_printer(self, printer_label):
        if sys.platform == 'win32':
            printers = [win32print.GetDefaultPrinter()]
            printers += [printer[2] for printer in win32print.EnumPrinters(2)]
            printer, ok = QInputDialog.getItem(
                self, "Select QR Printer",
                "Available Printers:", printers, 0, False
            )
            if ok and printer:
                self.settings['qr_printer'] = printer
                QMessageBox.information(self, "Printer Selected",
                                        f"QR printer set to: {printer}")
                self.save_settings()
                printer_label.setText(f"Selected Printer: {printer}")  # this works because self is available

    def print_qr_code_standard(self, url, capture_label, printer_name, qr_header, qr_footer, qr_font_size, paper_size, qr_margin_top, qr_margin_left, qr_margin_right, qr_margin_bottom, access_code=''):
        """Print QR code label as a PDF using reportlab for standard printers."""
        try:
            # 1. Generate QR Code Image
            qr_code_path = self.generate_qr_code(url, capture_label)
            if not qr_code_path:
                raise ValueError("Failed to generate QR code image")

            # 2. Setup PDF Generation
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            page_width, page_height = letter

            # Convert margins to points
            top_margin = qr_margin_top  # top
            left_margin = qr_margin_left  # left
            right_margin = qr_margin_right  # right
            bottom_margin = qr_margin_bottom  # bottom

            # Calculate available space based on margins
            available_width = page_width - left_margin - right_margin
            available_height = page_height - top_margin - bottom_margin

            # 3. Calculate QR Code Size
            img = Image.open(qr_code_path)
            img_width, img_height = img.size
            qr_size = min(available_width, available_height) * 0.5  # Occupy up to 50%

            # 4. Calculate Positions
            x = (page_width - qr_size) / 2
            y = (available_height - qr_size) / 2 + top_margin

            # 5. Define Fonts
            font_name = "Helvetica"

            # 6. Add Header
            c.setFont(font_name, qr_font_size)
            c.drawCentredString(page_width / 2.0, top_margin, qr_header)

            # 7. Draw QR Code
            c.drawImage(qr_code_path, x, y, width=qr_size, height=qr_size, preserveAspectRatio=True)

            # 8. Add Text Information
            text_y = y + qr_size + 20  # Position text below QR code

            c.setFont(font_name, qr_font_size)
            c.drawCentredString(page_width / 2.0, text_y, f"{capture_label} (Scan to view)")

            if self.settings.get('qr_print_access_code', True) and access_code:
                c.setFont(font_name, qr_font_size)
                c.drawCentredString(page_width / 2.0, text_y - (qr_font_size + 8), f"Access Code: {access_code}")

            # 9. Draw Footer
            c.setFont(font_name, qr_font_size)
            c.drawCentredString(page_width / 2.0, page_height - bottom_margin - 20, qr_footer)

            # 10. Save PDF
            c.showPage()  # Complete the first page
            c.save()

            # 11. Print PDF
            buffer.seek(0)  # Rewind to the beginning of the buffer
            self.print_pdf_buffer(buffer, printer_name)

        except Exception as e:
            QMessageBox.critical(self, "Printing Error", f"Error printing QR code: {str(e)}")
            return

    def print_pdf_buffer(self, buffer, printer_name):
        """Print PDF from buffer (platform-specific)."""
        try:
            if sys.platform == 'win32':
                temp_pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                temp_pdf.write(buffer.getvalue())
                temp_pdf.close()

                try:
                    hprinter = win32print.OpenPrinter(printer_name)
                    try:
                        with open(temp_pdf.name, 'rb') as f:
                            raw_data = f.read()
                        win32print.StartDocPrinter(hprinter, 1, ("QR Code Print", None, "RAW"))
                        win32print.StartPagePrinter(hprinter)
                        win32print.WritePrinter(hprinter, raw_data)
                        win32print.EndPagePrinter(hprinter)
                        win32print.EndDocPrinter(hprinter)
                    except Exception as e2:
                        QMessageBox.critical(self, "Print Error", f"Error during RAW printing: {e2}\n")
                    finally:
                        win32print.ClosePrinter(hprinter)

                except Exception as e3:
                    QMessageBox.critical(self, "Printing Error", f"Failed to open printer: {str(e3)}")

                finally:
                    os.unlink(temp_pdf.name)  # Delete temp file

        except Exception as e:
            QMessageBox.critical(self, "Printing Error", f"An unexpected printing error occurred: {str(e)}")

    def print_qr_code_thermal(self, url, capture_label, access_code, header_text, footer_text, com_port):
        """Print QR label using ESC/POS commands"""
        try:
            printer = p.Serial(devfile=com_port,
                               baudrate=9600,
                               bytesize=8,
                               parity="N",
                               stopbits=1,
                               timeout=1,
                               dsrdtr=False)

            try:
                # Error correction LEVEL
                error_correction_level = self.settings.get('qr_error_correction', "M")
                if error_correction_level == "L":
                    ec = qrcode.constants.ERROR_CORRECT_L
                elif error_correction_level == "M":
                    ec = qrcode.constants.ERROR_CORRECT_M
                elif error_correction_level == "Q":
                    ec = qrcode.constants.ERROR_CORRECT_Q
                elif error_correction_level == "H":
                    ec = qrcode.constants.ERROR_CORRECT_H
                else:
                    ec = qrcode.constants.ERROR_CORRECT_M  # Default

                # Apply replace
                formatted_header_text = header_text.replace("\\n", "\r\n") if header_text else ""
                formatted_footer_text = footer_text.replace("\\n", "\r\n") if footer_text else ""

                # Bold Check for Header
                if self.settings.get('qr_header_bold', False):
                    printer.bold = True

                # Underline check for header
                if self.settings.get('qr_header_ul', False):
                    printer.underline = True

                # Set justification to center
                printer.align = 'center'

                # Header Command
                printer.text(formatted_header_text + "\r\n")

                # Clear the check for the header
                printer.bold = False
                printer.underline = False

                # Set label command
                printer.text(capture_label + "\r\n")
                if self.settings.get('qr_print_access_code', True) and access_code:
                    printer.text(f"Code: {access_code}\r\n")

                # Set image URL code
                qr_data = url or "https://iknowapro.net"

                # QR code and all other settings related to the ESC commands
                printer.qr(qr_data,
                           ec=ec,
                           size=int(self.settings.get('qr_module_size', 3)))  # IMPORTANT: to int

                # Bold check for footer
                if self.settings.get('qr_footer_bold', False):
                    printer.bold = True

                # Underline check for header
                if self.settings.get('qr_header_ul', False):
                    printer.underline = True

                # Footer Command
                printer.text(formatted_footer_text + "\r\n")

                # Clear the check for the footer
                printer.bold = False
                printer.underline = False

                # Cut command
                printer.cut()

                # Close command
                printer.close()

            except Exception as e:
                error_msg = f"Error during thermal process {e}\n"
                QMessageBox.critical(self, "Print Error", f"Failed to print photo:\n{error_msg}")

        except Exception as e:
            error_msg = f"Print Error: {str(e)}"
            print(error_msg)
            if self.settings['attendant_mode']:
                self.show_feedback("Oops!", "#F44336")
            else:
                QMessageBox.critical(self, "Print Error", error_msg)

    def center_dialog(self, dialog):
        """Centers the given dialog on the main application window."""
        geometry = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        centerPoint = QApplication.desktop().screenGeometry(screen).center()
        dialog.move(centerPoint - geometry.center())

    def closeEvent(self, event):
        """Handle window close event with save prompt"""
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, 'Unsaved Changes',
                "You have unsaved changes. Would you like to save before exiting?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                self._save_active_frame_settings()
                self.save_settings()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            self._save_active_frame_settings()
            event.accept()

        # Release camera resources
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("Camera released")

        # Explicitly exit the application
        QApplication.instance().quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Set a comfortable base font so the UI doesn't look tiny on modern displays
    from PyQt5.QtGui import QFont
    _font = QFont()
    _font.setPointSize(15)
    app.setFont(_font)

    # Use a built-in modern theme to avoid external icon/theme resource warnings.
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget {
            background-color: #f4f7fb;
            color: #1f2a36;
            font-size: 16px;
        }
        QMainWindow, QDialog {
            background-color: #f4f7fb;
        }
        QGroupBox {
            border: 1px solid #d7e0eb;
            border-radius: 10px;
            margin-top: 12px;
            padding-top: 12px;
            font-weight: 600;
            background-color: #ffffff;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #3b4d63;
        }
        QPushButton {
            border-radius: 8px;
            border: 1px solid #c8d4e3;
            background-color: #ffffff;
            padding: 8px 14px;
            min-height: 40px;
            font-size: 15px;
        }
        QPushButton:hover {
            background-color: #eef4fb;
            border-color: #8fb5e2;
        }
        QPushButton:pressed {
            background-color: #dfeaf8;
        }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
            background-color: #ffffff;
            border: 1px solid #c8d4e3;
            border-radius: 8px;
            padding: 6px 10px;
            min-height: 38px;
            font-size: 15px;
        }
        QMenuBar {
            background-color: #ffffff;
            border-bottom: 1px solid #d7e0eb;
            font-size: 16px;
        }
        QMenuBar::item {
            background: transparent;
            padding: 10px 14px;
        }
        QMenuBar::item:selected {
            background: #e9f1fb;
        }
        QMenu {
            background-color: #ffffff;
            border: 1px solid #d7e0eb;
            font-size: 15px;
        }
        QMenu::item {
            padding: 10px 28px 10px 28px;
        }
        QMenu::item:selected {
            background-color: #e9f1fb;
        }
    """)

    window = CameraApp()
    window.show()
    sys.exit(app.exec_())


