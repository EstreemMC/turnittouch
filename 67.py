import sys
import threading
import time
import socket
import cv2
import numpy as np
import pyautogui
from pynput import keyboard
from enum import Enum, auto

from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal, QEvent, QCoreApplication
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QMouseEvent, 
                           QPainter, QPainterPath, QPen, QPolygon)
from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog, QFrame, 
                               QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, 
                               QInputDialog, QLabel, QLineEdit, QPushButton, 
                               QSlider, QToolButton, QVBoxLayout, QWidget)

# --- 1. CORE CONFIGURATION ---
W_CAM, H_CAM = 1280, 720 
UDP_IP, UDP_PORT = "0.0.0.0", 5005
pyautogui.FAILSAFE = False

cam_config = {"mouse_enabled": False, "mouse_smoothing": 0.1}

# --- 2. ESP32 UDP RECEIVER ---
def start_udp_receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    print(f"UDP Receiver active on port {UDP_PORT}...")
    last_state = 0
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            state = int(data.decode().strip())
            if cam_config["mouse_enabled"]:
                if state == 1 and last_state == 0:
                    pyautogui.mouseDown()
                elif state == 0 and last_state == 1:
                    pyautogui.mouseUp()
            last_state = state
        except: pass

# --- 3. DETECTION ENGINE ---
class SmartCamera(threading.Thread):
    def __init__(self, index, name, target_rect, low_hsv, high_hsv):
        super().__init__(daemon=True)
        self.index, self.name, self.target_rect = index, name, target_rect
        self.low_hsv = np.array(low_hsv)
        self.high_hsv = np.array(high_hsv)
        self.cap, self.connected, self.lock = None, False, threading.Lock()
        self.frame = np.zeros((H_CAM, W_CAM, 3), dtype=np.uint8)
        self.last_det, self.pts, self.homography = None, [], None

    def connect(self):
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, W_CAM)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H_CAM)
            self.cap, self.connected = cap, True
            return True
        return False

    def run(self):
        while True:
            if not self.connected:
                if not self.connect(): time.sleep(2); continue
            ret, img = self.cap.read()
            if ret:
                hsv = cv2.cvtColor(cv2.GaussianBlur(img, (7,7), 0), cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, self.low_hsv, self.high_hsv)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                det = None
                if contours:
                    best_cnt = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(best_cnt) > 400:
                        x, y, w, h = cv2.boundingRect(best_cnt)
                        det = (x + w//2, y + h//2)
                        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 0), 2)
                        cv2.drawMarker(img, det, (0, 0, 0), cv2.MARKER_CROSS, 20, 2)
                with self.lock: self.frame, self.last_det = img, det
            else: self.connected = False

# --- 4. UI COMPONENTS ---
class Tool(Enum): DRAW, HIGHLIGHTER, ERASER = range(3)

class ColorButton(QToolButton):
    def __init__(self, color_hex):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(32, 32)
        self.setStyleSheet(f"background-color: {color_hex}; border-radius: 16px; border: 2px solid rgba(0,0,0,0.1);")
        self.color = QColor(color_hex)

class IconButton(QToolButton):
    def __init__(self, tool_type=None):
        super().__init__()
        self.tool_type = tool_type
        self.setCheckable(True)
        self.setFixedSize(50, 50)
        self.setStyleSheet("QToolButton { border: none; border-radius: 12px; background: transparent; } QToolButton:checked { background: rgba(0,0,0,0.1); }")

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#4c1d95"), 2.5, Qt.SolidLine, Qt.RoundCap))
        cx, cy = self.width()//2, self.height()//2
        if self.tool_type == Tool.DRAW: 
            p.drawLine(cx-10, cy+10, cx+10, cy-10)
        elif self.tool_type == Tool.ERASER: 
            p.drawRect(cx-12, cy-6, 24, 12)
        elif self.tool_type == Tool.HIGHLIGHTER:
            p.save()
            p.translate(cx, cy)
            p.rotate(-30)
            p.setBrush(QColor("#4c1d95"))
            p.setPen(Qt.NoPen)
            p.drawRect(-15, -6, 25, 12)
            p.setBrush(QColor("#facc15"))
            p.drawRect(10, -6, 5, 12)
            p.restore()

