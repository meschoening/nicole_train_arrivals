"""Popout UI components."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from views.common import get_font_family


class IPPopout(QWidget):
    """A popout widget that displays the device IP address and Tailscale address."""

    def __init__(self, ip_address, tailscale_address, config_store, parent=None):
        super().__init__(parent)

        self.config_store = config_store
        font_family = get_font_family(self.config_store)

        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(15, 10, 15, 10)
        content_layout.setSpacing(8)

        ip_line = QHBoxLayout()
        ip_line.setSpacing(10)
        ip_label = QLabel("Device IP:")
        ip_label.setStyleSheet(
            f"font-family: {font_family}; font-size: 16px; font-weight: bold; color: #333; border: none;"
        )
        ip_line.addWidget(ip_label)

        ip_value = QLabel(ip_address)
        ip_value.setStyleSheet(
            f"font-family: {font_family}; font-size: 16px; color: #666; border: none;"
        )
        ip_line.addWidget(ip_value)
        content_layout.addLayout(ip_line)

        tailscale_line = QHBoxLayout()
        tailscale_line.setSpacing(10)
        tailscale_label = QLabel("Tailscale Address:")
        tailscale_label.setStyleSheet(
            f"font-family: {font_family}; font-size: 16px; font-weight: bold; color: #333; border: none;"
        )
        tailscale_line.addWidget(tailscale_label)

        tailscale_value = QLabel(tailscale_address)
        tailscale_value.setStyleSheet(
            f"font-family: {font_family}; font-size: 16px; color: #666; border: none;"
        )
        tailscale_line.addWidget(tailscale_value)
        content_layout.addLayout(tailscale_line)

        container = QWidget()
        container.setLayout(content_layout)
        container.setStyleSheet(
            """
            QWidget {
                background-color: white;
                border: 2px solid white;
                border-radius: 10px;
            }
        """
        )

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        self.setLayout(main_layout)

        self.adjustSize()


class UpdatePopout(QWidget):
    """A popout widget that displays git pull terminal output."""

    def __init__(self, config_store, parent=None):
        super().__init__(parent)

        self.config_store = config_store
        font_family = get_font_family(self.config_store)

        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(3, 3, 3, 3)
        content_layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(
            "background-color: #f0f0f0; border-bottom: 1px solid #999; border: none;"
        )
        header.setFixedHeight(30)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 5, 5, 5)

        self.header_label = QLabel("Update Status")
        self.header_label.setStyleSheet(
            f"font-family: {font_family}; font-size: 14px; font-weight: bold; color: #333; border: none;"
        )
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()

        self.close_button = QPushButton("✕")
        self.close_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {font_family};
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
                background-color: transparent;
                border: none;
                color: #666;
            }}
            QPushButton:hover {{
                color: #000;
                background-color: #e0e0e0;
                border-radius: 3px;
            }}
            QPushButton:pressed {{
                background-color: #d0d0d0;
            }}
        """
        )
        self.close_button.setFixedSize(20, 20)
        header_layout.addWidget(self.close_button)

        header.setLayout(header_layout)
        content_layout.addWidget(header)

        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet(
            """
            QPlainTextEdit {
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding: 10px;
            }
        """
        )
        content_layout.addWidget(self.output_text)

        self.success_label = QLabel()
        self.success_label.setStyleSheet(
            f"""
            QLabel {{
                font-family: {font_family};
                font-size: 13px;
                font-weight: bold;
                color: #2a7a2a;
                background-color: #e8f5e9;
                border: none;
                padding: 8px 10px;
            }}
        """
        )
        self.success_label.setWordWrap(True)
        self.success_label.hide()
        content_layout.addWidget(self.success_label)

        container = QWidget()
        container.setLayout(content_layout)
        container.setStyleSheet(
            """
            QWidget {
                background-color: white;
                border: 3px solid #666;
                border-radius: 5px;
            }
        """
        )

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        self.setLayout(main_layout)

        self.setFixedSize(500, 300)

    def append_output(self, text):
        """Append text to the output area."""
        self.output_text.appendPlainText(text)
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )

    def clear_output(self):
        """Clear the output area and hide success label."""
        font_family = get_font_family(self.config_store)

        self.header_label.setStyleSheet(
            f"font-family: {font_family}; font-size: 14px; font-weight: bold; color: #333; border: none;"
        )
        self.close_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {font_family};
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
                background-color: transparent;
                border: none;
                color: #666;
            }}
            QPushButton:hover {{
                color: #000;
                background-color: #e0e0e0;
                border-radius: 3px;
            }}
            QPushButton:pressed {{
                background-color: #d0d0d0;
            }}
        """
        )
        self.success_label.setStyleSheet(
            f"""
            QLabel {{
                font-family: {font_family};
                font-size: 13px;
                font-weight: bold;
                color: #2a7a2a;
                background-color: #e8f5e9;
                border: none;
                padding: 8px 10px;
            }}
        """
        )

        self.output_text.clear()
        self.success_label.hide()

    def show_success_message(self, commit_message):
        """Show the installed update success message."""
        self.success_label.setText(f"Installed Update: {commit_message}")
        self.success_label.show()


class ShutdownPopout(QWidget):
    """A popout widget that displays shutdown and exit options."""

    def __init__(self, config_store, parent=None):
        super().__init__(parent)

        self.config_store = config_store
        self.font_family = get_font_family(self.config_store)

        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.shutdown_confirmed = False
        self.reboot_confirmed = False

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        self.reboot_button = QPushButton("Reboot")
        self.reboot_button.setMinimumWidth(200)
        self.reboot_button.setStyleSheet(
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
        layout.addWidget(self.reboot_button)

        self.shutdown_button = QPushButton("Shutdown")
        self.shutdown_button.setMinimumWidth(200)
        self.shutdown_button.setStyleSheet(
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
        layout.addWidget(self.shutdown_button)

        self.setLayout(layout)

        self.setStyleSheet(
            """
            ShutdownPopout {
                background-color: white;
                border: 2px solid #999;
                border-radius: 5px;
            }
        """
        )

        self.adjustSize()

    def reset_shutdown_state(self):
        """Reset the shutdown button to its initial state."""
        self.font_family = get_font_family(self.config_store)

        self.shutdown_confirmed = False
        self.shutdown_button.setText("Shutdown")
        self.shutdown_button.setMinimumWidth(200)
        self.shutdown_button.setStyleSheet(
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

    def reset_reboot_state(self):
        """Reset the reboot button to its initial state."""
        self.font_family = get_font_family(self.config_store)

        self.reboot_confirmed = False
        self.reboot_button.setText("Reboot")
        self.reboot_button.setMinimumWidth(200)
        self.reboot_button.setStyleSheet(
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

    def set_reboot_confirm_state(self):
        """Set the reboot button to confirmation state (red)."""
        self.reboot_confirmed = True
        self.reboot_button.setText("Confirm Reboot")
        self.reboot_button.setMinimumWidth(200)
        self.reboot_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 18px;
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
                background-color: #c1170a;
                padding-bottom: 9px;
            }}
        """
        )

    def set_shutdown_confirm_state(self):
        """Set the shutdown button to confirmation state (red)."""
        self.shutdown_confirmed = True
        self.shutdown_button.setText("Confirm Shutdown")
        self.shutdown_button.setMinimumWidth(200)
        self.shutdown_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {self.font_family};
                font-size: 18px;
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
                background-color: #c1170a;
                padding-bottom: 9px;
            }}
        """
        )
