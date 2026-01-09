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

        main_layout.addStretch()
        container_holder = QHBoxLayout()
        container_holder.addStretch()
        container_holder.addWidget(self._build_center_container(font_family))
        container_holder.addStretch()
        main_layout.addLayout(container_holder)
        main_layout.addStretch()

        self.setLayout(main_layout)

    def _build_center_container(self, font_family):
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
        center_layout.addWidget(self._build_warning_label(font_family))

        self.countdown_label = self._build_countdown_label(font_family)
        center_layout.addWidget(self.countdown_label)
        center_layout.addSpacing(10)

        self.cancel_button = self._build_cancel_button(font_family)
        center_layout.addWidget(self.cancel_button, alignment=Qt.AlignCenter)

        center_container.setLayout(center_layout)
        return center_container

    def _build_warning_label(self, font_family):
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
        return warning_label

    def _build_countdown_label(self, font_family):
        countdown_label = QLabel("System will reboot in 60 seconds")
        countdown_label.setStyleSheet(
            f"""
            font-family: {font_family};
            font-size: 24px;
            font-weight: bold;
            color: white;
        """
        )
        countdown_label.setAlignment(Qt.AlignCenter)
        countdown_label.setWordWrap(True)
        return countdown_label

    def _build_cancel_button(self, font_family):
        cancel_button = QPushButton("Cancel Reboot")
        cancel_button.setStyleSheet(
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
        return cancel_button

    def update_countdown(self, seconds):
        """Update the countdown display."""
        self.countdown_label.setText(f"System will reboot in {seconds} seconds")
