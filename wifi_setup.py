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

import os
import sys
import argparse
import subprocess
from services.config_store import ConfigStore
from services.system_actions import run_command, start_process


class WiFiSetupWindow(QMainWindow):
    """Main window for WiFi configuration setup."""
    
    def __init__(self):
        super().__init__()

        # Load config to get font family
        config_store = ConfigStore()
        self.font_family = config_store.get_str('font_family', 'Quicksand')
        
        self.title_text = "WiFi Configuration"
        self.setWindowTitle(self.title_text)
        
        # Hide cursor for touchscreen kiosk mode
        self.setCursor(Qt.BlankCursor)
        
        # AP state tracking
        self.is_broadcasting = False
        self.portal_server_process = None
        
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
        layout.addWidget(self.build_header_title_label(), alignment=Qt.AlignVCenter | Qt.AlignLeft)
        
        layout.addStretch()
        
        # Return to Main Display button (right-aligned)
        layout.addWidget(self.build_return_button(), alignment=Qt.AlignVCenter | Qt.AlignRight)
        
        header.setLayout(layout)
        return header

    def build_header_title_label(self):
        title_label = QLabel(self.title_text)
        title_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 30px; font-weight: bold;"
        )
        return title_label

    def build_return_button(self):
        return_button = QPushButton("Return to Main Display")
        return_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 18px;
                font-weight: bold;
                padding: 10px 25px;
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
        return_button.setFixedHeight(45)
        return_button.clicked.connect(self.return_to_main_display)
        return return_button

    def build_status_row(self, title, value_attr, initial_value):
        row = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 24px; font-weight: bold;"
        )
        title_label.setFixedWidth(150)
        value_label = QLabel(initial_value)
        value_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px;")
        setattr(self, value_attr, value_label)
        row.addWidget(title_label)
        row.addWidget(value_label)
        row.addStretch()
        return row

    def build_status_box(self):
        status_container = QWidget()
        status_container.setStyleSheet(
            """
            background-color: #e8e8e8;
            border-radius: 10px;
        """
        )
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(30, 30, 30, 30)
        status_layout.setSpacing(15)

        status_layout.addLayout(self.build_status_row("Status:", "status_value", "Checking..."))
        status_layout.addLayout(self.build_status_row("AP Name:", "ap_name_value", "—"))
        status_layout.addLayout(self.build_status_row("IP Address:", "ip_value", "—"))

        self.broadcast_button = QPushButton("Broadcast Setup Network")
        self.broadcast_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 18px;
                font-weight: bold;
                padding: 10px 25px;
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
                padding-bottom: 9px;
            }}
        """
        )
        self.broadcast_button.setFixedHeight(45)
        self.broadcast_button.clicked.connect(self.toggle_broadcast)
        status_layout.addWidget(self.broadcast_button)

        self.connection_result_label = QLabel("")
        self.connection_result_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 20px; color: #666;"
        )
        self.connection_result_label.setWordWrap(True)
        self.connection_result_label.hide()
        status_layout.addWidget(self.connection_result_label)

        status_container.setLayout(status_layout)
        return status_container

    def build_manual_connection_box(self):
        manual_container = QWidget()
        manual_container.setStyleSheet(
            """
            background-color: #e8e8e8;
            border-radius: 10px;
        """
        )
        manual_layout = QVBoxLayout()
        manual_layout.setContentsMargins(30, 30, 30, 30)
        manual_layout.setSpacing(15)

        manual_title = QLabel("Manual Connection")
        manual_title.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 22px; font-weight: bold;"
        )
        manual_layout.addWidget(manual_title)

        self.saved_networks_combo = QComboBox()
        self.saved_networks_combo.setStyleSheet(
            f"""
            QComboBox {{
                font-family: {self.font_family};
                font-size: 18px;
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: white;
            }}
            QComboBox:hover {{
                border: 1px solid #999;
            }}
            QComboBox QAbstractItemView {{
                font-family: {self.font_family};
                font-size: 18px;
                background-color: white;
                selection-background-color: #e0e0e0;
                selection-color: #000;
                color: #000;
            }}
            QComboBox QAbstractItemView::item {{
                color: #000;
                padding: 5px;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #e0e0e0;
                color: #000;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #e0e0e0;
                color: #000;
            }}
        """
        )
        manual_layout.addWidget(self.saved_networks_combo)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)

        self.refresh_networks_button = QPushButton("Refresh List")
        self.refresh_networks_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 16px;
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
            }}
        """
        )
        self.refresh_networks_button.clicked.connect(self.load_saved_networks)
        buttons_row.addWidget(self.refresh_networks_button)

        self.connect_button = QPushButton("Connect to Network")
        self.connect_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 16px;
                font-weight: bold;
                padding: 10px 20px;
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
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
        """
        )
        self.connect_button.clicked.connect(self.toggle_manual_connection)
        buttons_row.addWidget(self.connect_button)

        manual_layout.addLayout(buttons_row)
        manual_container.setLayout(manual_layout)
        return manual_container

    def build_console_section(self):
        console_container = QWidget()
        console_container.setStyleSheet(
            """
            background-color: #e8e8e8;
            border-radius: 10px;
        """
        )
        console_layout = QVBoxLayout()
        console_layout.setContentsMargins(30, 30, 30, 30)
        console_layout.setSpacing(15)

        console_title = QLabel("Console Output:")
        console_title.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 22px; font-weight: bold;"
        )
        console_layout.addWidget(console_title)

        self.connection_console = QPlainTextEdit()
        self.connection_console.setReadOnly(True)
        self.connection_console.setStyleSheet(
            """
            QPlainTextEdit {
                font-family: monospace;
                font-size: 14px;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 10px;
            }
        """
        )
        console_layout.addWidget(self.connection_console, 1)

        console_container.setLayout(console_layout)
        return console_container
    
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
        
        left_column_layout = QVBoxLayout()
        left_column_layout.setSpacing(20)
        left_column_layout.addWidget(self.build_status_box())
        left_column_layout.addWidget(self.build_manual_connection_box())
        left_column_layout.addStretch()
        columns_layout.addLayout(left_column_layout, 1)

        columns_layout.addWidget(self.build_console_section(), 1)
        
        # Add the columns to the outer layout
        outer_layout.addLayout(columns_layout, 1)  # stretch factor 1 to fill height
        
        # Load saved networks on startup
        QTimer.singleShot(500, self.load_saved_networks)
        
        content.setLayout(outer_layout)
        return content
    
    def update_status_labels(self):
        """Update the status labels based on current network state."""
        try:
            if self.is_broadcasting:
                self.status_value.setText("AP Mode (Broadcasting)")
                self.status_value.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #2196F3;")
                self.ap_name_value.setText("NicoleTrains-Setup")
                self.ip_value.setText("192.168.4.1")
            else:
                # Check WiFi connection status
                result = run_command(
                    ["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"],
                    timeout_s=5,
                    log_label="wifi_status",
                )
                
                connected = False
                connection_name = ""
                
                if result.ok:
                    for line in result.stdout.strip().split('\n'):
                        parts = line.split(':')
                        if len(parts) >= 3 and parts[0] == 'wifi':
                            if 'connected' in parts[1].lower() and parts[1].lower() != 'disconnected':
                                connected = True
                                connection_name = parts[2] if len(parts) > 2 else "Unknown"
                                break
                
                if connected:
                    self.status_value.setText("Connected")
                    self.status_value.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #4CAF50;")
                    self.ap_name_value.setText(connection_name if connection_name else "—")
                    # Get current IP
                    ip = self.get_current_ip()
                    self.ip_value.setText(ip if ip else "—")
                else:
                    self.status_value.setText("Not Connected")
                    self.status_value.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #cc0000;")
                    self.ap_name_value.setText("—")
                    self.ip_value.setText("—")
                    
        except Exception as e:
            print(f"Error updating status: {e}")
            self.status_value.setText("Error checking status")
            self.status_value.setStyleSheet(f"font-family: {self.font_family}; font-size: 24px; color: #cc0000;")
    
    def get_current_ip(self):
        """Get the current IP address of wlan0."""
        try:
            result = run_command(
                ["ip", "-4", "addr", "show", "wlan0"],
                timeout_s=5,
                log_label="wifi_current_ip",
            )
            if result.ok:
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
            result = run_command(
                ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
                timeout_s=10,
                log_label="wifi_saved_networks",
            )
            
            if result.ok:
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
                error_text = result.stderr.strip() or result.error or "Command failed"
                self.connection_console.appendPlainText(f"Error: {error_text}")
                
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
        self.connect_button.setStyleSheet(f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 16px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #cccccc;
                color: #666666;
                border: none;
                border-radius: 5px;
            }}
        """)
        
        self.connection_console.clear()
        self.connection_console.appendPlainText(f"$ sudo nmcli connection up \"{selected}\"")
        self.connection_console.appendPlainText("Connecting...")
        
        # Use QProcess for async execution
        self.connection_process = QProcess()
        self.connection_process.readyReadStandardOutput.connect(self.on_connection_output)
        self.connection_process.readyReadStandardError.connect(self.on_connection_error)
        self.connection_process.finished.connect(self.on_connection_finished)
        
        self.connection_process.start("sudo", ["nmcli", "connection", "up", selected])
    
    def disconnect_network(self):
        """Disconnect from the current WiFi network."""
        self.is_connecting = True
        self.connect_button.setEnabled(False)
        self.connect_button.setText("Disconnecting...")
        
        self.connection_console.clear()
        self.connection_console.appendPlainText("$ sudo nmcli device disconnect wlan0")
        self.connection_console.appendPlainText("Disconnecting...")
        
        # Use QProcess for async execution
        self.connection_process = QProcess()
        self.connection_process.readyReadStandardOutput.connect(self.on_connection_output)
        self.connection_process.readyReadStandardError.connect(self.on_connection_error)
        self.connection_process.finished.connect(self.on_disconnect_finished)
        
        self.connection_process.start("sudo", ["nmcli", "device", "disconnect", "wlan0"])
    
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
            self.connect_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 16px;
                    font-weight: bold;
                    padding: 10px 20px;
                    background-color: #f44336;
                    color: white;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #da190b;
                }}
                QPushButton:pressed {{
                    background-color: #c41409;
                }}
            """)
        else:
            self.is_manually_connected = False
            self.connection_console.appendPlainText(f"\n✗ Connection failed (exit code: {exit_code})")
            self.connect_button.setText("Connect to Network")
            self.connect_button.setStyleSheet(f"""
                QPushButton {{
                    font-family: {self.font_family};
                    font-size: 16px;
                    font-weight: bold;
                    padding: 10px 20px;
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
                }}
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
        self.connect_button.setStyleSheet(f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 16px;
                font-weight: bold;
                padding: 10px 20px;
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
            }}
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
            # Clear console and start logging
            self.connection_console.clear()
            self.connection_console.appendPlainText("Starting Access Point...")
            
            self.broadcast_button.setEnabled(False)
            self.broadcast_button.setText("Starting Access Point...")
            QApplication.processEvents()
            
            # Get script directory for config files
            script_dir = os.path.dirname(os.path.abspath(__file__))
            hostapd_conf = os.path.join(script_dir, "hostapd_provisioning.conf")
            
            # Step 1: Disconnect from any existing WiFi connection
            self.connection_console.appendPlainText("$ sudo nmcli device disconnect wlan0")
            QApplication.processEvents()
            run_command(
                ["sudo", "nmcli", "device", "disconnect", "wlan0"],
                timeout_s=10,
                log_label="ap_disconnect_wifi",
            )
            
            # Step 2: Set static IP on wlan0
            self.connection_console.appendPlainText("$ sudo ip addr flush dev wlan0")
            QApplication.processEvents()
            run_command(
                ["sudo", "ip", "addr", "flush", "dev", "wlan0"],
                timeout_s=5,
                log_label="ap_flush_ip",
            )
            
            self.connection_console.appendPlainText("$ sudo ip addr add 192.168.4.1/24 dev wlan0")
            QApplication.processEvents()
            run_command(
                ["sudo", "ip", "addr", "add", "192.168.4.1/24", "dev", "wlan0"],
                timeout_s=5,
                log_label="ap_add_ip",
            )
            
            self.connection_console.appendPlainText("$ sudo ip link set wlan0 up")
            QApplication.processEvents()
            run_command(
                ["sudo", "ip", "link", "set", "wlan0", "up"],
                timeout_s=5,
                log_label="ap_link_up",
            )
            
            # Step 3: Start dnsmasq
            self.connection_console.appendPlainText("$ sudo systemctl start dnsmasq")
            QApplication.processEvents()
            run_command(
                ["sudo", "systemctl", "start", "dnsmasq"],
                timeout_s=10,
                log_label="ap_dnsmasq_start",
            )
            
            # Step 4: Start hostapd with our config
            self.connection_console.appendPlainText(f"$ sudo hostapd -B {hostapd_conf}")
            QApplication.processEvents()
            run_command(
                ["sudo", "hostapd", "-B", hostapd_conf],
                timeout_s=10,
                log_label="ap_hostapd_start",
            )
            
            # Step 5: Start Flask captive portal
            self.connection_console.appendPlainText("Starting captive portal server...")
            QApplication.processEvents()
            self.start_portal_server()
            
            self.is_broadcasting = True
            self.broadcast_button.setText("Close Setup Network")
            self.broadcast_button.setEnabled(True)
            
            # Hide any previous connection result
            self.connection_result_label.hide()
            
            # Read the hotspot password from config file
            hotspot_password = ""
            try:
                with open(hostapd_conf, 'r') as f:
                    for line in f:
                        if line.startswith('wpa_passphrase='):
                            hotspot_password = line.strip().split('=', 1)[1]
                            break
            except Exception:
                hotspot_password = "(unknown)"
            
            self.connection_console.appendPlainText("\n✓ Access Point started successfully!")
            self.connection_console.appendPlainText("SSID: NicoleTrains-Setup")
            self.connection_console.appendPlainText(f"Password: **{hotspot_password}**" if hotspot_password else "Password: (none - open network)")
            self.connection_console.appendPlainText("IP: 192.168.4.1")
            
            self.update_status_labels()
            
        except Exception as e:
            print(f"Error starting broadcast: {e}")
            self.connection_console.appendPlainText(f"\n✗ Error: {e}")
            self.broadcast_button.setText("Broadcast Setup Network")
            self.broadcast_button.setEnabled(True)
            self.connection_result_label.setText(f"Error starting broadcast: {e}")
            self.connection_result_label.setStyleSheet(f"font-family: {self.font_family}; font-size: 20px; color: #cc0000;")
            self.connection_result_label.show()
    
    def stop_broadcasting(self):
        """Stop AP mode and attempt to reconnect to WiFi."""
        try:
            # Clear console and start logging
            self.connection_console.clear()
            self.connection_console.appendPlainText("Shutting down Access Point...")
            
            self.broadcast_button.setEnabled(False)
            self.broadcast_button.setText("Shutting Down...")
            QApplication.processEvents()
            
            # Step 1: Stop Flask portal
            self.connection_console.appendPlainText("Stopping captive portal server...")
            QApplication.processEvents()
            self.stop_portal_server()
            
            # Step 2: Stop hostapd
            self.connection_console.appendPlainText("$ sudo killall hostapd")
            QApplication.processEvents()
            run_command(
                ["sudo", "killall", "hostapd"],
                timeout_s=10,
                log_label="ap_hostapd_stop",
            )
            
            # Step 3: Stop dnsmasq
            self.connection_console.appendPlainText("$ sudo systemctl stop dnsmasq")
            QApplication.processEvents()
            run_command(
                ["sudo", "systemctl", "stop", "dnsmasq"],
                timeout_s=10,
                log_label="ap_dnsmasq_stop",
            )
            
            # Step 4: Restart systemd-resolved to refresh DNS resolution
            # This is critical - without it, DNS queries fail after stopping dnsmasq
            self.connection_console.appendPlainText("$ sudo systemctl restart systemd-resolved")
            QApplication.processEvents()
            run_command(
                ["sudo", "systemctl", "restart", "systemd-resolved"],
                timeout_s=10,
                log_label="ap_dns_restart",
            )
            
            # Step 5: Flush IP and return interface to managed mode
            self.connection_console.appendPlainText("$ sudo ip addr flush dev wlan0")
            QApplication.processEvents()
            run_command(
                ["sudo", "ip", "addr", "flush", "dev", "wlan0"],
                timeout_s=5,
                log_label="ap_flush_ip_stop",
            )
            
            # Step 6: Restart NetworkManager to take control
            self.connection_console.appendPlainText("$ sudo systemctl restart NetworkManager")
            QApplication.processEvents()
            run_command(
                ["sudo", "systemctl", "restart", "NetworkManager"],
                timeout_s=15,
                log_label="ap_network_manager_restart",
            )
            
            # Wait a moment for NetworkManager to initialize
            self.connection_console.appendPlainText("Waiting for NetworkManager to initialize...")
            QApplication.processEvents()
            import time
            time.sleep(2)
            
            # Explicitly request connection to a saved WiFi network
            # This is needed because the earlier "nmcli device disconnect" is remembered
            # by NetworkManager as a user-requested disconnect, preventing auto-reconnect
            self.connection_console.appendPlainText("$ sudo nmcli connection up ifname wlan0")
            QApplication.processEvents()
            run_command(
                ["sudo", "nmcli", "--wait", "5", "connection", "up", "ifname", "wlan0"],
                timeout_s=10,
                log_label="ap_nmcli_connect",
            )
            
            # Wait for NetworkManager to auto-connect to a saved network (5 seconds max with polling)
            max_wait = 5  # seconds
            poll_interval = 0.5  # seconds
            waited = 0
            connected = False
            
            while waited < max_wait:
                remaining = int(max_wait - waited)
                
                # Update countdown display on same line
                cursor = self.connection_console.textCursor()
                cursor.movePosition(cursor.End)
                cursor.select(cursor.LineUnderCursor)
                if cursor.selectedText().startswith("Waiting for connection"):
                    cursor.removeSelectedText()
                    cursor.deletePreviousChar()  # Remove newline
                self.connection_console.appendPlainText(f"Waiting for connection... {remaining}s")
                QApplication.processEvents()
                
                # Check if WiFi is connected
                try:
                    result = run_command(
                        ["nmcli", "-t", "-f", "TYPE,STATE", "device"],
                        timeout_s=2,
                        log_label="wifi_poll_connection",
                    )
                    if result.ok:
                        for line in result.stdout.strip().split('\n'):
                            if line.startswith('wifi:') and ':connected' in line.lower():
                                connected = True
                                break
                except Exception:
                    pass
                
                if connected:
                    break
                
                time.sleep(poll_interval)
                waited += poll_interval
            
            self.is_broadcasting = False
            self.broadcast_button.setText("Broadcast Setup Network")
            self.broadcast_button.setEnabled(True)
            
            # Check connection result
            self.update_status_labels()
            
            # Show result message
            if self.status_value.text().startswith("Connected"):
                self.connection_console.appendPlainText("\n✓ Successfully connected to WiFi network!")
                self.connection_result_label.setText("Successfully connected to WiFi network.")
                self.connection_result_label.setStyleSheet("font-family: Quicksand; font-size: 20px; color: #4CAF50;")
            else:
                self.connection_console.appendPlainText("\n✗ Could not connect to a WiFi network.")
                self.connection_result_label.setText("Could not connect to a WiFi network.")
                self.connection_result_label.setStyleSheet("font-family: Quicksand; font-size: 20px; color: #cc0000;")
            self.connection_result_label.show()
            
        except Exception as e:
            print(f"Error stopping broadcast: {e}")
            self.connection_console.appendPlainText(f"\n✗ Error: {e}")
            self.is_broadcasting = False
            self.broadcast_button.setText("Broadcast Setup Network")
            self.broadcast_button.setEnabled(True)
            self.connection_result_label.setText(f"Error stopping broadcast: {e}")
            self.connection_result_label.setStyleSheet("font-family: Quicksand; font-size: 20px; color: #cc0000;")
            self.connection_result_label.show()
    
    def start_portal_server(self):
        """Start the Flask captive portal server as a background process."""
        if self.portal_server_process and self.portal_server_process.poll() is None:
            self.connection_console.appendPlainText("Captive portal server already running.")
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        portal_script = os.path.join(script_dir, "wifi_portal_server.py")
        self.portal_server_process = start_process(
            [sys.executable, portal_script],
            cwd=script_dir,
            log_label="start_wifi_portal_server",
        )

    def stop_portal_server(self):
        """Stop the Flask captive portal server."""
        process = self.portal_server_process
        if not process:
            return

        if process.poll() is not None:
            self.portal_server_process = None
            return

        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self.portal_server_process = None
    
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
            start_process(
                ["python3", main_display_script, "--fullscreen"],
                cwd=script_dir,
                log_label="launch_main_display",
                timeout_s=None,
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
