from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QWidget, QPushButton, QStackedWidget, QComboBox, QCheckBox, QSizePolicy, QSlider, QLineEdit, QGraphicsOpacityEffect
from PyQt5.QtCore import QSize, Qt, QTimer, QEvent, QPropertyAnimation, QEasingCurve, QObject, pyqtSignal, QRunnable, QThreadPool
from PyQt5.QtGui import QFontDatabase, QColor, QPalette, QPixmap, QPainter, QIcon
from MetroAPI import MetroAPI, MetroAPIError
from data_handler import DataHandler
from services.config_store import ConfigStore
from services.message_store import MessageStore
from services.settings_server_client import SettingsServerClient
from services.system_service import SystemService
from services.update_service import UpdateService
from views.filters import TouchscreenComboViewFilter
from views.popouts import IPPopout, UpdatePopout, ShutdownPopout
import os
from services.system_actions import start_process
import random
import time
import argparse
from datetime import datetime, timedelta

class PredictionsFetchSignals(QObject):
    success = pyqtSignal(str, int)
    error = pyqtSignal(str, int, str)
    finished = pyqtSignal(int)


class PredictionsFetchWorker(QRunnable):
    def __init__(self, data_handler, station_id, request_id):
        super().__init__()
        self.data_handler = data_handler
        self.station_id = station_id
        self.request_id = request_id
        self.signals = PredictionsFetchSignals()

    def run(self):
        try:
            self.data_handler.fetch_predictions(self.station_id)
            self.signals.success.emit(self.station_id, self.request_id)
        except MetroAPIError as exc:
            self.signals.error.emit(self.station_id, self.request_id, str(exc))
        except Exception as exc:
            self.signals.error.emit(self.station_id, self.request_id, f"Failed to fetch arrivals: {exc}")
        finally:
            self.signals.finished.emit(self.request_id)

