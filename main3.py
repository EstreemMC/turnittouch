import sys
import time
import threading
from enum import Enum, auto

import cv2
import numpy as np
from pynput import keyboard

from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal, QEvent
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygon,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# ============================================================
# CONFIG
# ============================================================
CAM_W, CAM_H = 1280, 720

config = {
    # Yellow / gold object HSV range
    "low_h": 10,
    "high_h": 32,
    "low_s": 90,
    "high_s": 255,
    "low_v": 130,
    "high_v": 255,

    # Tracking behavior
    "tracking_enabled": False,
    "show_camera_window": True,
    "mouse_smoothing": 0.18,
    "release_timeout": 0.20,
    "min_contour_area": 600,
}

# ============================================================
# OVERLAY TOOL ENUMS
# ============================================================
class Tool(Enum):
    SELECT = auto()
    DRAW = auto()
    ERASER = auto()
    SHAPE = auto()
    LINE = auto()
    STICKY = auto()
    TEXT = auto()
    TABLE = auto()
    CURSOR = auto()


class DrawableItemType(Enum):
    FREEHAND = auto()
    LINE = auto()
    RECT = auto()
    STICKY = auto()
    TEXT = auto()
    TABLE = auto()


# ============================================================
# DRAWABLE ITEM
# ============================================================
class DrawableItem:
    def __init__(self, item_type, color, thickness, points=None, rect=None, text=""):
        self.item_type = item_type
        self.color = QColor(color)
        self.thickness = thickness
        self.points = points or []
        self.rect = rect
        self.text = text

    def contains(self, point: QPoint) -> bool:
        if self.item_type == DrawableItemType.FREEHAND and self.points:
            for p in self.points:
                if (p - point).manhattanLength() <= 12:
                    return True
            return False

        if self.item_type == DrawableItemType.LINE and len(self.points) == 2:
            return QRect(self.points[0], self.points[1]).normalized().adjusted(-8, -8, 8, 8).contains(point)

        if self.rect:
            return self.rect.adjusted(-8, -8, 8, 8).contains(point)

        return False

    def move_by(self, delta: QPoint):
        if self.item_type in (DrawableItemType.FREEHAND, DrawableItemType.LINE):
            self.points = [p + delta for p in self.points]
        elif self.rect:
            self.rect.translate(delta)


