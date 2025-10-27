from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QPushButton, QStackedWidget, QComboBox, QCheckBox, QPlainTextEdit
from PyQt5.QtCore import QSize, Qt, QTimer, QEvent, QProcess
from PyQt5.QtGui import QFontDatabase, QColor, QPalette, QPixmap, QPainter, QIcon
from MetroAPI import MetroAPI, MetroAPIError
from data_handler import DataHandler
import config_handler
import os
import sys
import socket
from datetime import datetime

class IPPopout(QWidget):
    """A popout widget that displays the device IP address"""
    def __init__(self, ip_address, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        
        # Create layout
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        # Create labels
        label = QLabel("Device IP:")
        label.setStyleSheet("font-family: Quicksand; font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(label)
        
        ip_label = QLabel(ip_address)
        ip_label.setStyleSheet("font-family: Quicksand; font-size: 16px; color: #666;")
        layout.addWidget(ip_label)
        
        self.setLayout(layout)
        
        # Style the popout
        self.setStyleSheet("""
            IPPopout {
                background-color: white;
                border: 2px solid #999;
                border-radius: 5px;
            }
        """)
        
        self.adjustSize()

class UpdatePopout(QWidget):
    """A popout widget that displays git pull terminal output"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        
        # Create content layout (will have header and output)
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(3, 3, 3, 3)  # Space for border
        content_layout.setSpacing(0)
        
        # Create header with close button
        header = QWidget()
        header.setStyleSheet("background-color: #f0f0f0; border-bottom: 1px solid #999; border: none;")
        header.setFixedHeight(30)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 5, 5, 5)
        
        header_label = QLabel("Update Status")
        header_label.setStyleSheet("font-family: Quicksand; font-size: 14px; font-weight: bold; color: #333; border: none;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        self.close_button = QPushButton("✕")
        self.close_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
                background-color: transparent;
                border: none;
                color: #666;
            }
            QPushButton:hover {
                color: #000;
                background-color: #e0e0e0;
                border-radius: 3px;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """)
        self.close_button.setFixedSize(20, 20)
        header_layout.addWidget(self.close_button)
        
        header.setLayout(header_layout)
        content_layout.addWidget(header)
        
        # Create text area for terminal output
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet("""
            QPlainTextEdit {
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding: 10px;
            }
        """)
        content_layout.addWidget(self.output_text)
        
        # Create a container widget for the border
        container = QWidget()
        container.setLayout(content_layout)
        container.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 3px solid #666;
                border-radius: 5px;
            }
        """)
        
        # Main layout to hold the container
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        self.setLayout(main_layout)
        
        # Set fixed size
        self.setFixedSize(500, 300)
    
    def append_output(self, text):
        """Append text to the output area"""
        self.output_text.appendPlainText(text)
        # Auto-scroll to bottom
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )
    
    def clear_output(self):
        """Clear the output area"""
        self.output_text.clear()

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
    
    def __init__(self):
        super().__init__()

        # Load custom font
        QFontDatabase.addApplicationFont("assets/Quicksand-Bold.ttf")

        # self.setFixedSize(QSize(1024,600))  # Commented out for fullscreen mode
        self.setWindowTitle("Test")

        # Create main widget with stacked layout
        self.stack = QStackedWidget()
        
        # Create pages
        self.home_page = self.create_home_page()
        self.settings_page = self.create_settings_page()
        
        # Add pages to stack
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.settings_page)
        
        self.setCentralWidget(self.stack)
        
        # Error state tracking for refresh countdown (must be initialized before first data load)
        self.refresh_error_message = None
        
        # Initialize settings with config values
        self.initialize_settings_from_config()
        
        # Initial load of arrivals data
        try:
            self.update_arrivals_display()
        except MetroAPIError as e:
            # Store error for display in countdown
            self.refresh_error_message = str(e)
        
        # Set up auto-refresh timer (30 seconds)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_arrivals)
        self.refresh_timer.start(30000)  # 30000ms = 30 seconds
        
        # Set up countdown timer (updates every second)
        self.seconds_until_refresh = 30
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_timer.start(1000)  # 1000ms = 1 second
        
        # Update button state management
        self.git_process = None
        self.git_output = ""
        self.checking_animation_timer = QTimer()
        self.checking_animation_timer.timeout.connect(self.update_checking_animation)
        self.checking_animation_state = 0
    
    def eventFilter(self, obj, event):
        """Event filter to handle hover events on IP button"""
        if obj == self.ip_button:
            if event.type() == QEvent.Enter:
                self.show_ip_popout()
            elif event.type() == QEvent.Leave:
                if hasattr(self, 'ip_popout'):
                    self.ip_popout.hide()
        return super().eventFilter(obj, event)
    
    def get_device_ip(self):
        """Get the local IP address of the device"""
        try:
            # Create a socket to determine the local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connect to an external address (doesn't actually send data)
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
            s.close()
            return ip_address
        except Exception:
            return "Unable to detect"
    
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
    
    def open_settings_page(self):
        """Open settings page and reload values from config"""
        # Reload dropdowns from config (now using cache, so it's fast)
        self.initialize_settings_from_config()
        # Switch to settings page
        self.stack.setCurrentIndex(1)
    
    def close_settings_page(self):
        """Close settings page"""
        # Just switch to home page
        self.stack.setCurrentIndex(0)
    
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
    
    def on_direction_selected(self, index):
        """Handle direction selection change"""
        # Direction selection doesn't trigger any cascading updates
        pass
    
    def populate_stations(self, line_code):
        """Populate station dropdown based on selected line"""
        # Clear current stations and directions
        self.station_combo.clear()
        self.direction_combo.clear()
        
        if not line_code:
            return
        
        # Get stations for the selected line (uses cache, auto-fetches if needed)
        try:
            stations_data = data_handler.get_cached_stations(line_code)
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
        """Populate direction dropdown with unique destinations from station predictions"""
        # Clear current directions
        self.direction_combo.clear()
        
        if not station_code:
            return
        
        # Get predictions for the selected station (uses cache, auto-fetches if needed)
        try:
            predictions_data = data_handler.get_cached_predictions(station_code)
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
                    
                    self.direction_combo.addItem(icon, destination)
        except MetroAPIError as e:
            # Store error for display in countdown
            self.refresh_error_message = str(e)
    
    def get_config_last_saved(self):
        """Get the last modified timestamp of the config file"""
        config_path = "config.json"
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
    
    def save_settings(self):
        """Manually save current settings to config file"""
        current_index = self.line_combo.currentIndex()
        if current_index >= 0:
            line_code = self.line_combo.itemData(current_index)
            config_handler.save_config('selected_line', line_code)
        
        station_index = self.station_combo.currentIndex()
        if station_index >= 0:
            station_code = self.station_combo.itemData(station_index)
            config_handler.save_config('selected_station', station_code)
        
        direction_index = self.direction_combo.currentIndex()
        if direction_index >= 0:
            destination = self.direction_combo.currentText()
            config_handler.save_config('selected_destination', destination)
        
        # Save countdown visibility setting
        config_handler.save_config('show_countdown', self.show_countdown_checkbox.isChecked())
        
        # Save filter by direction setting
        config_handler.save_config('filter_by_direction', self.filter_by_direction_checkbox.isChecked())
        
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
        self.direction_combo.clear()
        
        # Load config
        config = config_handler.load_config()
        
        # Load and apply countdown visibility setting
        show_countdown = config.get('show_countdown', True)  # Default to True
        self.show_countdown_checkbox.setChecked(show_countdown)
        if show_countdown:
            self.refresh_countdown_label.show()
        else:
            self.refresh_countdown_label.hide()
        
        # Load and apply filter by direction setting
        filter_by_direction = config.get('filter_by_direction', False)  # Default to False (show all)
        self.filter_by_direction_checkbox.setChecked(filter_by_direction)

        # Populate lines
        lines_data = data_handler.get_cached_lines()

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
                            
                            # Set direction from config
                            selected_destination = config.get('selected_destination')
                            if selected_destination:
                                direction_index = self.direction_combo.findText(selected_destination)
                                if direction_index >= 0:
                                    self.direction_combo.setCurrentIndex(direction_index)
        
        # Hide unsaved warning after initialization (signals may have triggered it)
        self.unsaved_warning_label.hide()


    
    def create_arrival_row(self, index):
        """Create a single arrival row widget"""
        row = QWidget()
        
        # Alternating background colors - slightly darker for odd rows
        bg_color = "#ffffff" if index % 2 == 0 else "#f5f5f5"
        row.setStyleSheet(f"background-color: {bg_color};")
        row.setFixedHeight(95)
        
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
        destination_label.setStyleSheet("font-family: Quicksand; font-size: 28px; font-weight: bold;")
        row_layout.addWidget(destination_label, alignment=Qt.AlignVCenter)
        row_layout.addStretch()
        
        # Arrival time on the right
        time_label = QLabel("—")
        time_label.setStyleSheet("font-family: Quicksand; font-size: 28px; font-weight: bold;")
        row_layout.addWidget(time_label, alignment=Qt.AlignVCenter)
        
        row.setLayout(row_layout)
        
        # Store references to labels for easy updating
        row.circle_label = circle_label
        row.destination_label = destination_label
        row.time_label = time_label
        
        return row
    
    def update_arrivals_display(self):
        """Update the arrivals display with latest prediction data"""
        # Get selected station from config
        config = config_handler.load_config()
        station_id = config.get('selected_station')
        
        if not station_id:
            # No station configured, show empty rows
            for row in self.arrival_rows:
                row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                row.destination_label.setText("—")
                row.time_label.setText("—")
            return
        
        # Get predictions for the selected station
        try:
            predictions_data = data_handler.get_cached_predictions(station_id)
        except MetroAPIError as e:
            # Store error for display in countdown
            self.refresh_error_message = str(e)
            # Show empty rows when error occurs
            for row in self.arrival_rows:
                row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                row.destination_label.setText("—")
                row.time_label.setText("—")
            return
        
        if predictions_data is None or predictions_data.empty:
            # No data available, show empty rows
            for row in self.arrival_rows:
                row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                row.destination_label.setText("No arrivals")
                row.time_label.setText("—")
            return
        
        # Apply filtering if enabled
        if self.filter_by_direction_checkbox.isChecked():
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
        for i, row in enumerate(self.arrival_rows):
            if i < len(sorted_predictions):
                prediction = sorted_predictions[i]
                
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
                else:
                    time_text = str(min_val)
                row.time_label.setText(time_text)
            else:
                # No more predictions, show empty row
                row.circle_label.setStyleSheet("background-color: #cccccc; border-radius: 10px;")
                row.destination_label.setText("—")
                row.time_label.setText("—")
    
    def refresh_arrivals(self):
        """Refresh arrivals data from API and update display"""
        # Get selected station from config
        config = config_handler.load_config()
        station_id = config.get('selected_station')
        
        if station_id:
            try:
                # Fetch fresh predictions from API
                data_handler.fetch_predictions(station_id)
                # Clear error message on success
                self.refresh_error_message = None
            except MetroAPIError as e:
                # Store error message for display
                self.refresh_error_message = str(e)
        
        # Update the display
        self.update_arrivals_display()
        
        # Reset countdown
        self.seconds_until_refresh = 30
    
    def update_countdown(self):
        """Update the countdown label"""
        self.seconds_until_refresh -= 1
        
        if self.seconds_until_refresh <= 0:
            self.seconds_until_refresh = 30
        
        # Update the label text and styling based on error state
        if self.refresh_error_message:
            # Display error message with red background
            self.refresh_countdown_label.setText(
                f"Error Refreshing: {self.refresh_error_message} Trying again in {self.seconds_until_refresh}s"
            )
            self.refresh_countdown_label.setStyleSheet(
                "font-family: Quicksand; font-size: 14px; color: white; background-color: #e74c3c; padding: 5px; border-radius: 3px;"
            )
        else:
            # Normal countdown display
            self.refresh_countdown_label.setText(f"Refresh in {self.seconds_until_refresh}s")
            self.refresh_countdown_label.setStyleSheet("font-family: Quicksand; font-size: 14px; color: #666;")
    
    def toggle_countdown_visibility(self):
        """Toggle the visibility of the countdown label"""
        if self.show_countdown_checkbox.isChecked():
            self.refresh_countdown_label.show()
        else:
            self.refresh_countdown_label.hide()
    
    def show_ip_popout(self):
        """Show the IP popout near the IP button"""
        if not hasattr(self, 'ip_popout'):
            ip_address = self.get_device_ip()
            self.ip_popout = IPPopout(ip_address, self.settings_page)
        
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
            self.run_git_pull()
        elif button_text == "Restart":
            # Restart the application
            self.restart_application()
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
            self.update_popout = UpdatePopout(self.settings_page)
            self.update_popout.close_button.clicked.connect(self.close_update_popout)
        
        # Clear previous output
        self.update_popout.clear_output()
        
        # Position the popout above the Update button
        button_pos = self.update_button.mapTo(self.settings_page, self.update_button.rect().topLeft())
        popout_x = button_pos.x()
        popout_y = button_pos.y() - self.update_popout.height() - 10  # 10px gap above button
        
        self.update_popout.move(popout_x, popout_y)
        self.update_popout.show()
    
    def close_update_popout(self):
        """Close the update popout and reset state"""
        # Kill git process if still running
        if self.git_process is not None and self.git_process.state() == QProcess.Running:
            self.git_process.kill()
            self.git_process.waitForFinished()
        
        # Stop animation timer
        self.checking_animation_timer.stop()
        
        # Reset button text and color
        self.update_button.setText("Update")
        self.set_update_button_color("green")
        
        # Hide popout
        if hasattr(self, 'update_popout'):
            self.update_popout.hide()
    
    def set_update_button_color(self, color):
        """Set the update button color"""
        if color == "green":
            self.update_button.setStyleSheet("""
                QPushButton {
                    font-family: Quicksand;
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QPushButton:pressed {
                    background-color: #3d8b40;
                    padding-bottom: 7px;
                }
            """)
        elif color == "orange":
            self.update_button.setStyleSheet("""
                QPushButton {
                    font-family: Quicksand;
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #FFC107;
                    color: white;
                    border: none;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #FFB300;
                }
                QPushButton:pressed {
                    background-color: #FFA000;
                    padding-bottom: 7px;
                }
            """)
        elif color == "red":
            self.update_button.setStyleSheet("""
                QPushButton {
                    font-family: Quicksand;
                    font-size: 20px;
                    font-weight: bold;
                    padding: 8px 16px;
                    background-color: #f44336;
                    color: white;
                    border: none;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #da190b;
                }
                QPushButton:pressed {
                    background-color: #c1170a;
                    padding-bottom: 7px;
                }
            """)
    
    def run_git_pull(self):
        """Start the git pull process"""
        # Change button text, color, and start animation
        self.update_button.setText("Checking")
        self.set_update_button_color("orange")
        self.checking_animation_state = 0
        self.checking_animation_timer.start(500)  # Update every 500ms
        
        # Clear git output
        self.git_output = ""
        
        # Create and configure QProcess
        self.git_process = QProcess()
        self.git_process.setWorkingDirectory(os.path.dirname(os.path.abspath(__file__)))
        
        # Connect signals
        self.git_process.readyReadStandardOutput.connect(self.on_git_output_ready)
        self.git_process.readyReadStandardError.connect(self.on_git_output_ready)
        self.git_process.finished.connect(self.on_git_finished)
        
        # Start git pull
        self.update_popout.append_output("Running git pull...\n")
        self.git_process.start("git", ["pull"])
    
    def on_git_output_ready(self):
        """Handle output from git process"""
        if self.git_process is None:
            return
        
        # Read stdout
        stdout = self.git_process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        if stdout:
            self.git_output += stdout
            # Remove trailing newline for display to avoid double spacing
            self.update_popout.append_output(stdout.rstrip('\n'))
        
        # Read stderr
        stderr = self.git_process.readAllStandardError().data().decode('utf-8', errors='replace')
        if stderr:
            self.git_output += stderr
            self.update_popout.append_output(stderr.rstrip('\n'))
    
    def on_git_finished(self, exit_code, exit_status):
        """Handle git process completion"""
        # Stop animation timer
        self.checking_animation_timer.stop()
        
        # Append completion message
        self.update_popout.append_output(f"\nProcess finished with exit code: {exit_code}")
        
        # Check for errors
        if exit_code != 0 or self.has_git_error():
            self.update_button.setText("Error Updating")
            self.set_update_button_color("red")
        else:
            # Check if updates were found
            has_updates = self.parse_git_output()
            
            if has_updates:
                self.update_button.setText("Restart")
                self.set_update_button_color("orange")  # Stay orange to indicate action needed
            else:
                self.update_button.setText("Up to date!")
                self.set_update_button_color("green")
    
    def has_git_error(self):
        """Check if git output contains error indicators"""
        output_lower = self.git_output.lower()
        error_indicators = [
            "error:",
            "fatal:",
            "could not",
            "failed to",
            "permission denied",
            "cannot"
        ]
        
        for indicator in error_indicators:
            if indicator in output_lower:
                return True
        
        return False
    
    def parse_git_output(self):
        """Parse git output to determine if updates occurred"""
        output_lower = self.git_output.lower()
        
        # Check for "already up to date" or "already up-to-date"
        if "already up to date" in output_lower or "already up-to-date" in output_lower:
            return False
        
        # Check for indicators of updates
        update_indicators = [
            "updating",
            "fast-forward",
            "files changed",
            "file changed",
            "insertions",
            "deletions"
        ]
        
        for indicator in update_indicators:
            if indicator in output_lower:
                return True
        
        # If exit code was 0 and we have output but no "already up to date", assume updates
        if self.git_output and "error" not in output_lower and "fatal" not in output_lower:
            # Check if there's actual content beyond just "From" lines
            lines = [line.strip() for line in self.git_output.split('\n') if line.strip()]
            substantial_lines = [line for line in lines if not line.startswith('From') and not line.startswith('remote:')]
            if len(substantial_lines) > 1:  # More than just the git pull command echo
                return True
        
        return False
    
    def update_checking_animation(self):
        """Update the button text for checking animation"""
        animations = ["Checking", "Checking.", "Checking..", "Checking..."]
        self.update_button.setText(animations[self.checking_animation_state])
        self.checking_animation_state = (self.checking_animation_state + 1) % len(animations)
    
    def restart_application(self):
        """Restart the application"""
        # Close the update popout
        if hasattr(self, 'update_popout'):
            self.update_popout.hide()
        
        # Get the current script path
        script_path = os.path.abspath(__file__)
        
        # Restart using os.execv (replaces current process)
        python = sys.executable
        os.execv(python, [python, script_path])
    
    def create_title_bar(self, button_widget, countdown_label=None):
        """Create a title bar with the given button on the right"""
        title_bar = QWidget()
        title_bar.setStyleSheet("background-color: lightgray;")
        title_bar.setFixedHeight(75)
        
        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(20, 0, 20, 0)
        
        # Add title label
        title_label = QLabel("Nicole's Train Tables")
        title_label.setStyleSheet("font-family: Quicksand; font-size: 30px; font-weight: bold;")
        title_bar_layout.addWidget(title_label, alignment=Qt.AlignVCenter)
        
        # Add stretch to push items to the right
        title_bar_layout.addStretch()
        
        # Add countdown label if provided
        if countdown_label:
            title_bar_layout.addWidget(countdown_label, alignment=Qt.AlignVCenter)
            title_bar_layout.addSpacing(15)
        
        # Add button
        title_bar_layout.addWidget(button_widget, alignment=Qt.AlignVCenter)
        
        title_bar.setLayout(title_bar_layout)
        return title_bar
    
    def create_home_page(self):
        """Create the home page"""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create countdown label
        self.refresh_countdown_label = QLabel("Refresh in 30s")
        self.refresh_countdown_label.setStyleSheet("font-family: Quicksand; font-size: 14px; color: #666;")
        self.refresh_countdown_label.setMaximumWidth(500)  # Prevent overlap with title and buttons
        self.refresh_countdown_label.setWordWrap(True)  # Allow text to wrap to multiple lines
        
        # Create settings button
        settings_button = QPushButton("⚙")
        settings_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
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
        """)
        settings_button.setFixedHeight(45)
        settings_button.clicked.connect(self.open_settings_page)
        
        # Create close button
        close_button = QPushButton("✕")
        close_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
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
        """)
        close_button.setFixedHeight(45)
        close_button.clicked.connect(QApplication.instance().quit)
        
        # Create container widget for both buttons
        buttons_container = QWidget()
        buttons_container.setStyleSheet("background-color: lightgray;")
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10)
        buttons_layout.addWidget(settings_button)
        buttons_layout.addWidget(close_button)
        buttons_container.setLayout(buttons_layout)
        
        # Add title bar
        layout.addWidget(self.create_title_bar(buttons_container, self.refresh_countdown_label))
        
        # Add content
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(0)
        
        # Create 5 arrival rows
        self.arrival_rows = []
        for i in range(5):
            row = self.create_arrival_row(i)
            self.arrival_rows.append(row)
            content_layout.addWidget(row)
        
        content_layout.addStretch()
        
        content_widget = QWidget()
        content_widget.setLayout(content_layout)
        layout.addWidget(content_widget)
        
        page.setLayout(layout)
        return page
    
    def create_settings_page(self):
        """Create the settings page"""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create back button
        back_button = QPushButton("←")
        back_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
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
        """)
        back_button.setFixedHeight(45)
        back_button.clicked.connect(self.close_settings_page)
        
        # Add title bar
        layout.addWidget(self.create_title_bar(back_button))
        
        # Add settings subtitle
        content_layout = QVBoxLayout()
        settings_label = QLabel("Settings")
        settings_label.setStyleSheet("font-family: Quicksand; font-size: 28px; font-weight: bold;")
        settings_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(settings_label)
        
        # Add line selector
        line_selector_layout = QHBoxLayout()
        line_selector_layout.setContentsMargins(40, 20, 40, 0)
        
        line_selector_layout.addStretch()
        
        line_label = QLabel("Select Line:")
        line_label.setStyleSheet("font-family: Quicksand; font-size: 21px; font-weight: bold;")
        line_selector_layout.addWidget(line_label)
        
        self.line_combo = QComboBox()
        self.line_combo.setStyleSheet("""
            QComboBox {
                font-family: Quicksand;
                font-size: 18px;
                padding: 7px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
            }
            QComboBox:hover {
                border: 1px solid #999;
            }
        """)
        self.line_combo.setMinimumWidth(265)
        
        # Connect selection change to save config (connect before populating to ensure signals work)
        self.line_combo.currentIndexChanged.connect(self.on_line_selected)
        self.line_combo.currentIndexChanged.connect(self.mark_settings_changed)
        
        line_selector_layout.addWidget(self.line_combo)
        
        # Add disclaimer label
        line_disclaimer_label = QLabel("(for finding station only)")
        line_disclaimer_label.setStyleSheet("font-family: Quicksand; font-size: 14px; color: #666;")
        line_selector_layout.addWidget(line_disclaimer_label)
        
        line_selector_layout.addStretch()
        
        content_layout.addLayout(line_selector_layout)
        
        # Add station selector
        station_selector_layout = QHBoxLayout()
        station_selector_layout.setContentsMargins(40, 20, 40, 0)
        
        station_selector_layout.addStretch()
        
        station_label = QLabel("Select Station:")
        station_label.setStyleSheet("font-family: Quicksand; font-size: 21px; font-weight: bold;")
        station_selector_layout.addWidget(station_label)
        
        self.station_combo = QComboBox()
        self.station_combo.setStyleSheet("""
            QComboBox {
                font-family: Quicksand;
                font-size: 18px;
                padding: 7px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
            }
            QComboBox:hover {
                border: 1px solid #999;
            }
        """)
        self.station_combo.setMinimumWidth(265)
        
        # Connect selection change to save config
        self.station_combo.currentIndexChanged.connect(self.on_station_selected)
        self.station_combo.currentIndexChanged.connect(self.mark_settings_changed)
        
        station_selector_layout.addWidget(self.station_combo)
        station_selector_layout.addStretch()
        
        content_layout.addLayout(station_selector_layout)
        
        # Add direction selector
        direction_selector_layout = QHBoxLayout()
        direction_selector_layout.setContentsMargins(40, 20, 40, 0)
        
        direction_selector_layout.addStretch()
        
        direction_label = QLabel("Select Direction:")
        direction_label.setStyleSheet("font-family: Quicksand; font-size: 21px; font-weight: bold;")
        direction_selector_layout.addWidget(direction_label)
        
        self.direction_combo = QComboBox()
        self.direction_combo.setStyleSheet("""
            QComboBox {
                font-family: Quicksand;
                font-size: 18px;
                padding: 7px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
            }
            QComboBox:hover {
                border: 1px solid #999;
            }
        """)
        self.direction_combo.setMinimumWidth(265)
        
        # Connect selection change to save config
        self.direction_combo.currentIndexChanged.connect(self.on_direction_selected)
        self.direction_combo.currentIndexChanged.connect(self.mark_settings_changed)
        
        direction_selector_layout.addWidget(self.direction_combo)
        direction_selector_layout.addStretch()
        
        content_layout.addLayout(direction_selector_layout)
        
        # Add countdown visibility checkbox
        countdown_checkbox_layout = QHBoxLayout()
        countdown_checkbox_layout.setContentsMargins(40, 20, 40, 0)
        
        countdown_checkbox_layout.addStretch()
        
        countdown_label = QLabel("Show Time to Refresh:")
        countdown_label.setStyleSheet("font-family: Quicksand; font-size: 21px; font-weight: bold;")
        countdown_checkbox_layout.addWidget(countdown_label)
        
        self.show_countdown_checkbox = QCheckBox()
        self.show_countdown_checkbox.setStyleSheet("""
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
        """)
        self.show_countdown_checkbox.setChecked(True)  # Default to checked
        
        # Connect checkbox to toggle method
        self.show_countdown_checkbox.stateChanged.connect(self.toggle_countdown_visibility)
        self.show_countdown_checkbox.stateChanged.connect(self.mark_settings_changed)
        
        countdown_checkbox_layout.addWidget(self.show_countdown_checkbox)
        countdown_checkbox_layout.addStretch()
        
        content_layout.addLayout(countdown_checkbox_layout)
        
        # Add filter by direction checkbox
        filter_checkbox_layout = QHBoxLayout()
        filter_checkbox_layout.setContentsMargins(40, 20, 40, 0)
        
        filter_checkbox_layout.addStretch()
        
        filter_label = QLabel("Filter by Selected Direction:")
        filter_label.setStyleSheet("font-family: Quicksand; font-size: 21px; font-weight: bold;")
        filter_checkbox_layout.addWidget(filter_label)
        
        self.filter_by_direction_checkbox = QCheckBox()
        self.filter_by_direction_checkbox.setStyleSheet("""
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
        """)
        self.filter_by_direction_checkbox.setChecked(False)  # Default to unchecked (show all)
        
        # Connect checkbox to refresh arrivals
        self.filter_by_direction_checkbox.stateChanged.connect(self.update_arrivals_display)
        self.filter_by_direction_checkbox.stateChanged.connect(self.mark_settings_changed)
        
        filter_checkbox_layout.addWidget(self.filter_by_direction_checkbox)
        filter_checkbox_layout.addStretch()
        
        content_layout.addLayout(filter_checkbox_layout)
        
        # Add save button
        save_button_layout = QHBoxLayout()
        save_button_layout.setContentsMargins(40, 20, 40, 0)
        save_button_layout.addStretch()
        
        save_button = QPushButton("Save Settings")
        save_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 20px;
                font-weight: bold;
                padding: 12px 36px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
                padding-bottom: 11px;
            }
        """)
        save_button.clicked.connect(self.save_settings)
        
        save_button_layout.addWidget(save_button)
        save_button_layout.addStretch()
        
        content_layout.addLayout(save_button_layout)
        
        # Add timestamp label below the save button
        timestamp_layout = QHBoxLayout()
        timestamp_layout.setContentsMargins(40, 10, 40, 0)
        timestamp_layout.addStretch()
        
        self.timestamp_label = QLabel()
        self.timestamp_label.setStyleSheet("font-family: Quicksand; font-size: 14px; color: #666;")
        self.timestamp_label.setAlignment(Qt.AlignCenter)
        self.update_timestamp_label()
        timestamp_layout.addWidget(self.timestamp_label)
        
        # Add unsaved changes warning label
        self.unsaved_warning_label = QLabel("Changes not yet saved!")
        self.unsaved_warning_label.setStyleSheet("font-family: Quicksand; font-size: 14px; color: #e74c3c;")
        self.unsaved_warning_label.setAlignment(Qt.AlignCenter)
        self.unsaved_warning_label.hide()  # Initially hidden
        timestamp_layout.addWidget(self.unsaved_warning_label)
        
        timestamp_layout.addStretch()
        
        content_layout.addLayout(timestamp_layout)
        content_layout.addStretch()
        content_layout.addSpacing(-30)  # Move buttons up
        
        # Add IP and Update buttons at bottom left
        ip_button_layout = QHBoxLayout()
        ip_button_layout.setContentsMargins(20, 10, 40, 20)
        
        self.ip_button = QPushButton("ⓘ")
        self.ip_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 20px;
                font-weight: bold;
                padding: 8px 12px;
                background-color: #e0e0e0;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #c0c0c0;
                padding-bottom: 7px;
            }
        """)
        # Install event filter to detect hover
        self.ip_button.installEventFilter(self)
        ip_button_layout.addWidget(self.ip_button)
        
        # Add Update button
        self.update_button = QPushButton("Update")
        self.update_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 20px;
                font-weight: bold;
                padding: 8px 16px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
                padding-bottom: 7px;
            }
        """)
        self.update_button.clicked.connect(self.on_update_button_clicked)
        ip_button_layout.addWidget(self.update_button)
        
        ip_button_layout.addStretch()
        
        content_layout.addLayout(ip_button_layout)
        
        content_widget = QWidget()
        content_widget.setLayout(content_layout)
        layout.addWidget(content_widget)
        
        page.setLayout(layout)
        return page

# Load configuration and initialize API
config = config_handler.load_config()
metro_api = MetroAPI(config['api_key'])

# Initialize data handler
data_handler = DataHandler(metro_api)

# Fetch lines data on startup
try:
    data_handler.fetch_lines()
except MetroAPIError:
    # Suppress error during startup - will be shown in UI if needed
    pass

app = QApplication([])

window = MainWindow()
window.showFullScreen()

app.exec()