class MainWindow(QMainWindow):
    # Metro line color mapping
    LINE_COLORS = {
        'RD': '#BF0D3E',  # Red
        'OR': '#ED8B00',  # Orange
        'YL': '#FFD100',  # Yellow
        'GR': '#00B140',  # Green
        'BL': '#009CDE',  # Blue
        'SV': '#919D9D',  # Silver
    }
    
    def __init__(self, data_handler, config_store, message_store, settings_server, system_service, update_service):
        super().__init__()

        # Load config to get properties
        self.data_handler = data_handler
        self.config_store = config_store
        self.config_store.subscribe(self.on_config_changed)
        self.message_store = message_store
        self.settings_server = settings_server
        self.system_service = system_service
        self.update_service = update_service

        self.default_title_text = self.config_store.get_str('title_text', "Nicole's Train Tracker!")
        self.font_family = self.config_store.get_str('font_family', 'Quicksand')



        # self.setFixedSize(QSize(1024,600))  # Commented out for fullscreen mode
        self.setWindowTitle(self.default_title_text)

        # Hide cursor for touchscreen kiosk mode
        self.setCursor(Qt.BlankCursor)

        # Set window icon to train emoji
        pixmap = QPixmap(128, 128)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
        font = painter.font()
        font.setPointSize(96)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "🚆")
        painter.end()
        self.setWindowIcon(QIcon(pixmap))
        
        # Message display system (initialize before creating pages)
        self.message_config = self.message_store.load()
        self.home_title_label = None  # Will be set in create_home_page
        self.settings_title_label = None  # Will be set in create_settings_page
        self.title_opacity_effect = None
        self.current_fade_animation = None
        self.message_restore_timer = None
        self.message_schedule_timer = None
        self.is_showing_message = False
        self.web_trigger_check_timer = None

        # Create main widget with stacked layout
        self.stack = QStackedWidget()
        
        # Create pages
        self.startup_page = self.create_startup_page()
        self.home_page = self.create_home_page()
        self.settings_page = self.create_settings_page()
        
        # Add pages to stack (startup=0, home=1, settings=2)
        self.stack.addWidget(self.startup_page)
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.settings_page)
        
        # Start on the startup page
        self.stack.setCurrentIndex(0)
        
        self.setCentralWidget(self.stack)
        
        # Error state tracking for refresh countdown (must be initialized before first data load)
        self.refresh_error_message = None
        self.api_thread_pool = QThreadPool()
        self.refresh_in_progress = False
        self.active_station_id = None
        self.pending_station_id = None
        self.pending_refresh_source = None
        self.refresh_request_id = 0
        self.refresh_request_context = {}
        
        # Track which trains are showing actual time (persists across refreshes)
        self.trains_showing_actual_time = []
        
        # Initialize settings with config values
        self.initialize_settings_from_config()
        
        # Load refresh rate from config (needed for timers after initial load)
        self.refresh_rate_seconds = self.config_store.get_int('refresh_rate_seconds', 30)
        
        # Set up auto-refresh timer (will be started after initial load succeeds)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_arrivals)
        
        # Set up countdown timer (will be started after initial load succeeds)
        self.seconds_until_refresh = self.refresh_rate_seconds
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
        
        # Initial load will be triggered after window is shown (see showEvent)
        self.initial_load_triggered = False
        
        # Update button state management
        self.checking_animation_timer = QTimer()
        self.checking_animation_timer.timeout.connect(self.update_checking_animation)
        self.checking_animation_state = 0
        self.update_service.pull_output.connect(self.on_update_service_output)
        self.update_service.pull_finished.connect(self.on_update_service_finished)
        self.update_service.update_available_changed.connect(self.on_update_available_changed)
        
        # Reboot scheduling
        self.reboot_check_timer = QTimer()
        self.reboot_check_timer.timeout.connect(self.check_reboot_schedule)
        self.reboot_check_timer.start(1000)  # Check every second
        
        self.reboot_countdown_timer = None
        self.reboot_countdown_seconds = 0
        self.reboot_scheduled_for_today = False  # Track if we already triggered reboot today
        
        # API key detection for retry after web interface adds key
        self.waiting_for_api_key = False
        self.api_key_check_timer = QTimer()
        self.api_key_check_timer.timeout.connect(self.check_for_api_key)
        
        # Background update check
        self.update_check_timer = QTimer()
        self.update_check_timer.timeout.connect(self.update_service.check_for_updates)
        # Load interval from config and start timer
        self.update_check_interval_seconds = self.config_store.get_int('update_check_interval_seconds', 60)
        self.update_check_timer.start(self.update_check_interval_seconds * 1000)
    
    def showEvent(self, event):
        """Called when the window is shown - trigger initial API load"""
        super().showEvent(event)
        # Only trigger once (showEvent can be called multiple times)
        if not self.initial_load_triggered:
            self.initial_load_triggered = True
            print("Window shown at time:", datetime.now().strftime("%H:%M:%S"))
            # Show a brief loading state while UI finishes drawing
            self.startup_status_label.setText("Loading Visuals...")
            self.startup_status_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #666;")
            # Now start the delay, then check WiFi first
            QTimer.singleShot(1000, self.check_wifi_and_load)
    
    def check_wifi_and_load(self):
        """Check WiFi connection before attempting API load."""
        self.startup_status_label.setText("Checking WiFi connection...")
        self.startup_status_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #666;")
        
        if not self.check_wifi_connection():
            # No WiFi connection - show error and WiFi setup buttons
            self.startup_status_label.setText("WiFi connection not configured. Launch network setup?")
            self.startup_status_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #cc0000;")
            # Show WiFi-specific buttons
            self.startup_wifi_buttons_container.show()
            return
        
        # WiFi connected - proceed to normal API load
        self.perform_initial_load()

    
    def eventFilter(self, obj, event):
        """Event filter to handle hover events on IP button and clicks outside shutdown popout"""
        if obj == self.ip_button:
            if event.type() == QEvent.Enter:
                self.show_ip_popout()
            elif event.type() == QEvent.Leave:
                if hasattr(self, 'ip_popout'):
                    self.ip_popout.hide()
        
        # Handle clicks outside the shutdown popout
        if event.type() == QEvent.MouseButtonPress:
            if hasattr(self, 'shutdown_popout') and self.shutdown_popout.isVisible():
                # Check if click is outside both the popout and the button
                click_pos = event.globalPos()
                popout_rect = self.shutdown_popout.geometry()
                popout_rect.moveTopLeft(self.shutdown_popout.mapToGlobal(self.shutdown_popout.rect().topLeft()))
                
                button_rect = self.shutdown_exit_button.geometry()
                button_rect.moveTopLeft(self.shutdown_exit_button.mapToGlobal(self.shutdown_exit_button.rect().topLeft()))
                
                if not popout_rect.contains(click_pos) and not button_rect.contains(click_pos):
                    self.close_shutdown_popout()
        
        return super().eventFilter(obj, event)
    
    def perform_initial_load(self):
        """Perform initial API data load after window is shown"""
        # Switch subtitle when we actually begin the API call
        self.startup_status_label.setText("Connecting to Metro API...")
        self.startup_status_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #666;")

        api_key = self.config_store.get_str('api_key')
        if not api_key:
            # Stay on startup page and prompt user to add API key
            message = "API Key Missing. Add it by visiting nicoletrains.local"
            self.startup_status_label.setText(message)
            self.startup_status_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #cc0000;")
            # Start checking for API key to be added
            self.waiting_for_api_key = True
            self.api_key_check_timer.start(2000)  # Check every 2 seconds
            return

        # Stop API key check timer if it was running
        self.waiting_for_api_key = False
        self.api_key_check_timer.stop()

        station_id = self.config_store.get_str('selected_station')
        if not station_id:
            self.update_arrivals_display()
            self.enter_home_page()
            return

        self.startup_status_label.setText("Loading arrivals...")
        self.queue_predictions_refresh(station_id, source="startup")

    def enter_home_page(self):
        """Switch to the home page and start refresh timers."""
        print("Switching to main schedule page at time:", datetime.now().strftime("%H:%M:%S"))
        self.stack.setCurrentIndex(1)  # Home page
        self.refresh_timer.start(self.refresh_rate_seconds * 1000)
        self.countdown_timer.start(1000)

    def queue_predictions_refresh(self, station_id, source):
        if not station_id:
            self.refresh_error_message = None
            self.update_arrivals_display()
            if source == "startup":
                self.enter_home_page()
            return

        if self.refresh_in_progress:
            if station_id != self.active_station_id:
                self.pending_station_id = station_id
                self.pending_refresh_source = source
            return

        self.refresh_in_progress = True
        self.pending_station_id = None
        self.pending_refresh_source = None
        self.refresh_request_id += 1
        request_id = self.refresh_request_id
        self.refresh_request_context[request_id] = source
        self.active_station_id = station_id

        worker = PredictionsFetchWorker(self.data_handler, station_id, request_id)
        worker.signals.success.connect(self.on_predictions_fetch_success)
        worker.signals.error.connect(self.on_predictions_fetch_error)
        worker.signals.finished.connect(self.on_predictions_fetch_finished)
        self.api_thread_pool.start(worker)

    def on_predictions_fetch_success(self, station_id, request_id):
        source = self.refresh_request_context.get(request_id)
        current_station_id = self.config_store.get_str('selected_station')
        if station_id != current_station_id and source != "startup":
            return
        self.refresh_error_message = None
        self.update_arrivals_display()
        if source == "startup":
            self.enter_home_page()

    def on_predictions_fetch_error(self, station_id, request_id, message):
        source = self.refresh_request_context.get(request_id)
        current_station_id = self.config_store.get_str('selected_station')
        if station_id != current_station_id and source != "startup":
            return
        self.refresh_error_message = message
        if source == "startup":
            self.startup_status_label.setText(message)
            self.startup_status_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #cc0000;")
            self.startup_buttons_container.show()
            return
        self.update_arrivals_display()

    def on_predictions_fetch_finished(self, request_id):
        self.refresh_in_progress = False
        self.active_station_id = None
        self.refresh_request_context.pop(request_id, None)
        if self.pending_station_id:
            pending_station_id = self.pending_station_id
            pending_source = self.pending_refresh_source or "refresh"
            self.pending_station_id = None
            self.pending_refresh_source = None
            self.queue_predictions_refresh(pending_station_id, pending_source)
    
    def check_for_api_key(self):
        """Check if API key has been added via web interface and retry initial load"""
        if not self.waiting_for_api_key:
            return
        
        api_key = self.config_store.get_str('api_key')
        
        if api_key:
            if hasattr(self.data_handler, 'metro_api'):
                self.data_handler.metro_api.api_key = api_key
            
            # API key has been added, reset status label and retry
            self.waiting_for_api_key = False
            self.api_key_check_timer.stop()
            
            # Reset status label to original state
            self.startup_status_label.setText("Connecting to Metro API...")
            self.startup_status_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #666;")
            
            # Retry the initial load
            self.perform_initial_load()
    
    def check_wifi_connection(self):
        """Check if WiFi is connected using NetworkManager.
        
        Returns:
            bool: True if connected to a WiFi network, False otherwise
        """
        return self.system_service.check_wifi_connection()
    
    def launch_wifi_setup(self):
        """Launch the WiFi setup application and terminate main display."""
        try:
            # Get the directory of this script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            wifi_setup_script = os.path.join(script_dir, "wifi_setup.py")
            
            # Launch wifi_setup.py with fullscreen argument
            start_process(
                ["python3", wifi_setup_script, "--fullscreen"],
                cwd=script_dir,
                log_label="launch_wifi_setup",
                timeout_s=None,
            )
            
            # Terminate this application
            QApplication.instance().quit()
        except Exception as e:
            print(f"Error launching WiFi setup: {e}")
            self.startup_status_label.setText(f"Failed to launch WiFi setup: {e}")
            self.startup_status_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #cc0000;")
    
    def get_device_ip(self):
        """Get the local IP address of the device"""
        return self.system_service.get_device_ip()
    
    def get_tailscale_address(self):
        """Get the Tailscale address of the device"""
        return self.system_service.get_tailscale_address()
    
    def create_colored_circle_icon(self, color_hex):
        """Create a colored circle icon for dropdown items"""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(color_hex))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        
        return QIcon(pixmap)
    
    def create_multi_colored_circle_icon(self, color_list):
        """Create an icon with multiple overlapping colored circles for dropdown items"""
        if not color_list:
            return self.create_colored_circle_icon('#808080')
        
        if len(color_list) == 1:
            return self.create_colored_circle_icon(color_list[0])
        
        # Calculate width: base circle (16px) + overlap offset for additional circles
        overlap_offset = 10  # How much each circle overlaps
        width = 16 + (len(color_list) - 1) * overlap_offset
        height = 16
        
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        
        # Draw circles from right to left so the first one appears on top
        for i in range(len(color_list) - 1, -1, -1):
            color = color_list[i]
            x_offset = i * overlap_offset
            painter.setBrush(QColor(color))
            painter.drawEllipse(x_offset + 2, 2, 12, 12)
        
        painter.end()
        
        return QIcon(pixmap)
    
    def configure_combo_for_touchscreen(self, combo_box):
        """Configure a QComboBox for touchscreen use by installing an event filter on its view"""
        # Create and store the event filter
        if not hasattr(self, '_combo_filters'):
            self._combo_filters = {}
        
        filter_obj = TouchscreenComboViewFilter(combo_box)
        self._combo_filters[combo_box] = filter_obj
        
        # Override showPopup to install the filter on the view when it opens
        original_show_popup = combo_box.showPopup
        
        def show_popup_wrapper():
            original_show_popup()
            # Install the filter on the view after the popup is shown
            view = combo_box.view()
            if view:
                view.installEventFilter(filter_obj)
        
        combo_box.showPopup = show_popup_wrapper
    
    def open_settings_page(self):
        """Open settings page and reload values from config"""
        # Reload dropdowns from config (now using cache, so it's fast)
        self.initialize_settings_from_config()
        # Switch to settings page
        self.stack.setCurrentIndex(2)
    
    def close_settings_page(self):
        """Close settings page"""
        # Just switch to home page
        self.stack.setCurrentIndex(1)
    
    def on_line_selected(self, index):
        """Handle line selection change"""
        if index >= 0:
            line_code = self.line_combo.itemData(index)
            self.populate_stations(line_code)
    
    def on_station_selected(self, index):
        """Handle station selection change"""
        if index >= 0:
            station_code = self.station_combo.itemData(index)
            self.populate_directions(station_code)
    
    def on_destination_selected(self, index):
        """Handle destination selection change"""
        # Destination selection doesn't trigger any cascading updates
        pass
    
    def populate_stations(self, line_code):
        """Populate station dropdown based on selected line"""
        # Clear current stations and destinations
        self.station_combo.clear()
        self.destination_combo.clear()
        
        if not line_code:
            return
        
        # Get stations for the selected line (uses cache, auto-fetches if needed)
        try:
            stations_data = self.data_handler.get_cached_stations(line_code)
            if stations_data is not None and not stations_data.empty:
                # Add stations to combo box
                for _, station in stations_data.iterrows():
                    station_name = station.get('Name', '')
                    station_code = station.get('Code', '')
                    self.station_combo.addItem(station_name, station_code)
        except MetroAPIError as e:
            # Store error for display in countdown
            self.refresh_error_message = str(e)
    
    def populate_directions(self, station_code):
        """Populate destination dropdown with unique destinations from station predictions"""
        # Clear current destinations
        self.destination_combo.clear()
        
        if not station_code:
            return
        
        # Get predictions for the selected station (uses cache, auto-fetches if needed)
        try:
            predictions_data = self.data_handler.get_cached_predictions(station_code)
            if predictions_data is not None and not predictions_data.empty:
                # Create a dictionary to map destinations to lists of their line codes
                destination_lines = {}
                for _, row in predictions_data.iterrows():
                    dest = row.get('DestinationName')
                    line = row.get('Line')
                    if dest and line:
                        if dest not in destination_lines:
                            destination_lines[dest] = []
                        # Add line code if not already in the list (avoid duplicates)
                        if line not in destination_lines[dest]:
                            destination_lines[dest].append(line)
                
                # Sort destinations alphabetically
                destinations = sorted(destination_lines.keys())
                
                # Add destinations to combo box with colored icons
                for destination in destinations:
                    line_codes = destination_lines[destination]
                    # Get colors for all line codes
                    colors = [self.LINE_COLORS.get(code, '#808080') for code in line_codes]
                    
                    # Use appropriate icon based on number of lines
                    if len(colors) == 1:
                        icon = self.create_colored_circle_icon(colors[0])
                    else:
                        icon = self.create_multi_colored_circle_icon(colors)
                    
                    self.destination_combo.addItem(icon, destination)
        except MetroAPIError as e:
            # Store error for display in countdown
            self.refresh_error_message = str(e)
    
    def get_destination_direction(self, destination_name, destination_line):
        """
        Determine the direction of a destination relative to the current station.
        
        Args:
            destination_name: Name of the destination station
            destination_line: Line code of the destination (e.g., 'RD', 'SV')
        
        Returns:
            'forward' if destination is ahead on the line, 'backward' if behind, or None if can't determine
        """
        try:
            # Get current station code from config
            config = self.config_store.load()
            current_station_code = config.get('selected_station')
            if not current_station_code:
                return None
            
            # Get all stations for the destination's line
            stations_data = self.data_handler.get_cached_stations(destination_line)
            if stations_data is None or stations_data.empty:
                return None
            
            # Find positions of current and destination stations
            current_position = None
            destination_position = None
            
            for idx, station in stations_data.iterrows():
                station_code = station.get('Code', '')
                station_name = station.get('Name', '')
                
                if station_code == current_station_code:
                    current_position = idx
                if station_name == destination_name:
                    destination_position = idx
            
            # If both positions found, compare them
            if current_position is not None and destination_position is not None:
                if destination_position > current_position:
                    return 'forward'
                elif destination_position < current_position:
                    return 'backward'
                else:
                    # Same station - treat as forward by default
                    return 'forward'
            
            return None
            
        except Exception:
            return None
    
    def get_config_last_saved(self):
        """Get the last modified timestamp of the config file"""
        config_path = self.config_store.path
        if os.path.exists(config_path):
            mtime = os.path.getmtime(config_path)
            dt = datetime.fromtimestamp(mtime)
            return dt.strftime("%m/%d/%Y %I:%M:%S %p")
        return "Never"
    
    def update_timestamp_label(self):
        """Update the timestamp label with current file modification time"""
        timestamp = self.get_config_last_saved()
        self.timestamp_label.setText(f"Last saved: {timestamp}")
    
    def mark_settings_changed(self):
        """Show warning label when settings are changed"""
        self.unsaved_warning_label.show()
    
    def on_filter_by_destination_changed(self, state):
        """Handle filter by destination checkbox state change"""
        if state == Qt.Checked:
            # Uncheck the other filter if it's checked
            if self.filter_by_destination_direction_checkbox.isChecked():
                self.filter_by_destination_direction_checkbox.blockSignals(True)
                self.filter_by_destination_direction_checkbox.setChecked(False)
                self.filter_by_destination_direction_checkbox.blockSignals(False)
    
    def on_filter_by_direction_changed(self, state):
        """Handle filter by destination direction checkbox state change"""
        if state == Qt.Checked:
            # Uncheck the other filter if it's checked
            if self.filter_by_destination_checkbox.isChecked():
                self.filter_by_destination_checkbox.blockSignals(True)
                self.filter_by_destination_checkbox.setChecked(False)
                self.filter_by_destination_checkbox.blockSignals(False)
    
    def save_settings(self):
        """Manually save current settings to config file"""
        updates = {}
        current_index = self.line_combo.currentIndex()
        if current_index >= 0:
            line_code = self.line_combo.itemData(current_index)
            updates['selected_line'] = line_code
        
        station_index = self.station_combo.currentIndex()
        if station_index >= 0:
            station_code = self.station_combo.itemData(station_index)
            updates['selected_station'] = station_code
        
        destination_index = self.destination_combo.currentIndex()
        if destination_index >= 0:
            destination = self.destination_combo.currentText()
            updates['selected_destination'] = destination
        
        # Save countdown visibility setting
        updates['show_countdown'] = self.show_countdown_checkbox.isChecked()
        
        # Save clock visibility setting
        updates['show_clock'] = self.show_clock_checkbox.isChecked()
        
        # Save filter by selected destination setting
        updates['filter_by_direction'] = self.filter_by_destination_checkbox.isChecked()
        
        # Save filter by destination direction setting
        updates['filter_by_destination_direction'] = self.filter_by_destination_direction_checkbox.isChecked()
        
        # Save screen sleep settings
        updates['screen_sleep_enabled'] = self.screen_sleep_enabled_checkbox.isChecked()
        updates['screen_sleep_minutes'] = self.screen_sleep_slider.value()

        if updates:
            self.config_store.set_values(updates)
        
        # Apply screen sleep settings to system
        self.apply_screen_sleep_settings()
        
        # Update the timestamp label
        self.update_timestamp_label()
        
        # Hide unsaved changes warning
        self.unsaved_warning_label.hide()
        
        # Refresh arrivals display with new settings
        self.refresh_arrivals()
    
    def initialize_settings_from_config(self):
        """Initialize all settings dropdowns with values from config"""
        
        # Clear all dropdowns first
        self.line_combo.clear()
        self.station_combo.clear()
        self.destination_combo.clear()
        
        # Load config
        config = self.config_store.load()
        
        # Load and apply countdown visibility setting
        show_countdown = config.get('show_countdown', True)  # Default to True
        self.show_countdown_checkbox.setChecked(show_countdown)
        if show_countdown:
            self.refresh_countdown_label.show()
        else:
            self.refresh_countdown_label.hide()
        
        # Load and apply clock visibility setting
        show_clock = config.get('show_clock', True)  # Default to True
        self.show_clock_checkbox.setChecked(show_clock)
        if hasattr(self, 'clock_label'):
            self.clock_label.setVisible(show_clock)
        
        # Load and apply filter by selected destination setting
        filter_by_direction = config.get('filter_by_direction', False)  # Default to False (show all)
        filter_by_destination_direction = config.get('filter_by_destination_direction', False)  # Default to False (show all)
        
        # Ensure only one filter is checked (prioritize filter_by_direction if both are true)
        if filter_by_direction and filter_by_destination_direction:
            filter_by_destination_direction = False
        
        self.filter_by_destination_checkbox.setChecked(filter_by_direction)
        self.filter_by_destination_direction_checkbox.setChecked(filter_by_destination_direction)
        
        # Load and apply screen sleep settings
        screen_sleep_enabled = config.get('screen_sleep_enabled', False)
        self.screen_sleep_enabled_checkbox.setChecked(screen_sleep_enabled)
        
        screen_sleep_minutes = config.get('screen_sleep_minutes', 5)
        self.screen_sleep_slider.setValue(screen_sleep_minutes)
        self.update_screen_sleep_label()
        
        # Apply screen sleep settings to system on startup
        self.apply_screen_sleep_settings()

        # Populate lines
        lines_data = self.data_handler.get_cached_lines()

        if lines_data is not None and not lines_data.empty:
            for _, line in lines_data.iterrows():
                display_name = line.get('DisplayName', '')
                self.line_combo.addItem(display_name, line.get('LineCode', ''))

            # Set line from config
            selected_line = config.get('selected_line')
            if selected_line:
                index = self.line_combo.findData(selected_line)
                if index >= 0:
                    self.line_combo.setCurrentIndex(index)
                    # Manually populate stations for this line
                    self.populate_stations(selected_line)
                    
                    # Set station from config
                    selected_station = config.get('selected_station')
                    if selected_station:
                        station_index = self.station_combo.findData(selected_station)
                        if station_index >= 0:
                            self.station_combo.setCurrentIndex(station_index)
                            # Manually populate directions for this station
                            self.populate_directions(selected_station)
                            
                            # Set destination from config
                            selected_destination = config.get('selected_destination')
                            if selected_destination:
                                destination_index = self.destination_combo.findText(selected_destination)
                                if destination_index >= 0:
                                    self.destination_combo.setCurrentIndex(destination_index)
        
        # Hide unsaved warning after initialization (signals may have triggered it)
        self.unsaved_warning_label.hide()


    
    def create_arrival_row(self, index):
        """Create a single arrival row widget"""
        row = QWidget()
        
        # Alternating background colors - slightly darker for odd rows
        bg_color = "#ffffff" if index % 2 == 0 else "#f5f5f5"
        row.setStyleSheet(f"background-color: {bg_color};")
        row.setFixedHeight(95)
        row.setCursor(Qt.PointingHandCursor)  # Show pointer cursor on hover
        
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(25, 15, 25, 15)
        row_layout.setSpacing(20)
        
        # Colored circle on the left
        circle_label = QLabel()
        circle_label.setFixedSize(20, 20)
        circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
        row_layout.addWidget(circle_label, alignment=Qt.AlignVCenter)
        
        # Destination label in the center
        destination_label = QLabel("—")
        destination_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 28px; font-weight: bold;")
        row_layout.addWidget(destination_label, alignment=Qt.AlignVCenter)
        row_layout.addStretch()
        
        # Arrival time on the right
        time_label = QLabel("—")
        time_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 28px; font-weight: bold;")
        row_layout.addWidget(time_label, alignment=Qt.AlignVCenter)
        
        row.setLayout(row_layout)
        
        # Store references to labels for easy updating
        row.circle_label = circle_label
        row.destination_label = destination_label
        row.time_label = time_label
        row.row_index = index
        row.base_color = bg_color  # Store base color for press effect
        row.prediction_signature = None
        row.prediction_arrival_minutes = None
        
        # Make row clickable with press effect
        row.mousePressEvent = lambda event: self.on_arrival_row_pressed(index)
        row.mouseReleaseEvent = lambda event: self.on_arrival_row_released(index)
        
        return row
    
    def on_arrival_row_pressed(self, index):
        """Handle mouse press on arrival row - show darker color"""
        row = self.arrival_rows[index]
        # Apply pressed color (slightly darker)
        pressed_color = "#e8e8e8" if index % 2 == 0 else "#e0e0e0"
        row.setStyleSheet(f"background-color: {pressed_color};")
    
    def on_arrival_row_released(self, index):
        """Handle mouse release on arrival row - toggle time display and restore color"""
        row = self.arrival_rows[index]
        
        # Don't toggle if the row is empty (showing "—")
        if row.time_label.text() == "—" or not row.prediction_signature or row.prediction_arrival_minutes is None:
            # Restore base color but don't toggle anything
            base_color = "#ffffff" if index % 2 == 0 else "#f5f5f5"
            row.setStyleSheet(f"background-color: {base_color};")
            return
        
        # Toggle the time display state
        matching_index = self.find_matching_toggle_index(
            row.prediction_signature,
            row.prediction_arrival_minutes
        )
        if matching_index is not None:
            # Row is currently showing actual time, toggle it off
            del self.trains_showing_actual_time[matching_index]
        else:
            # Row is not showing actual time, toggle it on
            self.trains_showing_actual_time.append(
                (row.prediction_signature, row.prediction_arrival_minutes)
            )
        
        # Restore base color
        base_color = "#ffffff" if index % 2 == 0 else "#f5f5f5"
        row.setStyleSheet(f"background-color: {base_color};")
        
        # Refresh display to show updated format
        self.update_arrivals_display()
    
    def calculate_actual_time(self, min_value):
        """Calculate the actual arrival time given minutes until arrival"""
        arrival_time = self.calculate_actual_datetime(min_value)
        if not arrival_time:
            return None

        # Format as 12-hour time with AM/PM, remove leading zero
        return arrival_time.strftime("%I:%M %p").lstrip('0')

    def calculate_actual_datetime(self, min_value):
        """Calculate the actual arrival datetime given minutes until arrival."""
        # Handle special cases that shouldn't show actual time
        if min_value in ['ARR', 'BRD', '—']:
            return None
        
        # Try to convert to integer
        try:
            if isinstance(min_value, str):
                minutes = int(min_value)
            else:
                minutes = int(min_value)
        except (ValueError, TypeError):
            return None
        
        # Calculate actual arrival time
        now = datetime.now()
        return now + timedelta(minutes=minutes)

    def arrival_time_to_minutes(self, arrival_time):
        """Convert an arrival datetime to minutes since midnight."""
        if not arrival_time:
            return None
        return (arrival_time.hour * 60) + arrival_time.minute

    def arrival_minutes_within_tolerance(self, minutes_a, minutes_b, tolerance=1):
        """Return True if two minute-of-day values are within tolerance."""
        if minutes_a is None or minutes_b is None:
            return False
        diff = abs(minutes_a - minutes_b)
        diff = min(diff, 1440 - diff)
        return diff <= tolerance

    def normalize_prediction_value(self, value):
        """Normalize prediction values for stable key creation."""
        if value is None:
            return ''
        try:
            if value != value:
                return ''
        except Exception:
            return ''
        return str(value)

    def build_prediction_signature(self, prediction):
        """Build a stable signature for a prediction to track it across refreshes."""
        location_code = self.normalize_prediction_value(prediction.get('LocationCode'))
        line = self.normalize_prediction_value(prediction.get('Line'))
        group = self.normalize_prediction_value(prediction.get('Group'))
        car = self.normalize_prediction_value(prediction.get('Car'))

        signature = (location_code, line, group, car)
        if not any(signature):
            return None
        return signature

    def find_matching_toggle_index(self, signature, arrival_minutes):
        """Find the index of a matching toggle using arrival-time tolerance."""
        for idx, (toggle_signature, toggle_minutes) in enumerate(self.trains_showing_actual_time):
            if signature != toggle_signature:
                continue
            if self.arrival_minutes_within_tolerance(arrival_minutes, toggle_minutes):
                return idx
        return None

    def is_toggle_active(self, signature, arrival_minutes):
        """Return True if a toggle matches the signature and arrival time."""
        return self.find_matching_toggle_index(signature, arrival_minutes) is not None
    
    def update_arrivals_display(self):
        """Update the arrivals display with latest prediction data"""
        # Get selected station from config
        config = self.config_store.load()
        station_id = config.get('selected_station')
        
        if not station_id:
            # No station configured, show empty rows
            for row in self.arrival_rows:
                row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                row.destination_label.setText("—")
                row.time_label.setText("—")
            self.trains_showing_actual_time.clear()
            return
        
        # Get cached predictions for the selected station
        predictions_data = self.data_handler.get_predictions_cache(station_id)
        
        if predictions_data is None or predictions_data.empty:
            # No data available, show empty rows
            empty_text = "—" if self.refresh_error_message else "No arrivals"
            for row in self.arrival_rows:
                row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                row.destination_label.setText(empty_text)
                row.time_label.setText("—")
            self.trains_showing_actual_time.clear()
            return
        
        # Apply filtering if enabled (use config flag to reflect remote changes)
        if config.get('filter_by_direction', False):
            selected_destination = config.get('selected_destination')
            if selected_destination:
                # Filter to only show arrivals matching the selected destination
                predictions_data = predictions_data[predictions_data['DestinationName'] == selected_destination]
                
                # Check if any predictions remain after filtering
                if predictions_data.empty:
                    # No arrivals for selected destination
                    for row in self.arrival_rows:
                        row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                        row.destination_label.setText("No arrivals")
                        row.time_label.setText("—")
                    self.trains_showing_actual_time.clear()
                    return
        
        # Apply direction-based filtering if enabled
        if config.get('filter_by_destination_direction', False):
            selected_destination = config.get('selected_destination')
            if selected_destination:
                # Find the direction of the selected destination
                # We need to get the line for the selected destination from predictions
                selected_direction = None
                selected_destination_line = None
                
                # First, find which line the selected destination is on
                for _, pred_row in predictions_data.iterrows():
                    if pred_row.get('DestinationName') == selected_destination:
                        selected_destination_line = pred_row.get('Line')
                        break
                
                # Determine the direction of the selected destination
                if selected_destination_line:
                    selected_direction = self.get_destination_direction(selected_destination, selected_destination_line)
                
                # If we have a direction, filter predictions to only show trains going in that direction
                if selected_direction:
                    # Create a mask for filtering
                    mask = []
                    for _, pred_row in predictions_data.iterrows():
                        dest_name = pred_row.get('DestinationName')
                        dest_line = pred_row.get('Line')
                        if dest_name and dest_line:
                            dest_direction = self.get_destination_direction(dest_name, dest_line)
                            mask.append(dest_direction == selected_direction)
                        else:
                            mask.append(False)
                    
                    # Apply the mask to filter the DataFrame
                    predictions_data = predictions_data[mask].copy()
                
                # Check if any predictions remain after filtering
                if predictions_data.empty:
                    # No arrivals in the selected direction
                    for row in self.arrival_rows:
                        row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                        row.destination_label.setText("No arrivals")
                        row.time_label.setText("—")
                    self.trains_showing_actual_time.clear()
                    return
        
        # Sort predictions by arrival time (Min field)
        # Need to handle special values like 'ARR', 'BRD', etc.
        def sort_key(row_data):
            min_val = row_data.get('Min', '')
            if isinstance(min_val, str):
                # Special values should come first
                if min_val in ['ARR', 'BRD']:
                    return -1
                try:
                    return int(min_val)
                except ValueError:
                    return 999  # Unknown values go last
            return min_val if isinstance(min_val, (int, float)) else 999
        
        sorted_predictions = sorted(
            [row for _, row in predictions_data.iterrows()],
            key=sort_key
        )
        
        # Update each arrival row
        visible_predictions = []
        for i, row in enumerate(self.arrival_rows):
            if i < len(sorted_predictions):
                prediction = sorted_predictions[i]
                prediction_signature = self.build_prediction_signature(prediction)
                actual_datetime = self.calculate_actual_datetime(prediction.get('Min'))
                arrival_minutes = self.arrival_time_to_minutes(actual_datetime)
                row.prediction_signature = prediction_signature
                row.prediction_arrival_minutes = arrival_minutes
                if prediction_signature and arrival_minutes is not None:
                    visible_predictions.append((prediction_signature, arrival_minutes))
                
                # Update row background to base color
                base_color = "#ffffff" if i % 2 == 0 else "#f5f5f5"
                row.setStyleSheet(f"background-color: {base_color};")
                
                # Update line color
                line_code = prediction.get('Line', '')
                color = self.LINE_COLORS.get(line_code, '#cccccc')
                row.circle_label.setStyleSheet(f"background-color: {color}; border-radius: 10px;")
                
                # Update destination
                destination = prediction.get('DestinationName', 'Unknown')
                row.destination_label.setText(destination)
                
                # Update arrival time
                min_val = prediction.get('Min', '')
                if min_val in ['ARR', 'BRD']:
                    time_text = min_val
                elif isinstance(min_val, (int, float)) or (isinstance(min_val, str) and min_val.isdigit()):
                    time_text = f"{min_val} min"
                    # Add actual time if this row is clicked
                    if prediction_signature and self.is_toggle_active(
                        prediction_signature,
                        arrival_minutes
                    ):
                        actual_time = self.calculate_actual_time(min_val)
                        if actual_time:
                            time_text = f"{actual_time} • {min_val} min"
                else:
                    time_text = str(min_val)
                row.time_label.setText(time_text)
            else:
                # No more predictions, show empty row
                base_color = "#ffffff" if i % 2 == 0 else "#f5f5f5"
                row.setStyleSheet(f"background-color: {base_color};")
                row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                row.destination_label.setText("—")
                row.time_label.setText("—")
                row.prediction_signature = None
                row.prediction_arrival_minutes = None

        # Remove toggles for trains no longer visible
        self.trains_showing_actual_time = [
            (toggle_signature, toggle_minutes)
            for toggle_signature, toggle_minutes in self.trains_showing_actual_time
            if any(
                toggle_signature == visible_signature
                and self.arrival_minutes_within_tolerance(toggle_minutes, visible_minutes)
                for visible_signature, visible_minutes in visible_predictions
            )
        ]
    
    def refresh_arrivals(self):
        """Refresh arrivals data from API and update display"""
        # Sync settings from config so web changes apply promptly
        config = self.config_store.refresh_if_changed()
        # Get selected station from config
        station_id = config.get('selected_station')
        
        if station_id:
            self.queue_predictions_refresh(station_id, source="refresh")
        else:
            self.refresh_error_message = None
            self.update_arrivals_display()
        
        # Reset countdown to configured refresh rate
        self.seconds_until_refresh = self.refresh_rate_seconds
    
    def format_time_display(self, seconds):
        """Format seconds into user-friendly display string"""
        if seconds < 60:
            return f"{seconds}s"
        else:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds == 0:
                return f"{minutes}m"
            else:
                return f"{minutes}m {remaining_seconds}s"
    
    def update_countdown(self):
        """Update the countdown label"""
        self.seconds_until_refresh -= 1
        
        if self.seconds_until_refresh <= 0:
            self.seconds_until_refresh = self.refresh_rate_seconds
        
        # Format the time display
        time_display = self.format_time_display(self.seconds_until_refresh)
        
        # Update the label text and styling based on error state
        if self.refresh_error_message:
            # Display error message with red background
            self.refresh_countdown_label.setText(
                f"Error Refreshing: {self.refresh_error_message} Trying again in {time_display}"
            )
            self.refresh_countdown_label.setStyleSheet(
                f"font-family: {self.font_family}; font-size: 14px; color: white; background-color: #e74c3c; padding: 5px; border-radius: 3px;"
            )
        else:
            # Normal countdown display
            self.refresh_countdown_label.setText(f"Refresh in {time_display}")
            self.refresh_countdown_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 14px; color: #666;")
    
    def toggle_countdown_visibility(self):
        """Toggle the visibility of the countdown label"""
        if self.show_countdown_checkbox.isChecked():
            self.refresh_countdown_label.show()
        else:
            self.refresh_countdown_label.hide()

    def update_clock(self):
        """Update the centered clock label with current time"""
        now = datetime.now()
        # 12-hour format with AM/PM, remove leading zero on hour
        if hasattr(self, 'clock_label'):
            self.clock_label.setText(now.strftime("%I:%M %p").lstrip('0'))

    def toggle_clock_visibility(self):
        """Toggle the visibility of the centered clock label"""
        if hasattr(self, 'clock_label') and hasattr(self, 'show_clock_checkbox'):
            self.clock_label.setVisible(self.show_clock_checkbox.isChecked())
    
    def sync_settings_from_config(self, config=None, changed_keys=None):
        """Sync checkbox and screen sleep settings from config file."""
        config = config or self.config_store.load()

        def should_update(*keys):
            if changed_keys is None:
                return True
            return any(key in changed_keys for key in keys)

        # Update title text
        if should_update('title_text'):
            new_title_text = config.get('title_text', "Nicole's Train Tracker!")
            if new_title_text != self.default_title_text:
                self.default_title_text = new_title_text
                self.setWindowTitle(self.default_title_text)
                # Update the home page title label if it exists and we're not showing a message
                if hasattr(self, 'home_title_label') and self.home_title_label and not self.is_showing_message:
                    self.home_title_label.setText(self.default_title_text)
                # Update the settings page title label if it exists
                if hasattr(self, 'settings_title_label') and self.settings_title_label:
                    self.settings_title_label.setText(self.default_title_text)
        # Show countdown
        if should_update('show_countdown') and hasattr(self, 'show_countdown_checkbox'):
            self.show_countdown_checkbox.blockSignals(True)
            self.show_countdown_checkbox.setChecked(config.get('show_countdown', True))
            self.show_countdown_checkbox.blockSignals(False)
            self.toggle_countdown_visibility()
        # Show clock
        if should_update('show_clock') and hasattr(self, 'show_clock_checkbox'):
            self.show_clock_checkbox.blockSignals(True)
            self.show_clock_checkbox.setChecked(config.get('show_clock', True))
            self.show_clock_checkbox.blockSignals(False)
            self.toggle_clock_visibility()
        # Filter by selected destination and direction (mutually exclusive)
        if should_update('filter_by_direction', 'filter_by_destination_direction'):
            if hasattr(self, 'filter_by_destination_checkbox') and hasattr(self, 'filter_by_destination_direction_checkbox'):
                filter_by_direction = config.get('filter_by_direction', False)
                filter_by_destination_direction = config.get('filter_by_destination_direction', False)

                # Ensure only one filter is checked (prioritize filter_by_direction if both are true)
                if filter_by_direction and filter_by_destination_direction:
                    filter_by_destination_direction = False

                self.filter_by_destination_checkbox.blockSignals(True)
                self.filter_by_destination_checkbox.setChecked(filter_by_direction)
                self.filter_by_destination_checkbox.blockSignals(False)

                self.filter_by_destination_direction_checkbox.blockSignals(True)
                self.filter_by_destination_direction_checkbox.setChecked(filter_by_destination_direction)
                self.filter_by_destination_direction_checkbox.blockSignals(False)
        # Screen sleep
        screen_sleep_changed = should_update('screen_sleep_enabled', 'screen_sleep_minutes')
        if screen_sleep_changed:
            if hasattr(self, 'screen_sleep_enabled_checkbox'):
                self.screen_sleep_enabled_checkbox.blockSignals(True)
                self.screen_sleep_enabled_checkbox.setChecked(config.get('screen_sleep_enabled', False))
                self.screen_sleep_enabled_checkbox.blockSignals(False)
            if hasattr(self, 'screen_sleep_slider') and 'screen_sleep_minutes' in config:
                self.screen_sleep_slider.blockSignals(True)
                self.screen_sleep_slider.setValue(int(config.get('screen_sleep_minutes', 5)))
                self.screen_sleep_slider.blockSignals(False)
                self.update_screen_sleep_label()
            # Apply to system if needed
            self.apply_screen_sleep_settings()
        # Refresh rate
        if should_update('refresh_rate_seconds'):
            refresh_rate_seconds = config.get('refresh_rate_seconds', 30)
            if refresh_rate_seconds != self.refresh_rate_seconds:
                self.refresh_rate_seconds = refresh_rate_seconds
                if hasattr(self, 'refresh_timer'):
                    self.refresh_timer.stop()
                    self.refresh_timer.start(refresh_rate_seconds * 1000)  # Convert seconds to milliseconds
            self.seconds_until_refresh = refresh_rate_seconds
        # API timeout
        if should_update('api_timeout_seconds'):
            timeout_seconds = config.get('api_timeout_seconds', 5)
            if hasattr(self.data_handler, 'metro_api'):
                self.data_handler.metro_api.set_timeout_seconds(timeout_seconds)
        # Background update check interval
        if should_update('update_check_interval_seconds') and hasattr(self, 'update_check_timer'):
            update_interval = config.get('update_check_interval_seconds', 60)
            if update_interval != self.update_check_interval_seconds:
                self.update_check_interval_seconds = update_interval
                self.update_check_timer.stop()
                self.update_check_timer.start(update_interval * 1000)

    def on_config_changed(self, config, changed_keys):
        """Apply config changes to timers and UI when settings change."""
        self.sync_settings_from_config(config=config, changed_keys=changed_keys)
    
    def update_screen_sleep_label(self):
        """Update the screen sleep label to show current slider value"""
        if hasattr(self, 'screen_sleep_slider') and hasattr(self, 'screen_sleep_value_label'):
            minutes = self.screen_sleep_slider.value()
            self.screen_sleep_value_label.setText(f"Screen Sleep Timeout: {minutes} min")
    
    def show_ip_popout(self):
        """Show the IP popout near the IP button"""
        if not hasattr(self, 'ip_popout'):
            ip_address = self.get_device_ip()
            tailscale_address = self.get_tailscale_address()
            self.ip_popout = IPPopout(ip_address, tailscale_address, self.config_store, self.settings_page)
        
        # Position the popout above the IP button
        button_pos = self.ip_button.mapTo(self.settings_page, self.ip_button.rect().topLeft())
        popout_x = button_pos.x()
        popout_y = button_pos.y() - self.ip_popout.height() - 10  # 10px gap above button
        
        self.ip_popout.move(popout_x, popout_y)
        self.ip_popout.show()
        # Raise IP popout above update popout
        self.ip_popout.raise_()
    
    def on_ip_button_hover(self, event):
        """Handle hover event on IP button"""
        self.show_ip_popout()
        return False  # Let the event propagate
    
    def on_update_button_clicked(self):
        """Handle Update button click"""
        button_text = self.update_button.text()
        
        if button_text == "Update":
            # Start the update process
            self.show_update_popout()
            self.start_update_pull()
        elif button_text == "Reboot":
            # Reboot the system
            self.reboot_application()
        elif button_text.startswith("Checking"):
            # Already checking, do nothing
            pass
        elif button_text == "Up to date!":
            # Do nothing, user should close popout
            pass
        elif button_text == "Error Updating":
            # Do nothing, user should close popout
            pass
    
    def show_update_popout(self):
        """Show the update popout near the Update button"""
        if not hasattr(self, 'update_popout'):
            self.update_popout = UpdatePopout(self.config_store, self.settings_page)
            self.update_popout.close_button.clicked.connect(self.close_update_popout)
        
        # Clear previous output
        self.update_popout.clear_output()
        
        # Position the popout above the Update button
        button_pos = self.update_button.mapTo(self.settings_page, self.update_button.rect().topLeft())
        button_right = self.update_button.mapTo(self.settings_page, self.update_button.rect().topRight())
        
        # Default: align left edge of popout with left edge of button
        popout_x = button_pos.x()
        
        # Check if popout would extend past the right edge of the settings page
        popout_right_edge = popout_x + self.update_popout.width()
        page_width = self.settings_page.width()
        
        if popout_right_edge > page_width - 20:  # 20px margin from edge
            # Shift the popout left so its right edge aligns with button's right edge
            popout_x = button_right.x() - self.update_popout.width()
        
        popout_y = button_pos.y() - self.update_popout.height() - 10  # 10px gap above button
        
        self.update_popout.move(popout_x, popout_y)
        self.update_popout.show()
    
    def close_update_popout(self):
        """Close the update popout and reset state"""
        self.update_service.cancel_pull()
        
        # Stop animation timer
        self.checking_animation_timer.stop()
        
        # Reset button text and color
        self.update_button.setText("Update")
        self.set_update_button_color("neutral")
        
        # Hide popout
        if hasattr(self, 'update_popout'):
            self.update_popout.hide()
    
    def set_update_button_color(self, color):
        """Set the update button color"""
        if color == "green":
            self.update_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #45a049;
                }}
                QPushButton:pressed {{
                    background-color: #3d8b40;
                    padding-bottom: 7px;
                }}
            """)
        elif color == "orange":
            self.update_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #FFC107;
                    color: white;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #FFB300;
                }}
                QPushButton:pressed {{
                    background-color: #FFA000;
                    padding-bottom: 7px;
                }}
            """)
        elif color == "red":
            self.update_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #f44336;
                    color: white;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #da190b;
                }}
                QPushButton:pressed {{
                    background-color: #c1170a;
                    padding-bottom: 7px;
                }}
            """)
        elif color == "light_green":
            # Light green for "update available" state
            self.update_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #a5d6a7;
                    color: #1b5e20;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #81c784;
                }}
                QPushButton:pressed {{
                    background-color: #66bb6a;
                    padding-bottom: 7px;
                }}
            """)
        elif color == "neutral":
            # Neutral grey for default state
            self.update_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #e0e0e0;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #d0d0d0;
                }}
                QPushButton:pressed {{
                    background-color: #c0c0c0;
                    padding-bottom: 7px;
                }}
            """)
    
    def start_update_pull(self):
        """Start the update workflow and kick off git pull."""
        self.update_button.setText("Checking")
        self.set_update_button_color("orange")
        self.checking_animation_state = 0
        self.checking_animation_timer.start(500)
        self.update_service.run_pull()

    def on_update_service_output(self, text):
        """Append git output to the update popout."""
        if hasattr(self, 'update_popout'):
            self.update_popout.append_output(text)

    def on_update_service_finished(self, result):
        """Handle completion of the update workflow."""
        self.checking_animation_timer.stop()

        if result.get("reason") == "busy":
            self.update_button.setText("Update Busy")
            self.set_update_button_color("neutral")
            return

        if result.get("has_error"):
            self.update_button.setText("Error Updating")
            self.set_update_button_color("red")
            return

        if result.get("has_updates"):
            self.update_button.setText("Reboot")
            self.set_update_button_color("orange")
            commit_message = result.get("commit_message")
            if commit_message and hasattr(self, 'update_popout'):
                self.update_popout.show_success_message(commit_message)
            self.hide_update_notification()
        else:
            self.update_button.setText("Up to date!")
            self.set_update_button_color("green")
            self.hide_update_notification()

    def on_update_available_changed(self, available):
        """Reflect update availability in the UI."""
        if available:
            self.show_update_notification()
        else:
            self.hide_update_notification()
    
    def show_update_notification(self):
        """Show the update available notification in the UI"""
        # Show notification label on home page (if it exists)
        if hasattr(self, 'update_notification_label'):
            self.update_notification_label.show()
        
        # Change update button color to light green on settings page
        if hasattr(self, 'update_button'):
            self.set_update_button_color("light_green")
    
    def hide_update_notification(self):
        """Hide the update available notification"""
        # Hide notification label on home page
        if hasattr(self, 'update_notification_label'):
            self.update_notification_label.hide()
        
        # Reset update button color to normal green
        if hasattr(self, 'update_button'):
            self.set_update_button_color("green")
    
    def update_checking_animation(self):
        """Update the button text for checking animation"""
        animations = ["Checking", "Checking.", "Checking..", "Checking..."]
        self.update_button.setText(animations[self.checking_animation_state])
        self.checking_animation_state = (self.checking_animation_state + 1) % len(animations)
    
    def reboot_application(self):
        """Reboot the system"""
        # Close the update popout
        if hasattr(self, 'update_popout'):
            self.update_popout.hide()
        
        # Perform system reboot
        self.perform_system_reboot()
    
    def on_shutdown_exit_button_clicked(self):
        """Handle Shutdown/Exit button click"""
        # Show the popout and change button color to slightly darker
        self.show_shutdown_popout()
        self.set_shutdown_exit_button_color("active")
    
    def show_shutdown_popout(self):
        """Show the shutdown popout near the Shutdown/Exit button"""
        if not hasattr(self, 'shutdown_popout'):
            self.shutdown_popout = ShutdownPopout(self.config_store, self.settings_page)
            # Connect button signals
            self.shutdown_popout.reboot_button.clicked.connect(self.on_reboot_button_clicked)
            self.shutdown_popout.shutdown_button.clicked.connect(self.on_shutdown_button_clicked)
        
        # Reset shutdown and reboot state when showing popout
        self.shutdown_popout.reset_shutdown_state()
        self.shutdown_popout.reset_reboot_state()
        
        # Position the popout above the Shutdown/Exit button
        button_pos = self.shutdown_exit_button.mapTo(self.settings_page, self.shutdown_exit_button.rect().topLeft())
        popout_x = button_pos.x() + self.shutdown_exit_button.width() - self.shutdown_popout.width()  # Align to right edge
        popout_y = button_pos.y() - self.shutdown_popout.height() - 10  # 10px gap above button
        
        self.shutdown_popout.move(popout_x, popout_y)
        self.shutdown_popout.show()
        self.shutdown_popout.raise_()
        
        # Install event filter to detect clicks outside the popout
        QApplication.instance().installEventFilter(self)
    
    def close_shutdown_popout(self):
        """Close the shutdown popout and reset button state"""
        if hasattr(self, 'shutdown_popout'):
            self.shutdown_popout.hide()
            self.shutdown_popout.reset_shutdown_state()
            self.shutdown_popout.reset_reboot_state()
        
        # Reset button color to neutral
        self.set_shutdown_exit_button_color("neutral")
        
        # Remove event filter
        QApplication.instance().removeEventFilter(self)
    
    def set_shutdown_exit_button_color(self, color):
        """Set the shutdown/exit button color"""
        if color == "neutral":
            self.shutdown_exit_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #e0e0e0;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #d0d0d0;
                }}
                QPushButton:pressed {{
                    background-color: #c0c0c0;
                    padding-bottom: 7px;
                }}
            """)
        elif color == "active":
            self.shutdown_exit_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #c8c8c8;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #b8b8b8;
                }}
                QPushButton:pressed {{
                    background-color: #a8a8a8;
                    padding-bottom: 7px;
                }}
            """)
    
    def exit_to_desktop(self):
        """Exit the application to desktop"""
        QApplication.instance().quit()
    
    def on_reboot_button_clicked(self):
        """Handle reboot button click with two-stage confirmation"""
        if not self.shutdown_popout.reboot_confirmed:
            # First click: set to confirmation state (red)
            self.shutdown_popout.set_reboot_confirm_state()
        else:
            # Second click: actually perform reboot
            self.perform_system_reboot()
    
    def on_shutdown_button_clicked(self):
        """Handle shutdown button click with two-stage confirmation"""
        if not self.shutdown_popout.shutdown_confirmed:
            # First click: set to confirmation state (red)
            self.shutdown_popout.set_shutdown_confirm_state()
        else:
            # Second click: actually perform shutdown
            self.perform_system_shutdown()
    
    def perform_system_shutdown(self):
        """Perform system shutdown"""
        # Close the popout
        self.close_shutdown_popout()
        
        self.system_service.shutdown()
    
    def check_reboot_schedule(self):
        """Check if it's time to trigger the reboot countdown"""
        config = self.config_store.load()
        reboot_enabled = config.get('reboot_enabled', False)
        
        if not reboot_enabled:
            # Reset the flag when reboot is disabled
            self.cancel_reboot()
            self.reboot_scheduled_for_today = False
            return
        
        reboot_time_str = config.get('reboot_time', '12:00 AM')
        
        try:
            # Parse the scheduled reboot time
            reboot_time = datetime.strptime(reboot_time_str, '%I:%M %p').time()
            
            # Get current time
            now = datetime.now()
            current_time = now.time()
            
            # Calculate the time when warning should appear (60 seconds before reboot)
            warning_datetime = datetime.combine(now.date(), reboot_time)
            warning_datetime = warning_datetime.replace(second=0, microsecond=0)
            warning_time = (warning_datetime - timedelta(seconds=60)).time()
            
            # Create time objects for comparison (ignore seconds)
            current_minute = current_time.replace(second=0, microsecond=0)
            warning_minute = warning_time.replace(second=0, microsecond=0)
            
            # Check if current time matches warning time and we haven't triggered yet today
            if current_minute == warning_minute and not self.reboot_scheduled_for_today:
                self.reboot_scheduled_for_today = True
                self.start_reboot_countdown()
            
            # Reset flag at a different hour (to allow next day's reboot)
            # Reset when we're not within 2 minutes of the scheduled time
            reboot_minute = reboot_time.replace(second=0, microsecond=0)
            time_diff = abs((datetime.combine(now.date(), current_minute) - 
                           datetime.combine(now.date(), reboot_minute)).total_seconds())
            if time_diff > 120:  # More than 2 minutes away
                self.reboot_scheduled_for_today = False
                
        except (ValueError, AttributeError):
            # If parsing fails, do nothing
            pass
    
    def start_reboot_countdown(self):
        """Start the 60-second reboot countdown"""
        self.reboot_countdown_seconds = 60

        self.update_reboot_warning_label(self.reboot_countdown_seconds)
        self.show_reboot_warning()
        
        # Start countdown timer
        if self.reboot_countdown_timer is None:
            self.reboot_countdown_timer = QTimer()
            self.reboot_countdown_timer.timeout.connect(self.update_reboot_countdown)
        
        self.reboot_countdown_timer.start(1000)  # Update every second
    
    def update_reboot_countdown(self):
        """Update the reboot countdown each second"""
        if not self.config_store.get_bool('reboot_enabled', False):
            self.cancel_reboot()
            return

        self.reboot_countdown_seconds -= 1
        
        if self.reboot_countdown_seconds <= 0:
            # Time's up, perform reboot
            self.reboot_countdown_timer.stop()
            self.hide_reboot_warning()
            self.perform_system_reboot()
        else:
            self.update_reboot_warning_label(self.reboot_countdown_seconds)
    
    def cancel_reboot(self):
        """Cancel the scheduled reboot"""
        if self.reboot_countdown_timer:
            self.reboot_countdown_timer.stop()

        self.hide_reboot_warning()
        
        self.reboot_countdown_seconds = 0
        # Don't reset reboot_scheduled_for_today so it won't trigger again today

    def show_reboot_warning(self):
        if hasattr(self, "reboot_warning_container"):
            self.reboot_warning_container.show()

    def hide_reboot_warning(self):
        if hasattr(self, "reboot_warning_container"):
            self.reboot_warning_container.hide()

    def update_reboot_warning_label(self, seconds):
        if hasattr(self, "reboot_warning_label"):
            self.reboot_warning_label.setText(f"Rebooting in {seconds} seconds")
    
    def perform_system_reboot(self):
        """Perform system reboot"""
        # Close the popout
        self.close_shutdown_popout()
        
        self.system_service.reboot()
    
    def apply_screen_sleep_settings(self):
        """Apply screen sleep settings to the system using xset commands"""
        screen_sleep_enabled = self.config_store.get_bool('screen_sleep_enabled', False)
        screen_sleep_minutes = self.config_store.get_int('screen_sleep_minutes', 5)
        self.system_service.apply_screen_sleep_settings(screen_sleep_enabled, screen_sleep_minutes)
    
    def create_title_bar(self, button_widget, countdown_label=None, center_widget=None, update_notification_label=None):
        """Create a title bar with fixed center widget regardless of left/right widths"""
        title_bar = QWidget()
        title_bar.setStyleSheet("background-color: lightgray;")
        title_bar.setFixedHeight(75)

        grid = QGridLayout()
        grid.setContentsMargins(20, 0, 20, 0)
        grid.setHorizontalSpacing(0)

        # Left: Title label
        left_container = QWidget()
        left_layout = QHBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        title_label = QLabel(self.default_title_text)
        title_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 30px; font-weight: bold;")
        
        left_layout.addWidget(title_label, alignment=Qt.AlignVCenter | Qt.AlignLeft)
        left_container.setLayout(left_layout)
        
        # Return the title label so the caller can reference it
        self._last_title_label = title_label

        # Center: Optional center widget (clock)
        center_container = QWidget()
        center_layout = QHBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        if center_widget:
            center_layout.addWidget(center_widget, alignment=Qt.AlignCenter)
        center_container.setLayout(center_layout)

        # Right: Update notification (optional) + Countdown (optional) + button
        right_container = QWidget()
        right_layout = QHBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        right_layout.addStretch()
        # Add update notification label BEFORE countdown (to the left of it)
        if update_notification_label:
            right_layout.addWidget(update_notification_label, alignment=Qt.AlignVCenter | Qt.AlignRight)
        if countdown_label:
            right_layout.addWidget(countdown_label, alignment=Qt.AlignVCenter | Qt.AlignRight)
        right_layout.addWidget(button_widget, alignment=Qt.AlignVCenter | Qt.AlignRight)
        right_container.setLayout(right_layout)

        grid.addWidget(left_container, 0, 0)
        grid.addWidget(center_container, 0, 1)
        grid.addWidget(right_container, 0, 2)

        # Equal stretch on left and right, center fixed to its size
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)

        title_bar.setLayout(grid)
        return title_bar
    
    def setup_message_system(self):
        """Initialize the message display system with timers and scheduling"""
        if self.home_title_label is None:
            return
        
        # Reload message config to get latest settings
        self.message_config = self.message_store.load()
        
        self.configure_web_trigger_handlers()
        
        # Schedule first automatic message
        self.schedule_next_message()

    def configure_web_trigger_handlers(self):
        """Connect web trigger signals and handle initial pending events."""
        signals = getattr(self.settings_server, "signals", None)
        if signals is None:
            return
        signals.message_triggered.connect(self.on_web_message_triggered)
        signals.settings_changed.connect(self.on_web_settings_changed)
        self.check_for_web_trigger()

    def on_web_message_triggered(self, message):
        pending = self.settings_server.get_pending_message_trigger()
        if pending is False:
            return
        self.trigger_message_display(pending)

    def on_web_settings_changed(self):
        if self.settings_server.get_pending_settings_change():
            self.handle_settings_changed()
    
    def check_for_web_trigger(self):
        """Check if there's a pending message trigger or settings change from the web interface"""
        # Check for message trigger
        trigger = self.settings_server.get_pending_message_trigger()
        if trigger is not False:  # False means no trigger, None or a string means trigger
            self.trigger_message_display(trigger)
        
        # Check for settings change
        if self.settings_server.get_pending_settings_change():
            self.handle_settings_changed()
    
    def handle_settings_changed(self):
        """Handle settings change from web interface - sync settings and refresh display"""
        # Refresh Python's timezone cache in case timezone was changed
        time.tzset()
        
        # Sync all settings from config file
        self.config_store.refresh_if_changed()
        
        # Refresh the arrivals display immediately
        self.refresh_error_message = None  # Clear any previous error
        self.refresh_arrivals()
    
    def schedule_next_message(self):
        """Calculate and schedule the next automatic message display"""
        # Stop any existing schedule timer
        if hasattr(self, 'message_schedule_timer') and self.message_schedule_timer:
            self.message_schedule_timer.stop()
            self.message_schedule_timer = None
        
        # Don't schedule if no messages or already showing a message
        if not self.message_config.get("messages") or self.is_showing_message:
            return
        
        timing_mode = self.message_config.get("timing_mode", "periodic")
        
        # Don't schedule if disabled
        if timing_mode == "disabled":
            return
        
        # Check if we should respect time window
        if timing_mode == "periodic":
            interval_minutes = self.message_config.get("periodic_interval_minutes", 30)
            delay_ms = interval_minutes * 60 * 1000
            time_window_enabled = self.message_config.get("periodic_time_window_enabled", False)
            window_start = self.message_config.get("periodic_window_start", "09:00")
            window_end = self.message_config.get("periodic_window_end", "17:00")
        else:  # random
            min_minutes = self.message_config.get("random_min_minutes", 15)
            max_minutes = self.message_config.get("random_max_minutes", 60)
            random_minutes = random.randint(min_minutes, max_minutes)
            delay_ms = random_minutes * 60 * 1000
            time_window_enabled = self.message_config.get("random_time_window_enabled", False)
            window_start = self.message_config.get("random_window_start", "09:00")
            window_end = self.message_config.get("random_window_end", "17:00")
        
        # If time window is enabled, check if we're currently in the window
        if time_window_enabled and not self.is_in_time_window(window_start, window_end):
            # Schedule a check for when the window opens
            delay_ms = self.calculate_delay_until_window(window_start)
        
        # Create single-shot timer for next message
        self.message_schedule_timer = QTimer()
        self.message_schedule_timer.setSingleShot(True)
        self.message_schedule_timer.timeout.connect(lambda: self.on_message_timer_trigger())
        self.message_schedule_timer.start(delay_ms)
    
    def on_message_timer_trigger(self):
        """Called when message timer triggers - checks time window before displaying"""
        timing_mode = self.message_config.get("timing_mode", "periodic")
        
        # Get time window settings for current mode
        if timing_mode == "periodic":
            time_window_enabled = self.message_config.get("periodic_time_window_enabled", False)
            window_start = self.message_config.get("periodic_window_start", "09:00")
            window_end = self.message_config.get("periodic_window_end", "17:00")
        else:  # random
            time_window_enabled = self.message_config.get("random_time_window_enabled", False)
            window_start = self.message_config.get("random_window_start", "09:00")
            window_end = self.message_config.get("random_window_end", "17:00")
        
        # Check if we're in the time window (or if window is disabled)
        if not time_window_enabled or self.is_in_time_window(window_start, window_end):
            self.trigger_message_display(None)
        else:
            # Outside window, reschedule for when window opens
            self.schedule_next_message()
    
    def is_in_time_window(self, start_time_str, end_time_str):
        """Check if current time is within the specified time window"""
        now = datetime.now().time()
        
        # Parse time strings (format: "HH:MM")
        start_parts = start_time_str.split(':')
        end_parts = end_time_str.split(':')
        
        start_time = datetime.now().replace(
            hour=int(start_parts[0]), 
            minute=int(start_parts[1]), 
            second=0, 
            microsecond=0
        ).time()
        
        end_time = datetime.now().replace(
            hour=int(end_parts[0]), 
            minute=int(end_parts[1]), 
            second=0, 
            microsecond=0
        ).time()
        
        # Handle window that crosses midnight
        if start_time <= end_time:
            return start_time <= now <= end_time
        else:
            return now >= start_time or now <= end_time
    
    def calculate_delay_until_window(self, start_time_str):
        """Calculate milliseconds until the time window starts"""
        now = datetime.now()
        
        # Parse start time
        start_parts = start_time_str.split(':')
        window_start = now.replace(
            hour=int(start_parts[0]), 
            minute=int(start_parts[1]), 
            second=0, 
            microsecond=0
        )
        
        # If window start is in the past today, schedule for tomorrow
        if window_start <= now:
            window_start += timedelta(days=1)
        
        # Calculate delay in milliseconds
        delay = (window_start - now).total_seconds() * 1000
        return int(delay)
    
    def trigger_message_display(self, message=None):
        """
        Display a message with fade animation.
        
        Args:
            message: Specific message object or string to display, or None to pick random from list
        """
        # Don't trigger if already showing a message
        if self.is_showing_message:
            return
        
        # Reload config to get latest messages
        self.message_config = self.message_store.load()
        messages_list = self.message_config.get("messages", [])
        
        if not messages_list:
            return
        
        # Pick message
        if message is None:
            display_message = random.choice(messages_list)
        else:
            display_message = message
        
        # Handle old string format for backward compatibility
        if isinstance(display_message, str):
            display_message = {"text": display_message, "color": None}
        # Ensure it's a dict with text and color keys
        elif not isinstance(display_message, dict):
            return
        
        self.is_showing_message = True
        
        # Get fade duration from config
        fade_duration = self.message_config.get("fade_duration_ms", 800)
        
        # Fade out
        self.fade_out(fade_duration, lambda: self.swap_to_message(display_message))
    
    def swap_to_message(self, message):
        """Swap title text to message and fade back in"""
        # Extract text and color from message object
        message_text = message.get("text", "") if isinstance(message, dict) else str(message)
        message_color = message.get("color") if isinstance(message, dict) else None
        
        self.home_title_label.setText(message_text)
        
        # Apply color if specified
        if message_color:
            self.home_title_label.setStyleSheet(
                f"font-family: {self.font_family}; font-size: 30px; font-weight: bold; color: {message_color};"
            )
        else:
            # Use default (no color specified - current behavior)
            self.home_title_label.setStyleSheet(
                f"font-family: {self.font_family}; font-size: 30px; font-weight: bold;"
            )
        
        fade_duration = self.message_config.get("fade_duration_ms", 800)
        display_duration_seconds = self.message_config.get("display_duration_seconds", 5)
        
        # Fade in
        self.fade_in(fade_duration, lambda: self.schedule_message_restore(display_duration_seconds))
    
    def schedule_message_restore(self, duration_seconds):
        """Schedule restoration of default title after message display duration"""
        # Stop any existing restore timer
        if self.message_restore_timer:
            self.message_restore_timer.stop()
        
        self.message_restore_timer = QTimer()
        self.message_restore_timer.setSingleShot(True)
        self.message_restore_timer.timeout.connect(self.restore_default_title)
        self.message_restore_timer.start(duration_seconds * 1000)
    
    def restore_default_title(self):
        """Fade back to the default title"""
        fade_duration = self.message_config.get("fade_duration_ms", 800)
        
        # Fade out
        self.fade_out(fade_duration, lambda: self.swap_to_default())
    
    def swap_to_default(self):
        """Swap title text back to default and fade in"""
        self.home_title_label.setText(self.default_title_text)
        
        # Restore default styling (no color specified)
        self.home_title_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 30px; font-weight: bold;"
        )
        
        fade_duration = self.message_config.get("fade_duration_ms", 800)
        
        # Fade in
        self.fade_in(fade_duration, lambda: self.on_message_display_complete())
    
    def on_message_display_complete(self):
        """Called when message display cycle is complete"""
        self.is_showing_message = False
        # Schedule next message
        self.schedule_next_message()
    
    def fade_out(self, duration_ms, on_finished):
        """Fade title label to transparent"""
        if self.current_fade_animation:
            self.current_fade_animation.stop()
        
        self.current_fade_animation = QPropertyAnimation(self.title_opacity_effect, b"opacity")
        self.current_fade_animation.setDuration(duration_ms)
        self.current_fade_animation.setStartValue(1.0)
        self.current_fade_animation.setEndValue(0.0)
        self.current_fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.current_fade_animation.finished.connect(on_finished)
        self.current_fade_animation.start()
    
    def fade_in(self, duration_ms, on_finished):
        """Fade title label from transparent to visible"""
        if self.current_fade_animation:
            self.current_fade_animation.stop()
        
        self.current_fade_animation = QPropertyAnimation(self.title_opacity_effect, b"opacity")
        self.current_fade_animation.setDuration(duration_ms)
        self.current_fade_animation.setStartValue(0.0)
        self.current_fade_animation.setEndValue(1.0)
        self.current_fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.current_fade_animation.finished.connect(on_finished)
        self.current_fade_animation.start()
    
    def build_startup_center_container(self):
        center_container = QWidget()
        center_layout = QVBoxLayout()
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setSpacing(20)

        self.startup_title_label = QLabel(self.default_title_text)
        self.startup_title_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 48px; font-weight: bold; color: #333;"
        )
        self.startup_title_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.startup_title_label)

        self.startup_status_label = QLabel("Connecting to Metro API...")
        self.startup_status_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 24px; color: #666;"
        )
        self.startup_status_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.startup_status_label)

        self.startup_buttons_container = self.build_startup_buttons_container()
        center_layout.addWidget(self.startup_buttons_container)

        self.startup_wifi_buttons_container = self.build_startup_wifi_buttons_container()
        center_layout.addWidget(self.startup_wifi_buttons_container)

        center_container.setLayout(center_layout)
        return center_container

    def build_startup_buttons_container(self):
        container = QWidget()
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 20, 0, 0)
        buttons_layout.setSpacing(20)
        buttons_layout.setAlignment(Qt.AlignCenter)

        self.startup_exit_button = QPushButton("Exit to Desktop")
        self.startup_exit_button.setMinimumWidth(180)
        self.startup_exit_button.setStyleSheet(
            """
            QPushButton {
                font-family: {self.font_family};
                font-size: 18px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #c0c0c0;
                padding-bottom: 9px;
            }
        """
        )
        self.startup_exit_button.clicked.connect(QApplication.instance().quit)
        buttons_layout.addWidget(self.startup_exit_button)

        self.startup_reboot_button = QPushButton("Reboot")
        self.startup_reboot_button.setMinimumWidth(180)
        self.startup_reboot_button.setStyleSheet(
            """
            QPushButton {
                font-family: {self.font_family};
                font-size: 18px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #c0c0c0;
                padding-bottom: 9px;
            }
        """
        )
        self.startup_reboot_button.clicked.connect(self.perform_system_reboot)
        buttons_layout.addWidget(self.startup_reboot_button)

        self.startup_shutdown_button = QPushButton("Shutdown")
        self.startup_shutdown_button.setMinimumWidth(180)
        self.startup_shutdown_button.setStyleSheet(
            """
            QPushButton {
                font-family: {self.font_family};
                font-size: 18px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #c0c0c0;
                padding-bottom: 9px;
            }
        """
        )
        self.startup_shutdown_button.clicked.connect(self.perform_system_shutdown)
        buttons_layout.addWidget(self.startup_shutdown_button)

        container.setLayout(buttons_layout)
        container.hide()
        return container

    def build_startup_wifi_buttons_container(self):
        container = QWidget()
        wifi_buttons_layout = QHBoxLayout()
        wifi_buttons_layout.setContentsMargins(0, 20, 0, 0)
        wifi_buttons_layout.setSpacing(20)
        wifi_buttons_layout.setAlignment(Qt.AlignCenter)

        self.startup_launch_setup_button = QPushButton("Launch Setup")
        self.startup_launch_setup_button.setMinimumWidth(180)
        self.startup_launch_setup_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 18px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #d0d0d0;
            }}
            QPushButton:pressed {{
                background-color: #c0c0c0;
                padding-bottom: 9px;
            }}
        """
        )
        self.startup_launch_setup_button.clicked.connect(self.launch_wifi_setup)
        wifi_buttons_layout.addWidget(self.startup_launch_setup_button)

        self.startup_wifi_reboot_button = QPushButton("Reboot")
        self.startup_wifi_reboot_button.setMinimumWidth(180)
        self.startup_wifi_reboot_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 18px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #d0d0d0;
            }}
            QPushButton:pressed {{
                background-color: #c0c0c0;
                padding-bottom: 9px;
            }}
        """
        )
        self.startup_wifi_reboot_button.clicked.connect(self.perform_system_reboot)
        wifi_buttons_layout.addWidget(self.startup_wifi_reboot_button)

        self.startup_wifi_shutdown_button = QPushButton("Shutdown")
        self.startup_wifi_shutdown_button.setMinimumWidth(180)
        self.startup_wifi_shutdown_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 18px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #d0d0d0;
            }}
            QPushButton:pressed {{
                background-color: #c0c0c0;
                padding-bottom: 9px;
            }}
        """
        )
        self.startup_wifi_shutdown_button.clicked.connect(self.perform_system_shutdown)
        wifi_buttons_layout.addWidget(self.startup_wifi_shutdown_button)

        container.setLayout(wifi_buttons_layout)
        container.hide()
        return container

    def create_startup_page(self):
        """Create the startup/loading page shown before API connection"""
        page = QWidget()
        page.setStyleSheet("background-color: lightgray;")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addStretch()
        main_layout.addWidget(self.build_startup_center_container())
        main_layout.addStretch()

        page.setLayout(main_layout)
        return page

    def build_home_title_bar(self):
        self.refresh_countdown_label = QLabel("Refresh in 30s")
        self.refresh_countdown_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 14px; color: #666; padding: 0px;"
        )
        self.refresh_countdown_label.setMaximumWidth(500)
        self.refresh_countdown_label.setWordWrap(False)
        self.refresh_countdown_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.refresh_countdown_label.setContentsMargins(0, 0, 0, 0)
        self.refresh_countdown_label.setMargin(0)
        self.refresh_countdown_label.setIndent(0)

        self.clock_label = QLabel()
        self.clock_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 30px; font-weight: bold;"
        )
        self.update_clock()
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)

        self.update_notification_label = QLabel("Update Available")
        self.update_notification_label.setStyleSheet(
            f"""
            font-family: {self.font_family};
            font-size: 14px;
            font-weight: bold;
            color: #155724;
            background-color: #d4edda;
            padding: 5px 10px;
            border-radius: 4px;
        """
        )
        self.update_notification_label.hide()

        settings_button = QPushButton("⚙")
        settings_button.setStyleSheet(
            """
            QPushButton {
                font-family: {self.font_family};
                font-size: 22px;
                font-weight: bold;
                padding: 5px 20px;
                background-color: lightgray;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #b0b0b0;
            }
            QPushButton:pressed {
                background-color: #909090;
                padding-bottom: 4px;
            }
        """
        )
        settings_button.setFixedHeight(45)
        settings_button.clicked.connect(self.open_settings_page)

        close_button = QPushButton("✕")
        close_button.setStyleSheet(
            """
            QPushButton {
                font-family: {self.font_family};
                font-size: 22px;
                font-weight: bold;
                padding: 5px 20px;
                background-color: lightgray;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #b0b0b0;
            }
            QPushButton:pressed {
                background-color: #909090;
                padding-bottom: 4px;
            }
        """
        )
        close_button.setFixedHeight(45)
        close_button.clicked.connect(QApplication.instance().quit)

        buttons_container = QWidget()
        buttons_container.setStyleSheet("background-color: lightgray;")
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10)
        buttons_layout.addWidget(settings_button)
        buttons_layout.addWidget(close_button)
        buttons_container.setLayout(buttons_layout)

        title_bar = self.create_title_bar(
            buttons_container,
            self.refresh_countdown_label,
            self.clock_label,
            self.update_notification_label,
        )
        self.home_title_label = self._last_title_label
        return title_bar

    def configure_home_title_effect(self):
        self.title_opacity_effect = QGraphicsOpacityEffect()
        self.title_opacity_effect.setOpacity(1.0)
        self.home_title_label.setGraphicsEffect(self.title_opacity_effect)

    def build_home_arrivals_content(self):
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(0)

        content_layout.addWidget(self.build_reboot_warning_banner())

        self.arrival_rows = []
        for i in range(5):
            row = self.create_arrival_row(i)
            self.arrival_rows.append(row)
            content_layout.addWidget(row)

        content_layout.addStretch()

        content_widget = QWidget()
        content_widget.setLayout(content_layout)
        return content_widget

    def build_reboot_warning_banner(self):
        self.reboot_warning_container = QWidget()
        self.reboot_warning_container.setStyleSheet("background-color: transparent;")
        self.reboot_warning_container.setFixedHeight(50)

        # Horizontal layout for label and button
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.setAlignment(Qt.AlignCenter)

        self.reboot_warning_label = QLabel("Rebooting in 60 seconds")
        self.reboot_warning_label.setStyleSheet(
            f"""
            font-family: {self.font_family};
            font-size: 14px;
            font-weight: bold;
            color: #721c24;
            background-color: #f8d7da;
            padding: 4px 8px;
            border-radius: 4px;
        """
        )
        self.reboot_warning_label.setAlignment(Qt.AlignCenter)
        self.reboot_warning_label.setWordWrap(False)
        content_layout.addWidget(self.reboot_warning_label)

        self.reboot_cancel_button = QPushButton("Cancel")
        self.reboot_cancel_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 12px;
                font-weight: bold;
                padding: 3px 8px;
                background-color: #ffffff;
                color: #721c24;
                border: 1px solid #f5c6cb;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #f8d7da;
            }}
            QPushButton:pressed {{
                background-color: #f5c6cb;
                padding-bottom: 2px;
            }}
        """
        )
        self.reboot_cancel_button.clicked.connect(self.cancel_reboot)
        content_layout.addWidget(self.reboot_cancel_button)

        # Wrap the horizontal content to allow alignment on the parent layout
        content_widget = QWidget()
        content_widget.setLayout(content_layout)

        # Vertical layout to center content within fixed height
        warning_layout = QVBoxLayout()
        warning_layout.setContentsMargins(0, 0, 0, 0)
        warning_layout.setSpacing(0)
        warning_layout.setAlignment(Qt.AlignCenter)
        warning_layout.addWidget(content_widget, alignment=Qt.AlignCenter)

        self.reboot_warning_container.setLayout(warning_layout)
        self.reboot_warning_container.hide()
        return self.reboot_warning_container
    
    def create_home_page(self):
        """Create the home page"""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.build_home_title_bar())
        self.configure_home_title_effect()

        layout.addWidget(self.build_home_arrivals_content())
        page.setLayout(layout)

        self.setup_message_system()
        return page

    def combo_box_stylesheet(self):
        return """
            QComboBox {
                font-family: {self.font_family};
                font-size: 18px;
                padding: 7px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
            }
            QComboBox:hover {
                border: 1px solid #999;
            }
            QComboBox QAbstractItemView {
                font-family: {self.font_family};
                font-size: 18px;
                background-color: white;
                selection-background-color: #e0e0e0;
                selection-color: #000;
                color: #000;
            }
            QComboBox QAbstractItemView::item {
                color: #000;
                padding: 5px;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #e0e0e0;
                color: #000;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #e0e0e0;
                color: #000;
            }
        """

    def checkbox_indicator_stylesheet(self):
        return """
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 25px;
                height: 25px;
                border: 2px solid #ccc;
                border-radius: 3px;
                background-color: white;
            }
            QCheckBox::indicator:hover {
                border: 2px solid #999;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border: 2px solid #4CAF50;
            }
        """

    def build_settings_back_button(self):
        back_button = QPushButton("←")
        back_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 22px;
                font-weight: bold;
                padding: 5px 20px;
                background-color: lightgray;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #b0b0b0;
            }}
            QPushButton:pressed {{
                background-color: #909090;
                padding-bottom: 4px;
            }}
        """
        )
        back_button.setFixedHeight(45)
        back_button.clicked.connect(self.close_settings_page)
        return back_button

    def build_settings_heading(self):
        heading_layout = QVBoxLayout()
        settings_label = QLabel("Settings")
        settings_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 28px; font-weight: bold;"
        )
        settings_label.setAlignment(Qt.AlignCenter)
        heading_layout.addWidget(settings_label)
        heading_layout.addSpacing(10)
        return heading_layout

    def build_settings_selectors_column(self, label_width):
        selectors_column_layout = QVBoxLayout()
        selectors_column_layout.setSpacing(20)
        selectors_column_layout.setAlignment(Qt.AlignTop)
        selectors_column_layout.addLayout(self.build_line_selector_row(label_width))
        selectors_column_layout.addLayout(self.build_station_selector_row(label_width))
        selectors_column_layout.addLayout(self.build_destination_selector_row(label_width))
        return selectors_column_layout

    def build_line_selector_row(self, label_width):
        line_selector_layout = QHBoxLayout()
        line_selector_layout.setContentsMargins(0, 0, 0, 0)

        line_label = QLabel("Select Line:")
        line_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        line_label.setFixedWidth(label_width)
        line_selector_layout.addWidget(line_label)

        self.line_combo = QComboBox()
        self.line_combo.setStyleSheet(self.combo_box_stylesheet())
        self.line_combo.setMinimumWidth(265)
        self.configure_combo_for_touchscreen(self.line_combo)
        self.line_combo.currentIndexChanged.connect(self.on_line_selected)
        self.line_combo.currentIndexChanged.connect(self.mark_settings_changed)
        line_selector_layout.addWidget(self.line_combo)
        line_selector_layout.addStretch()
        return line_selector_layout

    def build_station_selector_row(self, label_width):
        station_selector_layout = QHBoxLayout()
        station_selector_layout.setContentsMargins(0, 0, 0, 0)

        station_label = QLabel("Select Station:")
        station_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        station_label.setFixedWidth(label_width)
        station_selector_layout.addWidget(station_label)

        self.station_combo = QComboBox()
        self.station_combo.setStyleSheet(self.combo_box_stylesheet())
        self.station_combo.setMinimumWidth(265)
        self.configure_combo_for_touchscreen(self.station_combo)
        self.station_combo.currentIndexChanged.connect(self.on_station_selected)
        self.station_combo.currentIndexChanged.connect(self.mark_settings_changed)
        station_selector_layout.addWidget(self.station_combo)
        station_selector_layout.addStretch()
        return station_selector_layout

    def build_destination_selector_row(self, label_width):
        destination_selector_layout = QHBoxLayout()
        destination_selector_layout.setContentsMargins(0, 0, 0, 0)

        destination_label = QLabel("Select Destination:")
        destination_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        destination_label.setFixedWidth(label_width)
        destination_selector_layout.addWidget(destination_label)

        self.destination_combo = QComboBox()
        self.destination_combo.setStyleSheet(self.combo_box_stylesheet())
        self.destination_combo.setMinimumWidth(265)
        self.configure_combo_for_touchscreen(self.destination_combo)
        self.destination_combo.currentIndexChanged.connect(self.on_destination_selected)
        self.destination_combo.currentIndexChanged.connect(self.mark_settings_changed)
        destination_selector_layout.addWidget(self.destination_combo)
        destination_selector_layout.addStretch()
        return destination_selector_layout

    def build_settings_checkboxes_column(self, label_width):
        checkboxes_column_layout = QVBoxLayout()
        checkboxes_column_layout.setSpacing(20)
        checkboxes_column_layout.setAlignment(Qt.AlignTop)
        checkboxes_column_layout.addLayout(self.build_countdown_checkbox_row(label_width))
        checkboxes_column_layout.addLayout(self.build_clock_checkbox_row(label_width))
        checkboxes_column_layout.addLayout(self.build_filter_destination_checkbox_row(label_width))
        checkboxes_column_layout.addLayout(self.build_filter_direction_checkbox_row(label_width))
        return checkboxes_column_layout

    def build_countdown_checkbox_row(self, label_width):
        countdown_checkbox_layout = QHBoxLayout()
        countdown_checkbox_layout.setContentsMargins(0, 0, 0, 0)

        countdown_label = QLabel("Show Time to Refresh:")
        countdown_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        countdown_label.setFixedWidth(label_width)
        countdown_checkbox_layout.addWidget(countdown_label)

        self.show_countdown_checkbox = QCheckBox()
        self.show_countdown_checkbox.setStyleSheet(self.checkbox_indicator_stylesheet())
        self.show_countdown_checkbox.setChecked(True)
        self.show_countdown_checkbox.stateChanged.connect(self.toggle_countdown_visibility)
        self.show_countdown_checkbox.stateChanged.connect(self.mark_settings_changed)

        countdown_checkbox_layout.addWidget(self.show_countdown_checkbox)
        countdown_checkbox_layout.addStretch()
        return countdown_checkbox_layout

    def build_clock_checkbox_row(self, label_width):
        clock_checkbox_layout = QHBoxLayout()
        clock_checkbox_layout.setContentsMargins(0, 0, 0, 0)

        clock_label = QLabel("Show Clock in Top Bar:")
        clock_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        clock_label.setFixedWidth(label_width)
        clock_checkbox_layout.addWidget(clock_label)

        self.show_clock_checkbox = QCheckBox()
        self.show_clock_checkbox.setStyleSheet(self.show_countdown_checkbox.styleSheet())
        self.show_clock_checkbox.setChecked(True)
        self.show_clock_checkbox.stateChanged.connect(self.toggle_clock_visibility)
        self.show_clock_checkbox.stateChanged.connect(self.mark_settings_changed)
        clock_checkbox_layout.addWidget(self.show_clock_checkbox)
        clock_checkbox_layout.addStretch()
        return clock_checkbox_layout

    def build_filter_destination_checkbox_row(self, label_width):
        filter_checkbox_layout = QHBoxLayout()
        filter_checkbox_layout.setContentsMargins(0, 0, 0, 0)

        filter_label = QLabel("Filter by Selected Destination:")
        filter_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        filter_label.setFixedWidth(label_width)
        filter_checkbox_layout.addWidget(filter_label)

        self.filter_by_destination_checkbox = QCheckBox()
        self.filter_by_destination_checkbox.setStyleSheet(self.checkbox_indicator_stylesheet())
        self.filter_by_destination_checkbox.setChecked(False)
        self.filter_by_destination_checkbox.stateChanged.connect(
            self.on_filter_by_destination_changed
        )
        self.filter_by_destination_checkbox.stateChanged.connect(self.update_arrivals_display)
        self.filter_by_destination_checkbox.stateChanged.connect(self.mark_settings_changed)

        filter_checkbox_layout.addWidget(self.filter_by_destination_checkbox)
        filter_checkbox_layout.addStretch()
        return filter_checkbox_layout

    def build_filter_direction_checkbox_row(self, label_width):
        filter_direction_checkbox_layout = QHBoxLayout()
        filter_direction_checkbox_layout.setContentsMargins(0, 0, 0, 0)

        filter_direction_label = QLabel("Filter by Destination Direction:")
        filter_direction_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        filter_direction_label.setFixedWidth(label_width)
        filter_direction_checkbox_layout.addWidget(filter_direction_label)

        self.filter_by_destination_direction_checkbox = QCheckBox()
        self.filter_by_destination_direction_checkbox.setStyleSheet(
            self.checkbox_indicator_stylesheet()
        )
        self.filter_by_destination_direction_checkbox.setChecked(False)
        self.filter_by_destination_direction_checkbox.stateChanged.connect(
            self.on_filter_by_direction_changed
        )
        self.filter_by_destination_direction_checkbox.stateChanged.connect(
            self.update_arrivals_display
        )
        self.filter_by_destination_direction_checkbox.stateChanged.connect(
            self.mark_settings_changed
        )

        filter_direction_checkbox_layout.addWidget(self.filter_by_destination_direction_checkbox)
        filter_direction_checkbox_layout.addStretch()
        return filter_direction_checkbox_layout

    def build_settings_controls_layout(self):
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(40, 20, 40, 0)
        controls_layout.setSpacing(0)

        selectors_label_width = 190
        checkboxes_label_width = 310
        selectors_column_layout = self.build_settings_selectors_column(selectors_label_width)
        checkboxes_column_layout = self.build_settings_checkboxes_column(checkboxes_label_width)

        controls_layout.addLayout(selectors_column_layout)
        controls_layout.addSpacing(40)
        controls_layout.addWidget(self.build_settings_vertical_separator())
        controls_layout.addSpacing(39)
        controls_layout.addLayout(checkboxes_column_layout)
        return controls_layout

    def build_settings_vertical_separator(self):
        separator_line = QWidget()
        separator_line.setStyleSheet("background-color: #d0d0d0;")
        separator_line.setFixedWidth(1)
        return separator_line

    def build_settings_horizontal_separator(self):
        separator_container = QHBoxLayout()
        separator_container.setContentsMargins(40, 0, 40, 0)
        horizontal_separator = QWidget()
        horizontal_separator.setStyleSheet("background-color: #d0d0d0;")
        horizontal_separator.setFixedHeight(1)
        separator_container.addWidget(horizontal_separator)
        return separator_container

    def build_screen_sleep_section(self):
        system_settings_layout = QHBoxLayout()
        system_settings_layout.setContentsMargins(40, 0, 40, 0)
        system_settings_layout.setSpacing(0)

        screen_sleep_column_layout = QVBoxLayout()
        screen_sleep_column_layout.setSpacing(15)
        screen_sleep_column_layout.setAlignment(Qt.AlignTop)
        screen_sleep_column_layout.addLayout(self.build_screen_sleep_enable_row())
        screen_sleep_column_layout.addLayout(self.build_screen_sleep_slider_row())
        system_settings_layout.addLayout(screen_sleep_column_layout)
        return system_settings_layout

    def build_screen_sleep_enable_row(self):
        screen_sleep_enable_layout = QHBoxLayout()
        screen_sleep_enable_layout.setContentsMargins(0, 0, 0, 0)

        screen_sleep_enable_label = QLabel("Enable Screen Sleep:")
        screen_sleep_enable_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        screen_sleep_enable_layout.addWidget(screen_sleep_enable_label)

        self.screen_sleep_enabled_checkbox = QCheckBox()
        self.screen_sleep_enabled_checkbox.setStyleSheet(self.checkbox_indicator_stylesheet())
        self.screen_sleep_enabled_checkbox.setChecked(False)
        self.screen_sleep_enabled_checkbox.stateChanged.connect(self.mark_settings_changed)
        screen_sleep_enable_layout.addWidget(self.screen_sleep_enabled_checkbox)
        screen_sleep_enable_layout.addStretch()
        return screen_sleep_enable_layout

    def build_screen_sleep_slider_row(self):
        screen_sleep_slider_layout = QVBoxLayout()
        screen_sleep_slider_layout.setContentsMargins(0, 0, 0, 0)
        screen_sleep_slider_layout.setSpacing(5)

        self.screen_sleep_value_label = QLabel("Screen Sleep Timeout: 5 min")
        self.screen_sleep_value_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        screen_sleep_slider_layout.addWidget(self.screen_sleep_value_label)

        self.screen_sleep_slider = QSlider(Qt.Horizontal)
        self.screen_sleep_slider.setMinimum(1)
        self.screen_sleep_slider.setMaximum(30)
        self.screen_sleep_slider.setValue(5)
        self.screen_sleep_slider.setTickPosition(QSlider.TicksBelow)
        self.screen_sleep_slider.setTickInterval(5)
        self.screen_sleep_slider.setStyleSheet(
            """
            QSlider::groove:horizontal {
                border: 1px solid #ccc;
                height: 8px;
                background: white;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                border: 1px solid #4CAF50;
                width: 20px;
                margin: -7px 0;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #45a049;
                border: 1px solid #45a049;
            }
            QSlider::sub-page:horizontal {
                background: #4CAF50;
                border: 1px solid #4CAF50;
                height: 8px;
                border-radius: 4px;
            }
        """
        )
        self.screen_sleep_slider.valueChanged.connect(self.update_screen_sleep_label)
        self.screen_sleep_slider.valueChanged.connect(self.mark_settings_changed)
        screen_sleep_slider_layout.addWidget(self.screen_sleep_slider)
        return screen_sleep_slider_layout

    def build_settings_left_buttons(self):
        left_buttons_container = QWidget()
        left_buttons_layout = QHBoxLayout()
        left_buttons_layout.setContentsMargins(0, 0, 0, 0)
        left_buttons_layout.setSpacing(10)

        self.ip_button = QPushButton("IP")
        self.ip_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 20px;
                font-weight: bold;
                padding: 8px 12px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #d0d0d0;
            }}
            QPushButton:pressed {{
                background-color: #c0c0c0;
                padding-bottom: 7px;
            }}
        """
        )
        self.ip_button.installEventFilter(self)
        left_buttons_layout.addWidget(self.ip_button)

        self.wifi_button = QPushButton("WiFi Setup")
        self.wifi_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 20px;
                font-weight: bold;
                padding: 8px 12px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #d0d0d0;
            }}
            QPushButton:pressed {{
                background-color: #c0c0c0;
                padding-bottom: 7px;
            }}
        """
        )
        self.wifi_button.clicked.connect(self.launch_wifi_setup)
        left_buttons_layout.addWidget(self.wifi_button)

        left_buttons_container.setLayout(left_buttons_layout)
        return left_buttons_container

    def build_settings_center_section(self):
        center_section_container = QWidget()
        center_section_layout = QVBoxLayout()
        center_section_layout.setContentsMargins(0, 0, 0, 0)
        center_section_layout.setSpacing(5)

        save_button = QPushButton("Save Settings")
        save_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 20px;
                font-weight: bold;
                padding: 12px 36px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #45a049;
            }}
            QPushButton:pressed {{
                background-color: #3d8b40;
                padding-bottom: 11px;
            }}
        """
        )
        save_button.clicked.connect(self.save_settings)
        center_section_layout.addWidget(save_button, alignment=Qt.AlignCenter)

        labels_container = QHBoxLayout()
        labels_container.setSpacing(10)

        self.timestamp_label = QLabel()
        self.timestamp_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 14px; color: #666;"
        )
        self.timestamp_label.setAlignment(Qt.AlignCenter)
        self.update_timestamp_label()
        labels_container.addWidget(self.timestamp_label)

        self.unsaved_warning_label = QLabel("Changes not yet saved!")
        self.unsaved_warning_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 14px; color: #e74c3c;"
        )
        self.unsaved_warning_label.setAlignment(Qt.AlignCenter)
        self.unsaved_warning_label.hide()
        labels_container.addWidget(self.unsaved_warning_label)

        center_section_layout.addLayout(labels_container)
        center_section_container.setLayout(center_section_layout)
        return center_section_container

    def build_settings_right_buttons(self):
        right_buttons_container = QWidget()
        right_buttons_layout = QHBoxLayout()
        right_buttons_layout.setContentsMargins(0, 0, 0, 0)
        right_buttons_layout.setSpacing(10)

        self.update_button = QPushButton("Update")
        self.update_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 20px;
                font-weight: bold;
                padding: 8px 16px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #d0d0d0;
            }}
            QPushButton:pressed {{
                background-color: #c0c0c0;
                padding-bottom: 7px;
            }}
        """
        )
        self.update_button.clicked.connect(self.on_update_button_clicked)
        right_buttons_layout.addWidget(self.update_button)

        self.shutdown_exit_button = QPushButton("Shutdown")
        self.shutdown_exit_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 20px;
                font-weight: bold;
                padding: 8px 16px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #d0d0d0;
            }}
            QPushButton:pressed {{
                background-color: #c0c0c0;
                padding-bottom: 7px;
            }}
        """
        )
        self.shutdown_exit_button.clicked.connect(self.on_shutdown_exit_button_clicked)
        right_buttons_layout.addWidget(self.shutdown_exit_button)

        right_buttons_container.setLayout(right_buttons_layout)
        return right_buttons_container

    def build_settings_bottom_row(self):
        bottom_row_grid = QGridLayout()
        bottom_row_grid.setContentsMargins(20, 0, 20, 20)
        bottom_row_grid.setHorizontalSpacing(10)

        bottom_row_grid.addWidget(
            self.build_settings_left_buttons(),
            0,
            0,
            Qt.AlignLeft | Qt.AlignBottom,
        )
        bottom_row_grid.addWidget(
            self.build_settings_center_section(),
            0,
            1,
            Qt.AlignCenter | Qt.AlignBottom,
        )
        bottom_row_grid.addWidget(
            self.build_settings_right_buttons(),
            0,
            2,
            Qt.AlignRight | Qt.AlignBottom,
        )

        bottom_row_grid.setColumnStretch(0, 1)
        bottom_row_grid.setColumnStretch(1, 1)
        bottom_row_grid.setColumnStretch(2, 1)
        return bottom_row_grid
    
    def create_settings_page(self):
        """Create the settings page"""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.create_title_bar(self.build_settings_back_button()))
        self.settings_title_label = self._last_title_label

        content_layout = QVBoxLayout()
        content_layout.addLayout(self.build_settings_heading())
        content_layout.addLayout(self.build_settings_controls_layout())
        content_layout.addSpacing(10)
        content_layout.addLayout(self.build_settings_horizontal_separator())
        content_layout.addSpacing(10)
        content_layout.addLayout(self.build_screen_sleep_section())
        content_layout.addStretch()
        content_layout.addLayout(self.build_settings_bottom_row())

        content_widget = QWidget()
        content_widget.setLayout(content_layout)
        layout.addWidget(content_widget)

        page.setLayout(layout)
        return page