class FloatingToolbar(QFrame):
    tool_changed, color_changed = Signal(object), Signal(QColor)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setStyleSheet("QFrame#toolbar { background: #FDFCF0; border-radius: 25px; border: 1px solid #E5E4D7; }")
        self.setFixedWidth(80)
        layout = QVBoxLayout(self)
        self.tool_btns = {}
        for t in [Tool.DRAW, Tool.HIGHLIGHTER, Tool.ERASER]:
            btn = IconButton(t)
            btn.clicked.connect(lambda chk, tool=t: self.select_tool(tool))
            layout.addWidget(btn, alignment=Qt.AlignCenter); self.tool_btns[t] = btn
        self.tool_btns[Tool.DRAW].setChecked(True)
        layout.addSpacing(10)
        for c in ["#2563eb", "#ef4444", "#22c55e", "#8b5cf6", "#000000"]:
            btn = ColorButton(c)
            btn.clicked.connect(lambda chk, col=btn.color: self.color_changed.emit(col))
            layout.addWidget(btn, alignment=Qt.AlignCenter)

    def select_tool(self, tool):
        for t, b in self.tool_btns.items(): b.setChecked(t == tool)
        self.tool_changed.emit(tool)

# --- 5. OVERLAY WINDOW ---
class CustomCallEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())
    def __init__(self, action): super().__init__(self.EVENT_TYPE); self.action = action

class OverlayWindow(QWidget):
    def __init__(self, cams):
        super().__init__()
        self.cams, self.items, self.current_points = cams, [], []
        self.overlay_enabled, self.current_tool, self.current_color = False, Tool.DRAW, QColor("#8b5cf6")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.toolbar = FloatingToolbar(self)
        self.toolbar.tool_changed.connect(lambda t: setattr(self, 'current_tool', t))
        self.toolbar.color_changed.connect(lambda c: setattr(self, 'current_color', c))
        self.toolbar.hide()
        self.cur_x, self.cur_y = pyautogui.size()[0]//2, pyautogui.size()[1]//2
        threading.Thread(target=self.tracking_loop, daemon=True).start()

    def tracking_loop(self):
        while True:
            target = None
            for c in self.cams:
                with c.lock:
                    if c.homography is not None and c.last_det:
                        if cv2.pointPolygonTest(np.array(c.pts, np.float32), (c.last_det[0], c.last_det[1]), False) >= 0:
                            p_mat = np.array([[[c.last_det[0], c.last_det[1]]]], dtype=float)
                            target = cv2.perspectiveTransform(p_mat, c.homography)[0][0]
            if target is not None and cam_config["mouse_enabled"]:
                a = cam_config["mouse_smoothing"]
                self.cur_x = (1-a)*self.cur_x + a*target[0]; self.cur_y = (1-a)*self.cur_y + a*target[1]
                pyautogui.moveTo(int(self.cur_x), int(self.cur_y))
            time.sleep(0.01)

    def event(self, event):
        if event.type() == CustomCallEvent.EVENT_TYPE:
            if event.action == "show": self.show_board()
            elif event.action == "hide": self.hide_board()
            return True
        return super().event(event)

    def show_board(self):
        self.setWindowFlag(Qt.WindowTransparentForInput, False)
        geo = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(geo); self.toolbar.move(geo.width() - 110, geo.height() // 6)
        self.toolbar.show(); self.show(); self.raise_(); self.overlay_enabled = True

    def hide_board(self):
        self.setWindowFlag(Qt.WindowTransparentForInput, True); self.toolbar.hide(); self.hide(); self.overlay_enabled = False

    def mousePressEvent(self, e): 
        if self.overlay_enabled: self.current_points = [e.position().toPoint()]
        
    def mouseMoveEvent(self, e): 
        if not self.overlay_enabled: return
        pos = e.position().toPoint()
        
        if self.current_tool == Tool.ERASER:
            # --- SMART SMART ERASE: Object Collision ---
            remaining_items = []
            erased_any = False
            for item in self.items:
                hit = False
                for pt in item['pts']:
                    if (pt - pos).manhattanLength() < 20: 
                        hit = True; break
                if hit: erased_any = True
                else: remaining_items.append(item)
            if erased_any:
                self.items = remaining_items; self.update()
        elif self.current_points: 
            self.current_points.append(pos); self.update()

    def mouseReleaseEvent(self, e):
        if self.overlay_enabled and self.current_points:
            stroke_pts = self.current_points[:]
            if self.current_tool == Tool.HIGHLIGHTER:
                col = QColor("#facc15"); col.setAlpha(100)
                width = 25
            else:
                col = self.current_color
                width = 6
                
            self.items.append({'pts': stroke_pts, 'tool': self.current_tool, 'color': col, 'width': width})
            self.current_points = []; self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 1)) 
        for item in self.items:
            if item['tool'] == Tool.HIGHLIGHTER:
                painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
                pen = QPen(item['color'], item['width'], Qt.SolidLine, Qt.SquareCap)
            else:
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
                pen = QPen(item['color'], item['width'], Qt.SolidLine, Qt.RoundCap)
            
            painter.setPen(pen)
            for i in range(1, len(item['pts'])): painter.drawLine(item['pts'][i-1], item['pts'][i])
            
        if self.current_points:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            if self.current_tool == Tool.HIGHLIGHTER:
                c = QColor("#facc15"); c.setAlpha(100)
                painter.setPen(QPen(c, 25))
            else:
                painter.setPen(QPen(self.current_color, 6))
            for i in range(1, len(self.current_points)): painter.drawLine(self.current_points[i-1], self.current_points[i])

