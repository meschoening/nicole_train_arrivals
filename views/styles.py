"""Stylesheet and icon utilities for the display UI."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap


def create_colored_circle_icon(color_hex):
    """Create a colored circle icon for dropdown items.

    Args:
        color_hex: Hex color string (e.g., '#BF0D3E')

    Returns:
        QIcon with a filled circle of the specified color
    """
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()

    return QIcon(pixmap)


def create_multi_colored_circle_icon(color_list):
    """Create an icon with multiple overlapping colored circles for dropdown items.

    Args:
        color_list: List of hex color strings

    Returns:
        QIcon with overlapping circles, or single circle if only one color
    """
    if not color_list:
        return create_colored_circle_icon('#808080')

    if len(color_list) == 1:
        return create_colored_circle_icon(color_list[0])

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


def combo_box_stylesheet(font_family):
    """Return the stylesheet for QComboBox widgets.

    Args:
        font_family: Font family name string

    Returns:
        CSS stylesheet string for QComboBox
    """
    return f"""
        QComboBox {{
            font-family: {font_family};
            font-size: 18px;
            padding: 7px;
            border: 1px solid #ccc;
            border-radius: 3px;
            background-color: white;
        }}
        QComboBox:hover {{
            border: 1px solid #999;
        }}
        QComboBox QAbstractItemView {{
            font-family: {font_family};
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


def checkbox_indicator_stylesheet():
    """Return the stylesheet for QCheckBox indicator styling.

    Returns:
        CSS stylesheet string for QCheckBox
    """
    return """
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
    """


def main_display_error_label_stylesheet(font_family):
    """Return the stylesheet for error labels on the main display.

    Args:
        font_family: Font family name string

    Returns:
        CSS stylesheet string for error labels
    """
    return (
        f"font-family: {font_family}; font-size: 14px; font-weight: bold; "
        "color: white; background-color: #e74c3c; padding: 4px 8px; border-radius: 4px;"
    )


def update_button_stylesheet(font_family, color):
    """Return the stylesheet for the update button in different states.

    Args:
        font_family: Font family name string
        color: Color state - "green", "orange", "red", "light_green", or "neutral"

    Returns:
        CSS stylesheet string for the update button
    """
    color_configs = {
        "green": {
            "bg": "#4CAF50",
            "hover": "#45a049",
            "pressed": "#3d8b40",
            "text": "white",
        },
        "orange": {
            "bg": "#FFC107",
            "hover": "#FFB300",
            "pressed": "#FFA000",
            "text": "white",
        },
        "red": {
            "bg": "#f44336",
            "hover": "#da190b",
            "pressed": "#c1170a",
            "text": "white",
        },
        "light_green": {
            "bg": "#a5d6a7",
            "hover": "#81c784",
            "pressed": "#66bb6a",
            "text": "#1b5e20",
        },
        "neutral": {
            "bg": "#e0e0e0",
            "hover": "#d0d0d0",
            "pressed": "#c0c0c0",
            "text": "black",
        },
    }

    config = color_configs.get(color, color_configs["neutral"])

    return f"""
        QPushButton {{
            font-family: {font_family};
            font-size: 20px;
            font-weight: bold;
            padding: 8px 16px;
            background-color: {config["bg"]};
            color: {config["text"]};
            border: none;
            border-radius: 5px;
        }}
        QPushButton:hover {{
            background-color: {config["hover"]};
        }}
        QPushButton:pressed {{
            background-color: {config["pressed"]};
            padding-bottom: 7px;
        }}
    """


def default_action_button_stylesheet(font_family):
    """Return the stylesheet for default action buttons (grey background).

    Args:
        font_family: Font family name string

    Returns:
        CSS stylesheet string for action buttons
    """
    return f"""
        QPushButton {{
            font-family: {font_family};
            font-size: 20px;
            font-weight: bold;
            padding: 8px 12px;
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


def confirm_button_stylesheet(font_family):
    """Return the stylesheet for confirmation state buttons (red background).

    Args:
        font_family: Font family name string

    Returns:
        CSS stylesheet string for confirm buttons
    """
    return f"""
        QPushButton {{
            font-family: {font_family};
            font-size: 20px;
            font-weight: bold;
            padding: 8px 12px;
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
            padding-bottom: 7px;
        }}
    """


def shutdown_exit_button_stylesheet(font_family, active=False):
    """Return the stylesheet for the shutdown/exit button.

    Args:
        font_family: Font family name string
        active: Whether the button is in active/pressed state

    Returns:
        CSS stylesheet string for the shutdown button
    """
    if active:
        return f"""
            QPushButton {{
                font-family: {font_family};
                font-size: 20px;
                font-weight: bold;
                padding: 8px 16px;
                background-color: #c8c8c8;
                border: none;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: #b8b8b8;
            }}
            QPushButton:pressed {{
                background-color: #a8a8a8;
                padding-bottom: 7px;
            }}
        """
    else:
        return f"""
            QPushButton {{
                font-family: {font_family};
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
