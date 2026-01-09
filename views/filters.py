"""Event filters and input helpers for the UI."""

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QAbstractItemView


class TouchscreenComboViewFilter(QObject):
    """Event filter for QComboBox views to handle touchscreen taps correctly."""

    def __init__(self, combo_box):
        super().__init__()
        self.combo_box = combo_box
        self.pressed_index = None

    def eventFilter(self, obj, event):
        """Filter events to prevent dropdown from closing on mouse press for touchscreens."""
        view = self.combo_box.view()
        if isinstance(obj, QAbstractItemView) and obj == view:
            if event.type() == QEvent.MouseButtonPress:
                if isinstance(event, QMouseEvent):
                    index = obj.indexAt(event.pos())
                    if index.isValid():
                        self.pressed_index = index.row()
                        obj.setCurrentIndex(index)
                        return True

            elif event.type() == QEvent.MouseButtonRelease:
                if isinstance(event, QMouseEvent):
                    index = obj.indexAt(event.pos())
                    if self.pressed_index is not None:
                        if index.isValid():
                            self.combo_box.setCurrentIndex(index.row())
                        else:
                            self.combo_box.setCurrentIndex(self.pressed_index)
                        self.combo_box.hidePopup()
                        self.pressed_index = None
                        return True
                    self.pressed_index = None

        return False
