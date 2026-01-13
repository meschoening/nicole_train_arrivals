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


        container_holder = QHBoxLayout()
        container_holder.addStretch()
        container_holder.addWidget(self.build_center_container(font_family))
        container_holder.addStretch()
        main_layout.addLayout(container_holder)
        main_layout.addStretch()

        self.setLayout(main_layout)

    def build_center_container(self, font_family):
        center_container = QWidget()
        center_container.setStyleSheet("background-color: transparent;")

        center_layout = QHBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        self.warning_label = self.build_warning_label(font_family)
        center_layout.addWidget(self.warning_label, alignment=Qt.AlignCenter)

        self.cancel_button = self.build_cancel_button(font_family)
        center_layout.addWidget(self.cancel_button, alignment=Qt.AlignCenter)

        center_container.setLayout(center_layout)
        return center_container

    def build_warning_label(self, font_family):
        warning_label = QLabel("Rebooting in 60 seconds")
        warning_label.setStyleSheet(
            f"""
            font-family: {font_family};
            font-size: 14px;
            font-weight: bold;
            color: #721c24;
            background-color: #f8d7da;
            padding: 5px 10px;
            border-radius: 4px;
        """
        )
        warning_label.setAlignment(Qt.AlignCenter)
        warning_label.setWordWrap(False)
        return warning_label

    def build_cancel_button(self, font_family):
        cancel_button = QPushButton("Cancel Reboot")
        cancel_button.setStyleSheet(
            f"""
            QPushButton {{
                font-family: {font_family};
                font-size: 14px;
                font-weight: bold;
                padding: 5px 10px;
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
                padding-bottom: 4px;
            }}
        """
        )
        return cancel_button

    def update_countdown(self, seconds):
        """Update the countdown display."""
        self.warning_label.setText(f"Rebooting in {seconds} seconds")