def parse_cli_args():
    """Parse command line arguments for runtime display options."""
    parser = argparse.ArgumentParser(description="Train arrivals display")
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Launch the display in fullscreen mode",
    )
    return parser.parse_args()


def main():
    """Application entrypoint."""
    args = parse_cli_args()
    config_store = ConfigStore()
    message_store = MessageStore()
    settings_server = SettingsServerClient()
    system_service = SystemService()
    working_dir = os.path.dirname(os.path.abspath(__file__))
    update_service = UpdateService(settings_server, working_dir=working_dir)

    api_timeout_seconds = config_store.get_int('api_timeout_seconds', 5)
    metro_api = MetroAPI(config_store.get_str('api_key', ''), timeout_seconds=api_timeout_seconds)
    data_handler = DataHandler(metro_api)

    try:
        data_handler.fetch_lines()
    except MetroAPIError:
        # Suppress error during startup - will be shown in UI if needed
        pass

    app = QApplication([])

    window = MainWindow(
        data_handler=data_handler,
        config_store=config_store,
        message_store=message_store,
        settings_server=settings_server,
        system_service=system_service,
        update_service=update_service,
    )
    if args.fullscreen:
        window.showFullScreen()
    else:
        window.setFixedSize(1024, 600)
        window.show()

    settings_server.start(data_handler)

    app.exec()


if __name__ == "__main__":
    main()
