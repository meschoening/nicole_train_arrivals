"""Overlay UI components."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from views.common import get_font_family


class RebootWarningOverlay(QWidget):
    """A fullscreen modal overlay that displays reboot countdown warning."""

    def __init__(self, config_store, parent=None):
        super().__init__(parent)

        self.config_store = config_store
        font_family = get_font_family(self.config_store)

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.setStyleSheet("background-color: rgba(0, 0, 0, 180);")

        center_container = QWidget()
        center_container.setStyleSheet(
            """
            QWidget {
                background-color: #f44336;
                border: 3px solid #c62828;
                border-radius: 15px;
            }
        """
        )
        center_container.setFixedSize(600, 300)

        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(40, 40, 40, 40)
        center_layout.setSpacing(20)

        warning_label = QLabel("⚠ REBOOT WARNING ⚠")
        warning_label.setStyleSheet(
            f"""
            font-family: {font_family};
            font-size: 32px;
            font-weight: bold;
            color: white;
        """
        )
        warning_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(warning_label)

        self.countdown_label = QLabel("System will reboot in 60 seconds")
        self.countdown_label.setStyleSheet(
            f"""
            font-family: {font_family};
            font-size: 24px;
            font-weight: bold;
            color: white;
        """
        )
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setWordWrap(True)
        center_layout.addWidget(self.countdown_label)

        center_layout.addSpacing(10)

        self.cancel_button = QPushButton("Cancel Reboot")
        self.cancel_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {font_family};
                font-size: 22px;
                font-weight: bold;
                padding: 15px 40px;
                background-color: white;
                color: #f44336;
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: #f0f0f0;
            }}
            QPushButton:pressed {{
                background-color: #e0e0e0;
                padding-bottom: 14px;
            }}
        """
        )
        center_layout.addWidget(self.cancel_button, alignment=Qt.AlignCenter)

        center_container.setLayout(center_layout)

        main_layout.addStretch()
        container_holder = QHBoxLayout()
        container_holder.addStretch()
        container_holder.addWidget(center_container)
        container_holder.addStretch()
        main_layout.addLayout(container_holder)
        main_layout.addStretch()

        self.setLayout(main_layout)

    def update_countdown(self, seconds):
        """Update the countdown display."""
        self.countdown_label.setText(f"System will reboot in {seconds} seconds")