# ============================================================
# TOOLBAR BUTTON
# ============================================================
class IconButton(QToolButton):
    def __init__(self, tool_type=None):
        super().__init__()
        self.tool_type = tool_type
        self.icon_color = QColor("#111111")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 46)
        self.setStyleSheet("""
            QToolButton {
                border: none;
                border-radius: 14px;
                background: transparent;
            }
            QToolButton:hover {
                background: rgba(0, 0, 0, 0.07);
            }
            QToolButton:checked {
                background: rgba(0, 0, 0, 0.12);
            }
        """)

    def paintEvent(self, event):
        super().paintEvent(event)

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        color = QColor("#111111")
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)

        w = self.width()
        h = self.height()
        cx = w // 2
        cy = h // 2

        if self.tool_type == Tool.SELECT:
            arrow_len = 6
            p.drawLine(cx, cy - arrow_len, cx, cy + arrow_len)
            p.drawLine(cx, cy - arrow_len, cx - 3, cy - arrow_len + 3)
            p.drawLine(cx, cy - arrow_len, cx + 3, cy - arrow_len + 3)
            p.drawLine(cx, cy + arrow_len, cx - 3, cy + arrow_len - 3)
            p.drawLine(cx, cy + arrow_len, cx + 3, cy + arrow_len - 3)
            p.drawLine(cx - arrow_len, cy, cx + arrow_len, cy)
            p.drawLine(cx - arrow_len, cy, cx - arrow_len + 3, cy - 3)
            p.drawLine(cx - arrow_len, cy, cx - arrow_len + 3, cy + 3)
            p.drawLine(cx + arrow_len, cy, cx + arrow_len - 3, cy - 3)
            p.drawLine(cx + arrow_len, cy, cx + arrow_len - 3, cy + 3)

        elif self.tool_type == Tool.CURSOR:
            red_pen = QPen(QColor("#ef4444"), 2.2)
            red_pen.setCapStyle(Qt.RoundCap)
            p.setPen(red_pen)
            p.drawLine(cx - 6, cy - 6, cx + 6, cy + 6)
            p.drawLine(cx + 6, cy - 6, cx - 6, cy + 6)

        elif self.tool_type == Tool.DRAW:
            pen = QPen(self.icon_color, 2.6)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.drawLine(cx - 8, cy + 8, cx + 4, cy - 4)
            p.drawLine(cx + 4, cy - 4, cx + 8, cy)
            p.drawLine(cx - 5, cy + 11, cx + 7, cy - 1)
            p.setPen(QPen(self.icon_color, 2.2))
            path = QPainterPath()
            path.moveTo(cx - 12, cy + 14)
            path.cubicTo(cx - 8, cy + 9, cx - 4, cy + 16, cx, cy + 12)
            path.cubicTo(cx + 3, cy + 10, cx + 6, cy + 16, cx + 10, cy + 13)
            p.drawPath(path)

        elif self.tool_type == Tool.ERASER:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#9ca3af"))
            p.drawRoundedRect(cx - 10, cy - 2, 16, 10, 3, 3)
            p.setBrush(QColor("#111827"))
            p.drawRoundedRect(cx + 3, cy - 2, 7, 10, 2, 2)
            p.setBrush(QColor("#d1d5db"))
            p.drawRoundedRect(cx - 12, cy - 5, 8, 16, 3, 3)

        elif self.tool_type == Tool.SHAPE:
            p.setPen(pen)
            p.drawRect(cx - 10, cy - 8, 20, 16)

        elif self.tool_type == Tool.LINE:
            blue_pen = QPen(QColor("#2563eb"), 3)
            blue_pen.setCapStyle(Qt.RoundCap)
            p.setPen(blue_pen)
            p.drawLine(cx - 11, cy + 10, cx + 10, cy - 9)

        elif self.tool_type == Tool.STICKY:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#facc15"))
            p.drawRoundedRect(cx - 10, cy - 10, 20, 20, 4, 4)
            tri = QPolygon([
                QPoint(cx + 10, cy + 10),
                QPoint(cx + 1, cy + 10),
                QPoint(cx + 10, cy + 1),
            ])
            p.setBrush(QColor("#fb923c"))
            p.drawPolygon(tri)

        elif self.tool_type == Tool.TEXT:
            purple_pen = QPen(QColor("#9333ea"), 3)
            purple_pen.setCapStyle(Qt.RoundCap)
            p.setPen(purple_pen)
            p.drawLine(cx - 10, cy - 9, cx + 10, cy - 9)
            p.drawLine(cx, cy - 9, cx, cy + 11)

        elif self.tool_type == Tool.TABLE:
            table_pen = QPen(QColor("#1e3a8a"), 2.3)
            p.setPen(table_pen)
            rect = QRect(cx - 10, cy - 10, 20, 20)
            p.drawRect(rect)
            p.drawLine(cx - 10, cy - 3, cx + 10, cy - 3)
            p.drawLine(cx - 10, cy + 4, cx + 10, cy + 4)
            p.drawLine(cx - 3, cy - 10, cx - 3, cy + 10)
            p.drawLine(cx + 4, cy - 10, cx + 4, cy + 10)


# ============================================================
# TABLE DIALOG
# ============================================================
class NumpadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Table Size")
        self.setModal(True)

        layout = QVBoxLayout(self)

        rows_layout = QHBoxLayout()
        rows_label = QLabel("Rows:")
        rows_label.mousePressEvent = lambda e: self.rows_edit.setFocus()
        rows_layout.addWidget(rows_label)
        self.rows_edit = QLineEdit("3")
        self.rows_edit.setMaxLength(2)
        rows_layout.addWidget(self.rows_edit)
        layout.addLayout(rows_layout)

        cols_layout = QHBoxLayout()
        cols_label = QLabel("Columns:")
        cols_label.mousePressEvent = lambda e: self.cols_edit.setFocus()
        cols_layout.addWidget(cols_label)
        self.cols_edit = QLineEdit("3")
        self.cols_edit.setMaxLength(2)
        cols_layout.addWidget(self.cols_edit)
        layout.addLayout(cols_layout)

        numpad_layout = QGridLayout()
        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('0', 3, 1), ('⌫', 3, 2),
        ]
        for text, row, col in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked=False, t=text: self.on_button_click(t))
            numpad_layout.addWidget(btn, row, col)

        layout.addLayout(numpad_layout)

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)

        self.current_edit = self.rows_edit

    def on_button_click(self, text):
        if self.rows_edit.hasFocus():
            edit = self.rows_edit
        elif self.cols_edit.hasFocus():
            edit = self.cols_edit
        else:
            edit = self.current_edit

        if text == '⌫':
            edit.backspace()
        else:
            edit.insert(text)

    def get_values(self):
        try:
            rows = int(self.rows_edit.text())
            cols = int(self.cols_edit.text())
            return rows, cols
        except ValueError:
            return 3, 3