# --- 6. EXECUTION ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    sw, sh = pyautogui.size()
    mid_x = sw // 2
    c1_dest = np.array([[mid_x, 0], [sw, 0], [sw, sh], [mid_x, sh]], dtype="float32")
    c2_dest = np.array([[0, 0], [mid_x, 0], [mid_x, sh], [0, sh]], dtype="float32")
    
    # PER-CAM THRESHOLDS
    c1_low, c1_high = [10, 70, 100], [40, 255, 255]
    c2_low, c2_high = [10, 70, 100], [40, 255, 255]
    
    cams = [
        SmartCamera(1, "CAM 1 (RIGHT)", c1_dest, c1_low, c1_high),
        SmartCamera(2, "CAM 2 (LEFT)", c2_dest, c2_low, c2_high)
    ]
    for c in cams: c.start()
    
    window = OverlayWindow(cams)

    def on_press(key):
        try:
            k = key.char.lower()
            if k == "k": QCoreApplication.postEvent(window, CustomCallEvent("show"))
            elif k == "j": QCoreApplication.postEvent(window, CustomCallEvent("hide"))
            elif k == "m": cam_config["mouse_enabled"] = not cam_config["mouse_enabled"]
        except: pass
    
    threading.Thread(target=lambda: keyboard.Listener(on_press=on_press).start(), daemon=True).start()
    threading.Thread(target=start_udp_receiver, daemon=True).start() 

    def run_cv_monitor():
        active_idx = 0
        while True:
            frames = []
            for i, c in enumerate(cams):
                with c.lock:
                    f = cv2.resize(c.frame.copy(), (640, 360))
                    if len(c.pts) == 4:
                        poly = np.array(c.pts, np.int32).reshape((-1, 1, 2)) // 2
                        cv2.polylines(f, [poly], True, (0, 0, 0), 2)
                    if i == active_idx: cv2.rectangle(f, (0,0), (640,360), (0,0,0), 6)
                    frames.append(f)
            grid = np.hstack(frames)
            cv2.rectangle(grid, (0,0), (1280, 50), (255,255,255), -1)
            msg = f"CALIB {cams[active_idx].name}: PT {len(cams[active_idx].pts)+1}/4 -> 'C'" if active_idx < 2 else "READY"
            cv2.putText(grid, msg, (15, 35), 1, 1.3, (0,0,0), 2); cv2.imshow("Monitor HUD", grid)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('c') and active_idx < 2:
                c = cams[active_idx]
                if c.last_det:
                    c.pts.append(c.last_det)
                    if len(c.pts) == 4:
                        c.homography, _ = cv2.findHomography(np.array(c.pts, dtype="float32"), c.target_rect)
                        active_idx += 1
            if key == ord('r'): active_idx = 0; [setattr(c, 'pts', []) for c in cams]
            if key == ord('q'): break
    
    threading.Thread(target=run_cv_monitor, daemon=True).start()
    sys.exit(app.exec())