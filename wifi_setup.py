#!/usr/bin/env python3
"""
WiFi Configuration Setup Application

A fullscreen PyQt5 application for configuring WiFi networks on DietPi.
Launched from main_display.py when no WiFi connection is detected.
"""

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QWidget, QPushButton, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
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
        
        # AP state tracking
        self.is_broadcasting = False
        self.portal_server_thread = None
        self.portal_server_running = False
        
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
        
        # Content area
        content = self.create_content_area()
        main_layout.addWidget(content, 1)  # stretch factor 1
        
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
        """Create the main content area with status labels."""
        content = QWidget()
        content.setStyleSheet("background-color: #f0f0f0;")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Status container
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
        status_title.setFixedWidth(200)
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
        ap_title.setFixedWidth(200)
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
        ip_title.setFixedWidth(200)
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
        
        status_container.setLayout(status_layout)
        layout.addWidget(status_container)
        
        layout.addStretch()
        
        content.setLayout(layout)
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
