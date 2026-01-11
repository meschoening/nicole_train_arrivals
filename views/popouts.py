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

        content_layout.addLayout(
            self.build_info_row("Device IP:", ip_address, font_family)
        )
        content_layout.addLayout(
            self.build_info_row("Tailscale Address:", tailscale_address, font_family)
        )

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

    def build_info_row(self, label_text, value_text, font_family):
        row = QHBoxLayout()
        row.setSpacing(10)

        label = QLabel(label_text)
        label.setStyleSheet(
            f"font-family: {font_family}; font-size: 16px; font-weight: bold; color: #333; border: none;"
        )
        row.addWidget(label)

        value = QLabel(value_text)
        value.setStyleSheet(
            f"font-family: {font_family}; font-size: 16px; color: #666; border: none;"
        )
        row.addWidget(value)
        return row


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

        content_layout.addWidget(self.build_header(font_family))
        content_layout.addWidget(self.build_output_text())
        content_layout.addWidget(self.build_success_label(font_family))

        container = self.wrap_container(content_layout)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        self.setLayout(main_layout)

        self.setFixedSize(500, 300)

    def header_label_stylesheet(self, font_family):
        return (
            f"font-family: {font_family}; font-size: 14px; font-weight: bold; color: #333; border: none;"
        )

    def close_button_stylesheet(self, font_family):
        return f"""
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

    def success_label_stylesheet(self, font_family):
        return f"""
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

    def build_header(self, font_family):
        header = QWidget()
        header.setStyleSheet(
            "background-color: #f0f0f0; border-bottom: 1px solid #999; border: none;"
        )
        header.setFixedHeight(30)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 5, 5, 5)

        self.header_label = QLabel("Update Status")
        self.header_label.setStyleSheet(self.header_label_stylesheet(font_family))
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()

        self.close_button = QPushButton("✕")
        self.close_button.setStyleSheet(self.close_button_stylesheet(font_family))
        self.close_button.setFixedSize(20, 20)
        header_layout.addWidget(self.close_button)

        header.setLayout(header_layout)
        return header

    def build_output_text(self):
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
        return self.output_text

    def build_success_label(self, font_family):
        self.success_label = QLabel()
        self.success_label.setStyleSheet(self.success_label_stylesheet(font_family))
        self.success_label.setWordWrap(True)
        self.success_label.hide()
        return self.success_label

    def wrap_container(self, content_layout):
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
        return container

    def append_output(self, text):
        """Append text to the output area."""
        self.output_text.appendPlainText(text)
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )

    def clear_output(self):
        """Clear the output area and hide success label."""
        font_family = get_font_family(self.config_store)

        self.header_label.setStyleSheet(self.header_label_stylesheet(font_family))
        self.close_button.setStyleSheet(self.close_button_stylesheet(font_family))
        self.success_label.setStyleSheet(self.success_label_stylesheet(font_family))

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

        self.reboot_button = self.build_default_action_button("Reboot")
        layout.addWidget(self.reboot_button)

        self.shutdown_button = self.build_default_action_button("Shutdown")
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

    def default_action_button_stylesheet(self):
        return f"""
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

    def build_default_action_button(self, label):
        button = QPushButton(label)
        button.setMinimumWidth(200)
        button.setStyleSheet(self.default_action_button_stylesheet())
        return button

    def reset_shutdown_state(self):
        """Reset the shutdown button to its initial state."""
        self.font_family = get_font_family(self.config_store)

        self.shutdown_confirmed = False
        self.shutdown_button.setText("Shutdown")
        self.shutdown_button.setMinimumWidth(200)
        self.shutdown_button.setStyleSheet(self.default_action_button_stylesheet())

    def reset_reboot_state(self):
        """Reset the reboot button to its initial state."""
        self.font_family = get_font_family(self.config_store)

        self.reboot_confirmed = False
        self.reboot_button.setText("Reboot")
        self.reboot_button.setMinimumWidth(200)
        self.reboot_button.setStyleSheet(self.default_action_button_stylesheet())

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