# ============================================================
# FLOATING TOOLBAR
# ============================================================
class FloatingToolbar(QFrame):
    tool_changed = Signal(object)
    color_changed = Signal(QColor)
    thickness_changed = Signal(int)
    clear_requested = Signal()
    undo_requested = Signal()
    hide_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tool = Tool.DRAW
        self.current_color = QColor("#8b5cf6")
        self.current_thickness = 4
        self.panel_expanded = False

        self.setObjectName("toolbar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QFrame#toolbar {
                background: rgba(245, 245, 245, 240);
                border-radius: 28px;
            }
            QPushButton {
                border: none;
                border-radius: 10px;
                background: rgba(0, 0, 0, 0.06);
                padding: 8px 10px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.10);
            }
            QLabel {
                color: #222;
                font-size: 12px;
                font-weight: 600;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 14, 10, 14)
        self.main_layout.setSpacing(10)

        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setFixedHeight(30)
        self.toggle_btn.clicked.connect(self.toggle_panel)
        self.main_layout.addWidget(self.toggle_btn)

        self.hide_btn = IconButton(tool_type=Tool.CURSOR)
        self.hide_btn.setToolTip("Hide Overlay")
        self.hide_btn.clicked.connect(self.hide_requested.emit)
        self.main_layout.addWidget(self.hide_btn, alignment=Qt.AlignCenter)

        self.tool_buttons = {}
        self.add_tool_button(Tool.SELECT, "Select")
        self.add_tool_button(Tool.DRAW, "Draw")
        self.add_tool_button(Tool.ERASER, "Eraser")
        self.add_tool_button(Tool.SHAPE, "Shape")
        self.add_tool_button(Tool.LINE, "Line")
        self.add_tool_button(Tool.STICKY, "Sticky note")
        self.add_tool_button(Tool.TEXT, "Text")
        self.add_tool_button(Tool.TABLE, "Table")

        self.panel = QFrame()
        self.panel.setStyleSheet("background: transparent;")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        panel_layout.setSpacing(10)

        panel_layout.addWidget(QLabel("Color"))

        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self.pick_color)
        panel_layout.addWidget(self.color_btn)
        self.update_color_button()

        panel_layout.addWidget(QLabel("Thickness"))

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, 20)
        self.slider.setValue(self.current_thickness)
        self.slider.valueChanged.connect(self.on_thickness_changed)
        panel_layout.addWidget(self.slider)

        self.thickness_value = QLabel(str(self.current_thickness))
        panel_layout.addWidget(self.thickness_value)

        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self.undo_requested.emit)
        panel_layout.addWidget(self.undo_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        panel_layout.addWidget(self.clear_btn)

        self.panel.setVisible(False)
        self.main_layout.addWidget(self.panel)

        self.tool_buttons[Tool.DRAW].setChecked(True)
        self.setFixedWidth(88)

    def add_tool_button(self, tool, tooltip):
        btn = IconButton(tool_type=tool)
        btn.icon_color = self.current_color if tool == Tool.DRAW else QColor("#111111")
        btn.setToolTip(tooltip)
        btn.clicked.connect(lambda checked=False, t=tool: self.set_tool(t))
        self.main_layout.addWidget(btn, alignment=Qt.AlignCenter)
        self.tool_buttons[tool] = btn

    def set_tool(self, tool):
        self.current_tool = tool
        for t, btn in self.tool_buttons.items():
            btn.setChecked(t == tool)
        self.tool_changed.emit(tool)

    def toggle_panel(self):
        self.panel_expanded = not self.panel_expanded
        self.panel.setVisible(self.panel_expanded)
        self.toggle_btn.setText("▶" if self.panel_expanded else "◀")
        self.setFixedWidth(240 if self.panel_expanded else 88)
        self.adjustSize()

    def pick_color(self):
        color = QColorDialog.getColor(self.current_color, self, "Pick Color")
        if color.isValid():
            self.current_color = color
            self.update_color_button()
            self.color_changed.emit(color)

    def update_color_button(self):
        self.color_btn.setStyleSheet(
            f"background:{self.current_color.name()}; min-height: 34px; border-radius: 10px;"
        )
        self.color_btn.setText(self.current_color.name())
        if Tool.DRAW in self.tool_buttons:
            self.tool_buttons[Tool.DRAW].icon_color = self.current_color
            self.tool_buttons[Tool.DRAW].update()

    def on_thickness_changed(self, value):
        self.current_thickness = value
        self.thickness_value.setText(str(value))
        self.thickness_changed.emit(value)


# ============================================================
# OVERLAY WINDOW
# ============================================================
class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.overlay_enabled = False

        self.items = []
        self.current_tool = Tool.DRAW
        self.current_color = QColor("#8b5cf6")
        self.current_thickness = 4

        self.current_points = []
        self.preview_rect = None
        self.preview_line = None

        self.dragging_item = None
        self.last_mouse_pos = None

        self.tracking_active = False
        self.last_tracking_point = None
        self.last_tracking_seen = 0.0

        self.setup_window()
        self.setup_toolbar()

    def setup_window(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.hide()

    def setup_toolbar(self):
        self.toolbar = FloatingToolbar(self)
        self.toolbar.tool_changed.connect(self.on_tool_changed)
        self.toolbar.color_changed.connect(self.on_color_changed)
        self.toolbar.thickness_changed.connect(self.on_thickness_changed)
        self.toolbar.clear_requested.connect(self.clear_items)
        self.toolbar.undo_requested.connect(self.undo_item)
        self.toolbar.hide_requested.connect(self.hide_overlay)
        self.toolbar.hide()

    def point_is_in_toolbar(self, pos: QPoint) -> bool:
        return self.toolbar.isVisible() and self.toolbar.geometry().contains(pos)

    def on_tool_changed(self, tool):
        self.current_tool = tool
        self.reset_preview_state()
        self.setFocus()

    def on_color_changed(self, color):
        self.current_color = color
        self.setFocus()

    def on_thickness_changed(self, value):
        self.current_thickness = value
        self.setFocus()

    def reset_preview_state(self):
        self.current_points = []
        self.preview_rect = None
        self.preview_line = None
        self.dragging_item = None
        self.last_mouse_pos = None
        self.tracking_active = False
        self.last_tracking_point = None
        self.update()

    def show_overlay(self):
        screen = QGuiApplication.primaryScreen()
        geo = screen.geometry()
        self.setGeometry(geo)

        self.toolbar.move(14, max(40, geo.height() // 6))
        self.toolbar.show()
        self.toolbar.raise_()

        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

        self.overlay_enabled = True
        self.reset_preview_state()
        print("Overlay ON")

    def hide_overlay(self):
        self.hide()
        self.toolbar.hide()
        self.overlay_enabled = False
        config["tracking_enabled"] = False
        self.reset_preview_state()
        print("Overlay OFF")

    def clear_items(self):
        self.items.clear()
        self.update()
        self.setFocus()

    def undo_item(self):
        if self.items:
            self.items.pop()
            self.update()
        self.setFocus()

    def erase_at_point(self, pos: QPoint):
        for i in range(len(self.items) - 1, -1, -1):
            if self.items[i].contains(pos):
                self.items.pop(i)
                self.update()
                return

    def erase_near_path_point(self, pos: QPoint):
        erase_radius = max(10, self.current_thickness + 6)

        for i in range(len(self.items) - 1, -1, -1):
            item = self.items[i]

            if item.item_type == DrawableItemType.FREEHAND:
                for p in item.points:
                    if (p - pos).manhattanLength() <= erase_radius:
                        self.items.pop(i)
                        self.update()
                        return

            elif item.item_type == DrawableItemType.LINE and len(item.points) == 2:
                if QRect(item.points[0], item.points[1]).normalized().adjusted(
                    -erase_radius, -erase_radius, erase_radius, erase_radius
                ).contains(pos):
                    self.items.pop(i)
                    self.update()
                    return

            elif item.rect and item.rect.adjusted(
                -erase_radius, -erase_radius, erase_radius, erase_radius
            ).contains(pos):
                self.items.pop(i)
                self.update()
                return

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_overlay()
        elif event.key() == Qt.Key_C:
            self.clear_items()
        elif event.key() == Qt.Key_Z:
            self.undo_item()

    def mousePressEvent(self, event: QMouseEvent):
        if not self.overlay_enabled:
            return

        pos = event.position().toPoint()
        if self.point_is_in_toolbar(pos):
            return

        self._start_action(pos)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.overlay_enabled:
            return

        pos = event.position().toPoint()
        self._update_action(pos, event.buttons() & Qt.LeftButton)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self.overlay_enabled:
            return

        self._finish_action()
        self.update()

    def _start_action(self, pos: QPoint):
        if self.current_tool == Tool.DRAW:
            self.current_points = [pos]

        elif self.current_tool == Tool.LINE:
            self.preview_line = (pos, pos)

        elif self.current_tool == Tool.ERASER:
            self.erase_at_point(pos)

        elif self.current_tool == Tool.SHAPE:
            self.preview_rect = QRect(pos, pos)

        elif self.current_tool == Tool.SELECT:
            self.dragging_item = self.find_top_item(pos)
            self.last_mouse_pos = pos

        elif self.current_tool == Tool.TEXT:
            self.add_text_box(pos)

        elif self.current_tool == Tool.STICKY:
            self.add_sticky(pos)

        elif self.current_tool == Tool.TABLE:
            self.add_table(pos)

    def _update_action(self, pos: QPoint, pressed: bool):
        if self.current_tool == Tool.ERASER and pressed:
            if not self.point_is_in_toolbar(pos):
                self.erase_near_path_point(pos)

        elif self.current_tool == Tool.DRAW and self.current_points:
            if not self.point_is_in_toolbar(pos):
                self.current_points.append(pos)

        elif self.current_tool == Tool.LINE and self.preview_line:
            if not self.point_is_in_toolbar(pos):
                self.preview_line = (self.preview_line[0], pos)

        elif self.current_tool == Tool.SHAPE and self.preview_rect:
            if not self.point_is_in_toolbar(pos):
                self.preview_rect = QRect(self.preview_rect.topLeft(), pos).normalized()

        elif self.current_tool == Tool.SELECT and self.dragging_item and self.last_mouse_pos:
            if not self.point_is_in_toolbar(pos):
                delta = pos - self.last_mouse_pos
                self.dragging_item.move_by(delta)
                self.last_mouse_pos = pos

    def _finish_action(self):
        if self.current_tool == Tool.DRAW and self.current_points:
            self.items.append(
                DrawableItem(
                    DrawableItemType.FREEHAND,
                    self.current_color,
                    self.current_thickness,
                    points=self.current_points[:],
                )
            )
            self.current_points = []

        elif self.current_tool == Tool.LINE and self.preview_line:
            start, end = self.preview_line
            self.items.append(
                DrawableItem(
                    DrawableItemType.LINE,
                    self.current_color,
                    self.current_thickness,
                    points=[start, end],
                )
            )
            self.preview_line = None

        elif self.current_tool == Tool.SHAPE and self.preview_rect:
            self.items.append(
                DrawableItem(
                    DrawableItemType.RECT,
                    self.current_color,
                    self.current_thickness,
                    rect=self.preview_rect.normalized(),
                )
            )
            self.preview_rect = None

        elif self.current_tool == Tool.SELECT:
            self.dragging_item = None
            self.last_mouse_pos = None

    def handle_tracking_point(self, global_x: float, global_y: float, visible: bool):
        if not self.overlay_enabled or not config["tracking_enabled"]:
            self.end_tracking_action()
            return

        gx = int(np.clip(global_x, self.geometry().left(), self.geometry().right() - 1))
        gy = int(np.clip(global_y, self.geometry().top(), self.geometry().bottom() - 1))

        if not visible:
            if self.tracking_active and (time.time() - self.last_tracking_seen) > config["release_timeout"]:
                self.end_tracking_action()
            return

        local = self.mapFromGlobal(QPoint(gx, gy))
        if self.point_is_in_toolbar(local):
            return

        self.last_tracking_seen = time.time()

        if not self.tracking_active:
            self.tracking_active = True
            self.last_tracking_point = local
            self._start_action(local)
        else:
            self._update_action(local, True)
            self.last_tracking_point = local

        self.update()

    def end_tracking_action(self):
        if not self.tracking_active:
            return

        self._finish_action()
        self.tracking_active = False
        self.last_tracking_point = None
        self.update()

    def find_top_item(self, pos):
        for item in reversed(self.items):
            if item.contains(pos):
                return item
        return None

    def add_text_box(self, pos):
        text, ok = QInputDialog.getText(self, "Add Text", "Enter text:")
        if ok and text.strip():
            rect = QRect(pos, QSize(220, 70))
            self.items.append(
                DrawableItem(
                    DrawableItemType.TEXT,
                    self.current_color,
                    self.current_thickness,
                    rect=rect,
                    text=text.strip(),
                )
            )
            self.update()

    def add_sticky(self, pos):
        text, ok = QInputDialog.getText(self, "Add Sticky Note", "Enter text:")
        if ok and text.strip():
            rect = QRect(pos, QSize(180, 120))
            self.items.append(
                DrawableItem(
                    DrawableItemType.STICKY,
                    QColor("#ffd54f"),
                    self.current_thickness,
                    rect=rect,
                    text=text.strip(),
                )
            )
            self.update()

    def add_table(self, pos):
        dialog = NumpadDialog(self)
        if dialog.exec() == QDialog.Accepted:
            rows, cols = dialog.get_values()
        else:
            return

        if rows < 1 or rows > 20 or cols < 1 or cols > 20:
            return

        cell_w = 70
        cell_h = 38
        rect = QRect(pos, QSize(cols * cell_w, rows * cell_h))
        self.items.append(
            DrawableItem(
                DrawableItemType.TABLE,
                self.current_color,
                max(1, self.current_thickness),
                rect=rect,
                text=f"{rows},{cols}",
            )
        )
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        for item in self.items:
            self.paint_item(painter, item)

        if self.current_points:
            pen = QPen(self.current_color, self.current_thickness)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            for i in range(1, len(self.current_points)):
                painter.drawLine(self.current_points[i - 1], self.current_points[i])

        if self.preview_line:
            pen = QPen(self.current_color, self.current_thickness, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(*self.preview_line)

        if self.preview_rect:
            pen = QPen(self.current_color, self.current_thickness, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(self.preview_rect)

    def paint_item(self, painter, item: DrawableItem):
        pen = QPen(item.color, item.thickness)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        if item.item_type == DrawableItemType.FREEHAND:
            for i in range(1, len(item.points)):
                painter.drawLine(item.points[i - 1], item.points[i])

        elif item.item_type == DrawableItemType.LINE:
            if len(item.points) == 2:
                painter.drawLine(item.points[0], item.points[1])

        elif item.item_type == DrawableItemType.RECT:
            painter.drawRect(item.rect)

        elif item.item_type == DrawableItemType.STICKY:
            painter.fillRect(item.rect, QColor("#facc15"))
            corner = QPolygon([
                item.rect.bottomRight(),
                item.rect.bottomRight() - QPoint(20, 0),
                item.rect.bottomRight() - QPoint(0, 20),
            ])
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#fb923c"))
            painter.drawPolygon(corner)
            painter.setPen(QPen(Qt.black, 1))
            painter.setFont(QFont("Arial", 12, QFont.Bold))
            painter.drawText(item.rect.adjusted(10, 10, -10, -10), Qt.TextWordWrap, item.text)

        elif item.item_type == DrawableItemType.TEXT:
            painter.setPen(QPen(item.color, 1))
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(item.rect, Qt.TextWordWrap, item.text)

        elif item.item_type == DrawableItemType.TABLE:
            rows, cols = map(int, item.text.split(","))
            painter.setPen(QPen(item.color, max(1, item.thickness)))
            painter.drawRect(item.rect)

            cell_w = item.rect.width() / cols
            cell_h = item.rect.height() / rows

            for r in range(1, rows):
                y = int(item.rect.top() + r * cell_h)
                painter.drawLine(item.rect.left(), y, item.rect.right(), y)

            for c in range(1, cols):
                x = int(item.rect.left() + c * cell_w)
                painter.drawLine(x, item.rect.top(), x, item.rect.bottom())


# ============================================================
# THREAD-SAFE EVENT
# ============================================================
class _CallEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, callback):
        super().__init__(self.EVENT_TYPE)
        self.callback = callback


class OverlayApp(QApplication):
    pass


class OverlayReceiver(OverlayWindow):
    def event(self, event):
        if event.type() == _CallEvent.EVENT_TYPE:
            event.callback()
            return True
        return super().event(event)


# ============================================================
# CAMERA THREAD
# ============================================================
class SmartCamera(threading.Thread):
    def __init__(self, index, name, target_rect):
        super().__init__(daemon=True)
        self.index = index
        self.name = name
        self.target_rect = target_rect

        self.cap = None
        self.connected = False
        self.lock = threading.Lock()

        self.frame = np.zeros((CAM_H, CAM_W, 3), dtype=np.uint8)
        self.last_det = None
        self.pts = []
        self.homography = None

    def connect(self):
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]

        for backend in backends:
            cap = cv2.VideoCapture(self.index, backend)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
                cap.set(cv2.CAP_PROP_FPS, 30)
                self.cap = cap
                self.connected = True
                print(f"Connected to {self.name} (index {self.index})")
                return True

        return False

    def run(self):
        while True:
            if not self.connected:
                if not self.connect():
                    time.sleep(1.5)
                    continue

            ret, img = self.cap.read()

            if not ret or img is None:
                self.connected = False
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
                time.sleep(0.5)
                continue

            hsv = cv2.cvtColor(cv2.GaussianBlur(img, (7, 7), 0), cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(
                hsv,
                np.array([config["low_h"], config["low_s"], config["low_v"]]),
                np.array([config["high_h"], config["high_s"], config["high_v"]]),
            )

            mask = cv2.erode(mask, None, iterations=1)
            mask = cv2.dilate(mask, None, iterations=2)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            det = None
            if contours:
                best_cnt = max(contours, key=cv2.contourArea)
                if cv2.contourArea(best_cnt) > config["min_contour_area"]:
                    x, y, w_obj, h_obj = cv2.boundingRect(best_cnt)
                    det = (x + w_obj // 2, y + h_obj // 2)
                    cv2.rectangle(img, (x, y), (x + w_obj, y + h_obj), (0, 0, 0), 2)
                    cv2.circle(img, det, 6, (0, 0, 0), -1)

            if len(self.pts) == 4:
                poly = np.array(self.pts, np.int32).reshape((-1, 1, 2))
                cv2.polylines(img, [poly], True, (0, 0, 0), 3)

            for p in self.pts:
                cv2.circle(img, (int(p[0]), int(p[1])), 6, (0, 0, 0), -1)

            with self.lock:
                self.frame = img
                self.last_det = det


# ============================================================
# CAMERA CONTROLLER
# ============================================================
class CameraController(threading.Thread):
    def __init__(self, window, app):
        super().__init__(daemon=True)
        self.window = window
        self.app = app
        self.running = True

        screen = QGuiApplication.primaryScreen()
        geo = screen.geometry()
        self.screen_w = geo.width()
        self.screen_h = geo.height()
        mid_x = self.screen_w // 2

        c1_dest = np.array(
            [[mid_x, 0], [self.screen_w, 0], [self.screen_w, self.screen_h], [mid_x, self.screen_h]],
            dtype="float32"
        )
        c2_dest = np.array(
            [[0, 0], [mid_x, 0], [mid_x, self.screen_h], [0, self.screen_h]],
            dtype="float32"
        )

        self.cams = [
            SmartCamera(1, "CAM 1 (RIGHT)", c1_dest),
            SmartCamera(2, "CAM 2 (LEFT)", c2_dest),
        ]

        for c in self.cams:
            c.start()
            time.sleep(0.75)

        self.cur_x = self.screen_w / 2
        self.cur_y = self.screen_h / 2
        self.active_idx = 0

    def post(self, callback):
        self.app.postEvent(self.window, _CallEvent(callback))

    def all_calibrated(self):
        return len(self.cams) > 0 and all(c.homography is not None for c in self.cams)

    def compute_target(self):
        target = None
        frames = []

        for c in self.cams:
            with c.lock:
                frame_copy = c.frame.copy()
                frames.append(cv2.resize(frame_copy, (640, 360)))

                if c.homography is not None and c.last_det is not None and len(c.pts) == 4:
                    dist = cv2.pointPolygonTest(
                        np.array(c.pts, np.float32),
                        (c.last_det[0], c.last_det[1]),
                        False
                    )
                    if dist >= 0:
                        p_mat = np.array([[[c.last_det[0], c.last_det[1]]]], dtype=np.float32)
                        tr = cv2.perspectiveTransform(p_mat, c.homography)[0][0]
                        target = tr

        return target, frames

    def draw_hud(self, frames):
        if not config["show_camera_window"] or not frames:
            return

        grid = np.hstack(frames)
        cv2.rectangle(grid, (0, 0), (1280, 60), (255, 255, 255), -1)

        if self.active_idx < len(self.cams):
            c = self.cams[self.active_idx]
            hud = f"CALIB {c.name}: PT {len(c.pts)+1}/4 -> C | W SHOW | L HIDE | M TRACK | R RESET | Q QUIT"
        else:
            status = "ON" if config["tracking_enabled"] else "OFF"
            hud = f"TRACK {status} | W SHOW | L HIDE | M TRACK | R RESET | Q QUIT"

        cv2.putText(grid, hud, (10, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        cv2.imshow("720p Precision Monitor", grid)

    def process_key(self, key):
        if key == ord('c') and self.active_idx < len(self.cams):
            c = self.cams[self.active_idx]
            if c.last_det is not None:
                c.pts.append(c.last_det)
                if len(c.pts) == 4:
                    src = np.array(c.pts, dtype="float32")
                    c.homography, _ = cv2.findHomography(src, c.target_rect)
                    self.active_idx += 1

        elif key == ord('m'):
            if self.all_calibrated():
                config["tracking_enabled"] = not config["tracking_enabled"]
                if not config["tracking_enabled"]:
                    self.post(self.window.end_tracking_action)
            else:
                print("Finish calibration first before enabling tracking.")

        elif key == ord('r'):
            self.active_idx = 0
            config["tracking_enabled"] = False
            self.cur_x = self.screen_w / 2
            self.cur_y = self.screen_h / 2
            for c in self.cams:
                c.pts = []
                c.homography = None
            self.post(self.window.end_tracking_action)

        elif key == ord('w'):
            self.post(self.window.show_overlay)

        elif key == ord('l'):
            self.post(self.window.hide_overlay)

        elif key == ord('q'):
            self.running = False
            self.post(self.window.hide_overlay)

    def run(self):
        while self.running:
            target, frames = self.compute_target()

            if config["tracking_enabled"] and target is not None and self.window.overlay_enabled:
                alpha = config["mouse_smoothing"]
                tx = float(np.clip(target[0], 0, self.screen_w - 1))
                ty = float(np.clip(target[1], 0, self.screen_h - 1))

                self.cur_x = (1 - alpha) * self.cur_x + alpha * tx
                self.cur_y = (1 - alpha) * self.cur_y + alpha * ty

                gx = self.cur_x
                gy = self.cur_y
                self.post(lambda x=gx, y=gy: self.window.handle_tracking_point(x, y, True))
            else:
                self.post(lambda: self.window.handle_tracking_point(0, 0, False))

            self.draw_hud(frames)

            key = cv2.waitKey(1) & 0xFF
            if key != 255:
                self.process_key(key)

        cv2.destroyAllWindows()


# ============================================================
# HOTKEY LISTENER
# ============================================================
def start_hotkey_listener(window, app):
    def on_press(key):
        try:
            ch = key.char.lower()
            if ch == 'w':
                app.postEvent(window, _CallEvent(window.show_overlay))
            elif ch == 'l':
                app.postEvent(window, _CallEvent(window.hide_overlay))
        except AttributeError:
            pass

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app = OverlayApp(sys.argv)
    window = OverlayReceiver()

    hotkey_thread = threading.Thread(
        target=start_hotkey_listener,
        args=(window, app),
        daemon=True,
    )
    hotkey_thread.start()

    cam_controller = CameraController(window, app)
    cam_controller.start()

    sys.exit(app.exec())