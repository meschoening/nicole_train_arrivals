#!/usr/bin/env python3
"""
WiFi Configuration Setup Application

A fullscreen PyQt5 application for configuring WiFi networks on DietPi.
Launched from main_display.py when no WiFi connection is detected.
"""

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QWidget, QPushButton, QSizePolicy, QComboBox, QPlainTextEdit,
    QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, QProcess
from PyQt5.QtGui import QFontDatabase
import os
import sys
import subprocess
import argparse
import threading


class WiFiSetupWindow(QMainWindow):
    """Main window for WiFi configuration setup."""
    
    def __init__(self):
        super().__init__()
        
        # Load custom font
        QFontDatabase.addApplicationFont("assets/Quicksand-Bold.ttf")
        
        self.title_text = "WiFi Configuration"
        self.setWindowTitle(self.title_text)
        
        # Hide cursor for touchscreen kiosk mode
        self.setCursor(Qt.BlankCursor)
        
        # AP state tracking
        self.is_broadcasting = False
        self.portal_server_thread = None
        self.portal_server_running = False
        
        # Manual connection state tracking
        self.is_connecting = False
        self.is_manually_connected = False
        self.connection_process = None
        
        # Create main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header bar
        header = self.create_header_bar()
        main_layout.addWidget(header)
        
        # Content area (wrapped in scroll area for safety)
        content = self.create_content_area()
        scroll_area = QScrollArea()
        scroll_area.setWidget(content)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setStyleSheet("background-color: #f0f0f0;")
        main_layout.addWidget(scroll_area, 1)  # stretch factor 1
        
        # Footer bar
        footer = self.create_footer_bar()
        main_layout.addWidget(footer)
        
        main_widget.setLayout(main_layout)
        main_widget.setStyleSheet("background-color: lightgray;")
        
        # Initial status update
        self.update_status_labels()
        
        # Timer to periodically update status
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_labels)
        self.status_timer.start(5000)  # Update every 5 seconds
    
    def create_header_bar(self):
        """Create the header bar with title."""
        header = QWidget()
        header.setStyleSheet("background-color: lightgray;")
        header.setFixedHeight(75)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 0, 20, 0)
        
        # Title label
        title_label = QLabel(self.title_text)
        title_label.setStyleSheet("font-family: Quicksand; font-size: 30px; font-weight: bold;")
        layout.addWidget(title_label, alignment=Qt.AlignVCenter | Qt.AlignLeft)
        
        layout.addStretch()
        
        header.setLayout(layout)
        return header
    
    def create_content_area(self):
        """Create the main content area with status labels and manual connection."""
        content = QWidget()
        content.setStyleSheet("background-color: #f0f0f0;")
        
        # Outer vertical layout to control expansion
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(40, 15, 40, 15)
        outer_layout.setSpacing(20)
        
        # Inner horizontal layout for two columns
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(20)
        
        # ===== LEFT COLUMN: Status Section =====
        status_container = QWidget()
        status_container.setStyleSheet("""
            background-color: #e8e8e8;
            border-radius: 10px;
        """)
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(30, 30, 30, 30)
        status_layout.setSpacing(15)
        
        # Status label
        status_row = QHBoxLayout()
        status_title = QLabel("Status:")
        status_title.setStyleSheet("font-family: Quicksand; font-size: 24px; font-weight: bold;")
        status_title.setFixedWidth(150)
        self.status_value = QLabel("Checking...")
        self.status_value.setStyleSheet("font-family: Quicksand; font-size: 24px;")
        status_row.addWidget(status_title)
        status_row.addWidget(self.status_value)
        status_row.addStretch()
        status_layout.addLayout(status_row)
        
        # AP Name label
        ap_row = QHBoxLayout()
        ap_title = QLabel("AP Name:")
        ap_title.setStyleSheet("font-family: Quicksand; font-size: 24px; font-weight: bold;")
        ap_title.setFixedWidth(150)
        self.ap_name_value = QLabel("—")
        self.ap_name_value.setStyleSheet("font-family: Quicksand; font-size: 24px;")
        ap_row.addWidget(ap_title)
        ap_row.addWidget(self.ap_name_value)
        ap_row.addStretch()
        status_layout.addLayout(ap_row)
        
        # IP Address label
        ip_row = QHBoxLayout()
        ip_title = QLabel("IP Address:")
        ip_title.setStyleSheet("font-family: Quicksand; font-size: 24px; font-weight: bold;")
        ip_title.setFixedWidth(150)
        self.ip_value = QLabel("—")
        self.ip_value.setStyleSheet("font-family: Quicksand; font-size: 24px;")
        ip_row.addWidget(ip_title)
        ip_row.addWidget(self.ip_value)
        ip_row.addStretch()
        status_layout.addLayout(ip_row)
        
        # Connection result (shown after stopping broadcast)
        self.connection_result_label = QLabel("")
        self.connection_result_label.setStyleSheet("font-family: Quicksand; font-size: 20px; color: #666;")
        self.connection_result_label.setWordWrap(True)
        self.connection_result_label.hide()
        status_layout.addWidget(self.connection_result_label)
        
        status_layout.addStretch()
        status_container.setLayout(status_layout)
        columns_layout.addWidget(status_container, 1)  # stretch factor 1
        
        # ===== RIGHT COLUMN: Manual Connection Section =====
        manual_container = QWidget()
        manual_container.setStyleSheet("""
            background-color: #e8e8e8;
            border-radius: 10px;
        """)
        manual_layout = QVBoxLayout()
        manual_layout.setContentsMargins(30, 30, 30, 30)
        manual_layout.setSpacing(15)
        
        # Section title
        manual_title = QLabel("Manual Connection")
        manual_title.setStyleSheet("font-family: Quicksand; font-size: 22px; font-weight: bold;")
        manual_layout.addWidget(manual_title)
        
        # Saved networks dropdown
        self.saved_networks_combo = QComboBox()
        self.saved_networks_combo.setStyleSheet("""
            QComboBox {
                font-family: Quicksand;
                font-size: 18px;
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: white;
            }
            QComboBox:hover {
                border: 1px solid #999;
            }
            QComboBox QAbstractItemView {
                font-family: Quicksand;
                font-size: 18px;
                background-color: white;
                selection-background-color: #e0e0e0;
            }
        """)
        manual_layout.addWidget(self.saved_networks_combo)
        
        # Refresh List button
        self.refresh_networks_button = QPushButton("Refresh List")
        self.refresh_networks_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 16px;
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
            }
        """)
        self.refresh_networks_button.clicked.connect(self.load_saved_networks)
        manual_layout.addWidget(self.refresh_networks_button)
        
        # Connect/Disconnect button
        self.connect_button = QPushButton("Connect to Network")
        self.connect_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 16px;
                font-weight: bold;
                padding: 10px 20px;
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
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.connect_button.clicked.connect(self.toggle_manual_connection)
        manual_layout.addWidget(self.connect_button)
        
        # Console output
        
        self.connection_console = QPlainTextEdit()
        self.connection_console.setReadOnly(True)
        self.connection_console.setStyleSheet("""
            QPlainTextEdit {
                font-family: monospace;
                font-size: 14px;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        manual_layout.addWidget(self.connection_console, 1)  # stretch factor 1
        
        manual_container.setLayout(manual_layout)
        columns_layout.addWidget(manual_container, 1)  # stretch factor 1
        
        # Add the columns to the outer layout
        outer_layout.addLayout(columns_layout)
        outer_layout.addStretch()  # Push content up, keep footer at bottom
        
        # Load saved networks on startup
        QTimer.singleShot(500, self.load_saved_networks)
        
        content.setLayout(outer_layout)
        return content
    
    def create_footer_bar(self):
        """Create the footer bar with action buttons."""
        footer = QWidget()
        footer.setStyleSheet("background-color: lightgray;")
        footer.setFixedHeight(75)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(20)
        
        # Broadcast button (left-aligned)
        self.broadcast_button = QPushButton("Broadcast")
        self.broadcast_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 18px;
                font-weight: bold;
                padding: 10px 25px;
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
        """)
        self.broadcast_button.setFixedHeight(45)
        self.broadcast_button.clicked.connect(self.toggle_broadcast)
        layout.addWidget(self.broadcast_button, alignment=Qt.AlignVCenter | Qt.AlignLeft)
        
        layout.addStretch()
        
        # Return to Main Display button (right-aligned)
        return_button = QPushButton("Return to Main Display")
        return_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 18px;
                font-weight: bold;
                padding: 10px 25px;
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
        """)
        return_button.setFixedHeight(45)
        return_button.clicked.connect(self.return_to_main_display)
        layout.addWidget(return_button, alignment=Qt.AlignVCenter | Qt.AlignRight)
        
        footer.setLayout(layout)
        return footer
    
    def update_status_labels(self):
        """Update the status labels based on current network state."""
        try:
            if self.is_broadcasting:
                self.status_value.setText("AP Mode (Broadcasting)")
                self.status_value.setStyleSheet("font-family: Quicksand; font-size: 24px; color: #2196F3;")
                self.ap_name_value.setText("NicoleTrains-Setup")
                self.ip_value.setText("192.168.4.1")
            else:
                # Check WiFi connection status
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                connected = False
                connection_name = ""
                
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        parts = line.split(':')
                        if len(parts) >= 3 and parts[0] == 'wifi':
                            if 'connected' in parts[1].lower() and parts[1].lower() != 'disconnected':
                                connected = True
                                connection_name = parts[2] if len(parts) > 2 else "Unknown"
                                break
                
                if connected:
                    self.status_value.setText(f"Connected ({connection_name})")
                    self.status_value.setStyleSheet("font-family: Quicksand; font-size: 24px; color: #4CAF50;")
                    self.ap_name_value.setText("—")
                    # Get current IP
                    ip = self.get_current_ip()
                    self.ip_value.setText(ip if ip else "—")
                else:
                    self.status_value.setText("Not Connected")
                    self.status_value.setStyleSheet("font-family: Quicksand; font-size: 24px; color: #cc0000;")
                    self.ap_name_value.setText("—")
                    self.ip_value.setText("—")
                    
        except Exception as e:
            print(f"Error updating status: {e}")
            self.status_value.setText("Error checking status")
            self.status_value.setStyleSheet("font-family: Quicksand; font-size: 24px; color: #cc0000;")
    
    def get_current_ip(self):
        """Get the current IP address of wlan0."""
        try:
            result = subprocess.run(
                ["ip", "-4", "addr", "show", "wlan0"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'inet ' in line:
                        # Extract IP address (format: inet 192.168.1.100/24 ...)
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            return parts[1].split('/')[0]
            return None
        except Exception:
            return None
    
    def load_saved_networks(self):
        """Load saved WiFi networks into the dropdown."""
        try:
            self.saved_networks_combo.clear()
            result = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                networks = []
                for line in result.stdout.strip().split('\n'):
                    if not line.strip():
                        continue
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[1] == "802-11-wireless":
                        networks.append(parts[0])
                
                if networks:
                    self.saved_networks_combo.addItems(networks)
                    self.connection_console.appendPlainText(f"Found {len(networks)} saved network(s)")
                else:
                    self.saved_networks_combo.addItem("(No saved networks)")
                    self.connection_console.appendPlainText("No saved WiFi networks found")
            else:
                self.saved_networks_combo.addItem("(Error loading)")
                self.connection_console.appendPlainText(f"Error: {result.stderr.strip()}")
                
        except Exception as e:
            self.saved_networks_combo.addItem("(Error loading)")
            self.connection_console.appendPlainText(f"Exception: {e}")
    
    def toggle_manual_connection(self):
        """Toggle between connect and disconnect based on current state."""
        if self.is_connecting:
            return  # Already in progress
        
        if self.is_manually_connected:
            self.disconnect_network()
        else:
            self.attempt_connection()
    
    def attempt_connection(self):
        """Attempt to connect to the selected network asynchronously."""
        selected = self.saved_networks_combo.currentText()
        if not selected or selected.startswith("("):
            self.connection_console.appendPlainText("No valid network selected")
            return
        
        self.is_connecting = True
        self.connect_button.setEnabled(False)
        self.connect_button.setText("Connecting...")
        self.connect_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 16px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #cccccc;
                color: #666666;
                border: none;
                border-radius: 5px;
            }
        """)
        
        self.connection_console.clear()
        self.connection_console.appendPlainText(f"$ nmcli connection up \"{selected}\"")
        self.connection_console.appendPlainText("Connecting...")
        
        # Use QProcess for async execution
        self.connection_process = QProcess()
        self.connection_process.readyReadStandardOutput.connect(self.on_connection_output)
        self.connection_process.readyReadStandardError.connect(self.on_connection_error)
        self.connection_process.finished.connect(self.on_connection_finished)
        
        self.connection_process.start("nmcli", ["connection", "up", selected])
    
    def disconnect_network(self):
        """Disconnect from the current WiFi network."""
        self.is_connecting = True
        self.connect_button.setEnabled(False)
        self.connect_button.setText("Disconnecting...")
        
        self.connection_console.appendPlainText("\n$ nmcli device disconnect wlan0")
        self.connection_console.appendPlainText("Disconnecting...")
        
        # Use QProcess for async execution
        self.connection_process = QProcess()
        self.connection_process.readyReadStandardOutput.connect(self.on_connection_output)
        self.connection_process.readyReadStandardError.connect(self.on_connection_error)
        self.connection_process.finished.connect(self.on_disconnect_finished)
        
        self.connection_process.start("nmcli", ["device", "disconnect", "wlan0"])
    
    def on_connection_output(self):
        """Handle stdout from connection process."""
        if self.connection_process:
            output = self.connection_process.readAllStandardOutput().data().decode()
            if output.strip():
                self.connection_console.appendPlainText(output.strip())
    
    def on_connection_error(self):
        """Handle stderr from connection process."""
        if self.connection_process:
            output = self.connection_process.readAllStandardError().data().decode()
            if output.strip():
                self.connection_console.appendPlainText(f"Error: {output.strip()}")
    
    def on_connection_finished(self, exit_code, exit_status):
        """Handle connection attempt completion."""
        self.is_connecting = False
        self.connect_button.setEnabled(True)
        
        if exit_code == 0:
            self.is_manually_connected = True
            self.connection_console.appendPlainText("\n✓ Connection successful!")
            self.connect_button.setText("Disconnect")
            self.connect_button.setStyleSheet("""
                QPushButton {
                    font-family: Quicksand;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 10px 20px;
                    background-color: #f44336;
                    color: white;
                    border: none;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #da190b;
                }
                QPushButton:pressed {
                    background-color: #c41409;
                }
            """)
        else:
            self.is_manually_connected = False
            self.connection_console.appendPlainText(f"\n✗ Connection failed (exit code: {exit_code})")
            self.connect_button.setText("Connect to Network")
            self.connect_button.setStyleSheet("""
                QPushButton {
                    font-family: Quicksand;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 10px 20px;
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
                }
            """)
        
        # Update status labels
        self.update_status_labels()
    
    def on_disconnect_finished(self, exit_code, exit_status):
        """Handle disconnect completion."""
        self.is_connecting = False
        self.is_manually_connected = False
        self.connect_button.setEnabled(True)
        
        if exit_code == 0:
            self.connection_console.appendPlainText("\n✓ Disconnected successfully")
        else:
            self.connection_console.appendPlainText(f"\n✗ Disconnect failed (exit code: {exit_code})")
        
        self.connect_button.setText("Connect to Network")
        self.connect_button.setStyleSheet("""
            QPushButton {
                font-family: Quicksand;
                font-size: 16px;
                font-weight: bold;
                padding: 10px 20px;
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
            }
        """)
        
        # Update status labels
        self.update_status_labels()

    def toggle_broadcast(self):
        """Toggle between broadcast and normal mode."""
        if self.is_broadcasting:
            self.stop_broadcasting()
        else:
            self.start_broadcasting()
    
    def start_broadcasting(self):
        """Start AP mode and captive portal."""
        try:
            self.broadcast_button.setEnabled(False)
            self.broadcast_button.setText("Starting...")
            QApplication.processEvents()
            
            # Get script directory for config files
            script_dir = os.path.dirname(os.path.abspath(__file__))
            hostapd_conf = os.path.join(script_dir, "hostapd_provisioning.conf")
            
            # Step 1: Disconnect from any existing WiFi connection
            subprocess.run(["sudo", "nmcli", "device", "disconnect", "wlan0"], 
                          capture_output=True, timeout=10)
            
            # Step 2: Set static IP on wlan0
            subprocess.run([
                "sudo", "ip", "addr", "flush", "dev", "wlan0"
            ], capture_output=True, timeout=5)
            
            subprocess.run([
                "sudo", "ip", "addr", "add", "192.168.4.1/24", "dev", "wlan0"
            ], capture_output=True, timeout=5)
            
            subprocess.run([
                "sudo", "ip", "link", "set", "wlan0", "up"
            ], capture_output=True, timeout=5)
            
            # Step 3: Start dnsmasq
            subprocess.run([
                "sudo", "systemctl", "start", "dnsmasq"
            ], capture_output=True, timeout=10)
            
            # Step 4: Start hostapd with our config
            subprocess.run([
                "sudo", "hostapd", "-B", hostapd_conf
            ], capture_output=True, timeout=10)
            
            # Step 5: Start Flask captive portal
            self.start_portal_server()
            
            self.is_broadcasting = True
            self.broadcast_button.setText("Stop Broadcasting")
            self.broadcast_button.setEnabled(True)
            
            # Hide any previous connection result
            self.connection_result_label.hide()
            
            self.update_status_labels()
            
        except Exception as e:
            print(f"Error starting broadcast: {e}")
            self.broadcast_button.setText("Broadcast")
            self.broadcast_button.setEnabled(True)
            self.connection_result_label.setText(f"Error starting broadcast: {e}")
            self.connection_result_label.setStyleSheet("font-family: Quicksand; font-size: 20px; color: #cc0000;")
            self.connection_result_label.show()
    
    def stop_broadcasting(self):
        """Stop AP mode and attempt to reconnect to WiFi."""
        try:
            self.broadcast_button.setEnabled(False)
            self.broadcast_button.setText("Stopping...")
            QApplication.processEvents()
            
            # Step 1: Stop Flask portal
            self.stop_portal_server()
            
            # Step 2: Stop hostapd
            subprocess.run([
                "sudo", "killall", "hostapd"
            ], capture_output=True, timeout=10)
            
            # Step 3: Stop dnsmasq
            subprocess.run([
                "sudo", "systemctl", "stop", "dnsmasq"
            ], capture_output=True, timeout=10)
            
            # Step 4: Flush IP and return interface to managed mode
            subprocess.run([
                "sudo", "ip", "addr", "flush", "dev", "wlan0"
            ], capture_output=True, timeout=5)
            
            # Step 5: Restart NetworkManager to take control
            subprocess.run([
                "sudo", "systemctl", "restart", "NetworkManager"
            ], capture_output=True, timeout=15)
            
            # Wait a moment for NetworkManager to initialize
            import time
            time.sleep(2)
            
            # Step 6: Try to auto-connect to a saved network
            result = subprocess.run([
                "nmcli", "device", "wifi", "connect"
            ], capture_output=True, text=True, timeout=30)
            
            self.is_broadcasting = False
            self.broadcast_button.setText("Broadcast")
            self.broadcast_button.setEnabled(True)
            
            # Check connection result
            self.update_status_labels()
            
            # Show result message
            if self.status_value.text().startswith("Connected"):
                self.connection_result_label.setText("Successfully connected to WiFi network.")
                self.connection_result_label.setStyleSheet("font-family: Quicksand; font-size: 20px; color: #4CAF50;")
            else:
                self.connection_result_label.setText("Could not connect to a WiFi network. Check saved networks or try broadcasting again.")
                self.connection_result_label.setStyleSheet("font-family: Quicksand; font-size: 20px; color: #cc0000;")
            self.connection_result_label.show()
            
        except Exception as e:
            print(f"Error stopping broadcast: {e}")
            self.is_broadcasting = False
            self.broadcast_button.setText("Broadcast")
            self.broadcast_button.setEnabled(True)
            self.connection_result_label.setText(f"Error stopping broadcast: {e}")
            self.connection_result_label.setStyleSheet("font-family: Quicksand; font-size: 20px; color: #cc0000;")
            self.connection_result_label.show()
    
    def start_portal_server(self):
        """Start the Flask captive portal server in a background thread."""
        from wifi_portal_server import start_wifi_portal_server
        self.portal_server_running = True
        self.portal_server_thread = threading.Thread(
            target=start_wifi_portal_server,
            daemon=True
        )
        self.portal_server_thread.start()
    
    def stop_portal_server(self):
        """Stop the Flask captive portal server."""
        # Flask doesn't have a clean shutdown mechanism when run like this.
        # The thread is daemon=True, so it will die when the app exits.
        # For in-process stopping, we'd need a more complex solution.
        self.portal_server_running = False
    
    def return_to_main_display(self):
        """Return to the main display application."""
        try:
            # If broadcasting, stop it first
            if self.is_broadcasting:
                self.stop_broadcasting()
            
            # Get the directory of this script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            main_display_script = os.path.join(script_dir, "main_display.py")
            
            # Launch main_display.py with fullscreen argument
            subprocess.Popen(
                ["python3", main_display_script, "--fullscreen"],
                cwd=script_dir
            )
            
            # Terminate this application
            QApplication.instance().quit()
            
        except Exception as e:
            print(f"Error returning to main display: {e}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="WiFi Configuration Setup")
    parser.add_argument("--fullscreen", action="store_true", 
                       help="Run in fullscreen mode")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    app = QApplication([])
    
    window = WiFiSetupWindow()
    
    if args.fullscreen:
        window.showFullScreen()
    else:
        window.setFixedSize(1024, 600)
        window.show()
    
    app.exec()
