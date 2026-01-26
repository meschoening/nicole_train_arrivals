"""Settings page UI builders."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from views.styles import (
    checkbox_indicator_stylesheet,
    combo_box_stylesheet,
    default_action_button_stylesheet,
)


class SettingsPageBuilder:
    """Builder for settings page UI components."""

    def __init__(self, font_family, configure_combo_for_touchscreen_fn):
        """Initialize the builder.

        Args:
            font_family: Font family name string
            configure_combo_for_touchscreen_fn: Function to configure combo boxes for touchscreen
        """
        self.font_family = font_family
        self.configure_combo_for_touchscreen = configure_combo_for_touchscreen_fn

    def build_back_button(self, on_click):
        """Build the back button for the settings page.

        Args:
            on_click: Callback function for click events

        Returns:
            QPushButton configured as back button
        """
        back_button = QPushButton("\u2190")
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
        back_button.clicked.connect(on_click)
        return back_button

    def build_heading(self):
        """Build the Settings heading layout.

        Returns:
            QVBoxLayout with settings heading
        """
        heading_layout = QVBoxLayout()
        settings_label = QLabel("Settings")
        settings_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 28px; font-weight: bold;"
        )
        settings_label.setAlignment(Qt.AlignCenter)
        heading_layout.addWidget(settings_label)
        heading_layout.addSpacing(10)
        return heading_layout

    def build_line_selector_row(self, label_width, on_index_changed, on_settings_changed):
        """Build the line selector row.

        Args:
            label_width: Fixed width for the label
            on_index_changed: Callback for index change
            on_settings_changed: Callback to mark settings as changed

        Returns:
            tuple: (QHBoxLayout, QComboBox)
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Select Line:")
        label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        label.setFixedWidth(label_width)
        layout.addWidget(label)

        combo = QComboBox()
        combo.setStyleSheet(combo_box_stylesheet(self.font_family))
        combo.setMinimumWidth(265)
        self.configure_combo_for_touchscreen(combo)
        combo.currentIndexChanged.connect(on_index_changed)
        combo.currentIndexChanged.connect(on_settings_changed)
        layout.addWidget(combo)
        layout.addStretch()

        return layout, combo

    def build_station_selector_row(self, label_width, on_index_changed, on_settings_changed):
        """Build the station selector row.

        Args:
            label_width: Fixed width for the label
            on_index_changed: Callback for index change
            on_settings_changed: Callback to mark settings as changed

        Returns:
            tuple: (QHBoxLayout, QComboBox)
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Select Station:")
        label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        label.setFixedWidth(label_width)
        layout.addWidget(label)

        combo = QComboBox()
        combo.setStyleSheet(combo_box_stylesheet(self.font_family))
        combo.setMinimumWidth(265)
        self.configure_combo_for_touchscreen(combo)
        combo.currentIndexChanged.connect(on_index_changed)
        combo.currentIndexChanged.connect(on_settings_changed)
        layout.addWidget(combo)
        layout.addStretch()

        return layout, combo

    def build_destination_selector_row(self, label_width, on_index_changed, on_settings_changed):
        """Build the destination selector row.

        Args:
            label_width: Fixed width for the label
            on_index_changed: Callback for index change
            on_settings_changed: Callback to mark settings as changed

        Returns:
            tuple: (QHBoxLayout, QComboBox)
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Select Destination:")
        label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        label.setFixedWidth(label_width)
        layout.addWidget(label)

        combo = QComboBox()
        combo.setStyleSheet(combo_box_stylesheet(self.font_family))
        combo.setMinimumWidth(265)
        self.configure_combo_for_touchscreen(combo)
        combo.currentIndexChanged.connect(on_index_changed)
        combo.currentIndexChanged.connect(on_settings_changed)
        layout.addWidget(combo)
        layout.addStretch()

        return layout, combo

    def build_countdown_checkbox_row(self, label_width, on_toggle, on_settings_changed):
        """Build the countdown visibility checkbox row.

        Args:
            label_width: Fixed width for the label
            on_toggle: Callback for state change
            on_settings_changed: Callback to mark settings as changed

        Returns:
            tuple: (QHBoxLayout, QCheckBox)
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Show Time to Refresh:")
        label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        label.setFixedWidth(label_width)
        layout.addWidget(label)

        checkbox = QCheckBox()
        checkbox.setStyleSheet(checkbox_indicator_stylesheet())
        checkbox.setChecked(True)
        checkbox.stateChanged.connect(on_toggle)
        checkbox.stateChanged.connect(on_settings_changed)

        layout.addWidget(checkbox)
        layout.addStretch()

        return layout, checkbox

    def build_clock_checkbox_row(self, label_width, on_toggle, on_settings_changed, reference_checkbox):
        """Build the clock visibility checkbox row.

        Args:
            label_width: Fixed width for the label
            on_toggle: Callback for state change
            on_settings_changed: Callback to mark settings as changed
            reference_checkbox: Another checkbox to copy stylesheet from

        Returns:
            tuple: (QHBoxLayout, QCheckBox)
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Show Clock in Top Bar:")
        label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        label.setFixedWidth(label_width)
        layout.addWidget(label)

        checkbox = QCheckBox()
        checkbox.setStyleSheet(reference_checkbox.styleSheet())
        checkbox.setChecked(True)
        checkbox.stateChanged.connect(on_toggle)
        checkbox.stateChanged.connect(on_settings_changed)
        layout.addWidget(checkbox)
        layout.addStretch()

        return layout, checkbox

    def build_filter_destination_checkbox_row(
        self, label_width, on_filter_changed, on_display_update, on_settings_changed
    ):
        """Build the filter by destination checkbox row.

        Args:
            label_width: Fixed width for the label
            on_filter_changed: Callback for filter state change
            on_display_update: Callback to update display
            on_settings_changed: Callback to mark settings as changed

        Returns:
            tuple: (QHBoxLayout, QCheckBox)
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Filter by Selected Destination:")
        label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        label.setFixedWidth(label_width)
        layout.addWidget(label)

        checkbox = QCheckBox()
        checkbox.setStyleSheet(checkbox_indicator_stylesheet())
        checkbox.setChecked(False)
        checkbox.stateChanged.connect(on_filter_changed)
        checkbox.stateChanged.connect(on_display_update)
        checkbox.stateChanged.connect(on_settings_changed)

        layout.addWidget(checkbox)
        layout.addStretch()

        return layout, checkbox

    def build_filter_direction_checkbox_row(
        self, label_width, on_filter_changed, on_display_update, on_settings_changed
    ):
        """Build the filter by direction checkbox row.

        Args:
            label_width: Fixed width for the label
            on_filter_changed: Callback for filter state change
            on_display_update: Callback to update display
            on_settings_changed: Callback to mark settings as changed

        Returns:
            tuple: (QHBoxLayout, QCheckBox)
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Filter by Destination Direction:")
        label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        label.setFixedWidth(label_width)
        layout.addWidget(label)

        checkbox = QCheckBox()
        checkbox.setStyleSheet(checkbox_indicator_stylesheet())
        checkbox.setChecked(False)
        checkbox.stateChanged.connect(on_filter_changed)
        checkbox.stateChanged.connect(on_display_update)
        checkbox.stateChanged.connect(on_settings_changed)

        layout.addWidget(checkbox)
        layout.addStretch()

        return layout, checkbox

    def build_screen_sleep_enable_row(self, on_settings_changed):
        """Build the screen sleep enable checkbox row.

        Args:
            on_settings_changed: Callback to mark settings as changed

        Returns:
            tuple: (QHBoxLayout, QCheckBox)
        """
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Enable Screen Sleep:")
        label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        layout.addWidget(label)

        checkbox = QCheckBox()
        checkbox.setStyleSheet(checkbox_indicator_stylesheet())
        checkbox.setChecked(False)
        checkbox.stateChanged.connect(on_settings_changed)
        layout.addWidget(checkbox)
        layout.addStretch()

        return layout, checkbox

    def build_screen_sleep_slider_row(self, on_value_changed, on_settings_changed):
        """Build the screen sleep slider row.

        Args:
            on_value_changed: Callback for slider value changes
            on_settings_changed: Callback to mark settings as changed

        Returns:
            tuple: (QVBoxLayout, QSlider, QLabel)
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        value_label = QLabel("Screen Sleep Timeout: 5 min")
        value_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 21px; font-weight: bold;"
        )
        layout.addWidget(value_label)

        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(1)
        slider.setMaximum(30)
        slider.setValue(5)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(5)
        slider.setStyleSheet(
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
        slider.valueChanged.connect(on_value_changed)
        slider.valueChanged.connect(on_settings_changed)
        layout.addWidget(slider)

        return layout, slider, value_label

    def build_vertical_separator(self):
        """Build a vertical separator line.

        Returns:
            QWidget configured as vertical separator
        """
        separator = QWidget()
        separator.setStyleSheet("background-color: #d0d0d0;")
        separator.setFixedWidth(1)
        return separator

    def build_horizontal_separator(self):
        """Build a horizontal separator with margins.

        Returns:
            QHBoxLayout containing the horizontal separator
        """
        container = QHBoxLayout()
        container.setContentsMargins(40, 0, 40, 0)
        separator = QWidget()
        separator.setStyleSheet("background-color: #d0d0d0;")
        separator.setFixedHeight(1)
        container.addWidget(separator)
        return container

    def build_left_buttons(self, on_ip_button_event_filter, on_wifi_click, on_flip_display_click):
        """Build the left button group (IP, WiFi Setup, Flip Display).

        Args:
            on_ip_button_event_filter: Event filter object for IP button
            on_wifi_click: Callback for WiFi Setup button
            on_flip_display_click: Callback for Flip Display button

        Returns:
            tuple: (QWidget container, ip_button, wifi_button, flip_display_button)
        """
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        ip_button = QPushButton("IP")
        ip_button.setStyleSheet(default_action_button_stylesheet(self.font_family))
        ip_button.installEventFilter(on_ip_button_event_filter)
        layout.addWidget(ip_button)

        wifi_button = QPushButton("WiFi Setup")
        wifi_button.setStyleSheet(default_action_button_stylesheet(self.font_family))
        wifi_button.clicked.connect(on_wifi_click)
        layout.addWidget(wifi_button)

        flip_display_button = QPushButton("Flip Display")
        flip_display_button.setStyleSheet(default_action_button_stylesheet(self.font_family))
        flip_display_button.clicked.connect(on_flip_display_click)
        layout.addWidget(flip_display_button)

        container.setLayout(layout)
        return container, ip_button, wifi_button, flip_display_button

    def build_center_section(self, on_save_click, get_timestamp_fn):
        """Build the center section with Save button and status labels.

        Args:
            on_save_click: Callback for Save button
            get_timestamp_fn: Function to get config last saved timestamp

        Returns:
            tuple: (QWidget container, timestamp_label, unsaved_warning_label)
        """
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

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
        save_button.clicked.connect(on_save_click)
        layout.addWidget(save_button, alignment=Qt.AlignCenter)

        labels_container = QHBoxLayout()
        labels_container.setSpacing(10)

        timestamp_label = QLabel()
        timestamp_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 14px; color: #666;"
        )
        timestamp_label.setAlignment(Qt.AlignCenter)
        timestamp_label.setText(f"Last saved: {get_timestamp_fn()}")
        labels_container.addWidget(timestamp_label)

        unsaved_warning_label = QLabel("Changes not yet saved!")
        unsaved_warning_label.setStyleSheet(
            f"font-family: {self.font_family}; font-size: 14px; color: #e74c3c;"
        )
        unsaved_warning_label.setAlignment(Qt.AlignCenter)
        unsaved_warning_label.hide()
        labels_container.addWidget(unsaved_warning_label)

        layout.addLayout(labels_container)
        container.setLayout(layout)

        return container, timestamp_label, unsaved_warning_label

    def build_right_buttons(self, on_update_click, on_shutdown_click):
        """Build the right button group (Update, Shutdown).

        Args:
            on_update_click: Callback for Update button
            on_shutdown_click: Callback for Shutdown button

        Returns:
            tuple: (QWidget container, update_button, shutdown_exit_button)
        """
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        update_button = QPushButton("Update")
        update_button.setStyleSheet(
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
        update_button.clicked.connect(on_update_click)
        layout.addWidget(update_button)

        shutdown_exit_button = QPushButton("Shutdown")
        shutdown_exit_button.setStyleSheet(
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
        shutdown_exit_button.clicked.connect(on_shutdown_click)
        layout.addWidget(shutdown_exit_button)

        container.setLayout(layout)
        return container, update_button, shutdown_exit_button

    def build_bottom_row(self, left_buttons, center_section, right_buttons):
        """Build the bottom row grid layout.

        Args:
            left_buttons: Widget for left buttons
            center_section: Widget for center section
            right_buttons: Widget for right buttons

        Returns:
            QGridLayout for the bottom row
        """
        grid = QGridLayout()
        grid.setContentsMargins(20, 0, 20, 20)
        grid.setHorizontalSpacing(10)

        grid.addWidget(left_buttons, 0, 0, Qt.AlignLeft | Qt.AlignBottom)
        grid.addWidget(center_section, 0, 1, Qt.AlignCenter | Qt.AlignBottom)
        grid.addWidget(right_buttons, 0, 2, Qt.AlignRight | Qt.AlignBottom)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        return grid
