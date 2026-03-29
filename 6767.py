import sys
import threading
import time
import socket
import cv2
import numpy as np
import pyautogui
import base64
from openai import OpenAI
from pynput import keyboard
from enum import Enum, auto

from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal, QEvent, QCoreApplication, QObject
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QMouseEvent, 
                           QPainter, QPainterPath, QPen, QPolygon)
from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog, QFrame, 
                               QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, 
                               QInputDialog, QLabel, QLineEdit, QPushButton, 
                               QSlider, QToolButton, QVBoxLayout, QWidget, QTextEdit)

# --- 1. CORE CONFIGURATION ---
W_CAM, H_CAM = 1280, 720 
UDP_IP, UDP_PORT = "0.0.0.0", 5005
pyautogui.FAILSAFE = False

# --- OPENAI SETUP ---
client = OpenAI(api_key='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')

# --- CUSTOMIZABLE OFFSET ---
# Change "x_offset" to shift the cursor: e.g., 50 for right, -50 for left
cam_config = {
    "mouse_enabled": False, 
    "mouse_smoothing": 0.1, 
    "click_toggle": False,
    "x_offset": 0  
}

# --- 2. ESP32 UDP RECEIVER ---
def start_udp_receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((UDP_IP, UDP_PORT))
        print(f"\n[NETWORK] UDP Listener active on port {UDP_PORT}")
    except Exception as e:
        print(f"[ERROR] UDP Bind failed: {e}")
        return

    last_state = 0
    connected_announced = False

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if not connected_announced:
                print(f"[SUCCESS] ESP32 Connected! (IP: {addr[0]})")
                connected_announced = True

            state = int(data.decode().strip())
            
            if state == 1 and last_state == 0:
                cam_config["click_toggle"] = not cam_config["click_toggle"]
                status = "ON" if cam_config["click_toggle"] else "OFF"
                print(f" -> [ESP32] Click Toggle: {status}")
                
                if cam_config["mouse_enabled"]:
                    if cam_config["click_toggle"]:
                        pyautogui.mouseDown()
                    else:
                        pyautogui.mouseUp()
            
            last_state = state
        except Exception as e:
            pass

# --- 3. UI COMPONENTS: STICKY NOTE ---
class StickyNote(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(350, 500)
        self.container = QFrame(self)
        self.container.setObjectName("note")
        self.container.setFixedSize(330, 480)
        self.container.setStyleSheet("QFrame#note { background-color: rgba(255, 253, 208, 230); border-left: 5px solid #facc15; border-radius: 10px; }")
        layout = QVBoxLayout(self.container)
        self.title = QLabel("Similar Problem")
        self.title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.title.setStyleSheet("color: #854d0e;")
        layout.addWidget(self.title)
        self.content = QTextEdit()
        self.content.setReadOnly(True)
        self.content.setFrameStyle(QFrame.NoFrame)
        self.content.setFont(QFont("Consolas", 11))
        self.content.setStyleSheet("background: transparent; color: #1a1a1a;")
        layout.addWidget(self.content)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20); shadow.setXOffset(5); shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.container.setGraphicsEffect(shadow)
    def update_text(self, text):
        self.content.setPlainText(text); self.show()

# --- 4. TOOLBAR & OVERLAY CLASSES ---
class Tool(Enum): DRAW, HIGHLIGHTER, ERASER = range(3)

class IconButton(QToolButton):
    def __init__(self, tool_type=None):
        super().__init__()
        self.tool_type = tool_type
        self.setCheckable(True); self.setFixedSize(50, 50)
        self.setStyleSheet("QToolButton { border: none; border-radius: 12px; background: transparent; } QToolButton:checked { background: rgba(0,0,0,0.1); }")
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#4c1d95"), 2.5, Qt.SolidLine, Qt.RoundCap))
        cx, cy = self.width()//2, self.height()//2
        if self.tool_type == Tool.DRAW: p.drawLine(cx-10, cy+10, cx+10, cy-10)
        elif self.tool_type == Tool.ERASER: p.drawRect(cx-12, cy-6, 24, 12)
        elif self.tool_type == Tool.HIGHLIGHTER:
            p.save(); p.translate(cx, cy); p.rotate(-30)
            p.setBrush(QColor("#4c1d95")); p.setPen(Qt.NoPen); p.drawRect(-15, -6, 25, 12)
            p.setBrush(QColor("#facc15")); p.drawRect(10, -6, 5, 12); p.restore()

class FloatingToolbar(QFrame):
    tool_changed, color_changed = Signal(object), Signal(QColor)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbar"); self.setFixedWidth(80)
        self.setStyleSheet("QFrame#toolbar { background: #FDFCF0; border-radius: 25px; border: 1px solid #E5E4D7; }")
        layout = QVBoxLayout(self)
        self.tool_btns = {}
        for t in [Tool.DRAW, Tool.HIGHLIGHTER, Tool.ERASER]:
            btn = IconButton(t); btn.clicked.connect(lambda chk, tool=t: self.select_tool(tool))
            layout.addWidget(btn, alignment=Qt.AlignCenter); self.tool_btns[t] = btn
        self.tool_btns[Tool.DRAW].setChecked(True)
        layout.addSpacing(10)
        for c in ["#2563eb", "#ef4444", "#22c55e", "#8b5cf6", "#000000"]:
            btn = QToolButton(); btn.setFixedSize(32, 32); btn.setCheckable(True)
            btn.setStyleSheet(f"background-color: {c}; border-radius: 16px; border: 2px solid rgba(0,0,0,0.1);")
            btn.clicked.connect(lambda chk, col=QColor(c): self.color_changed.emit(col))
            layout.addWidget(btn, alignment=Qt.AlignCenter)
    def select_tool(self, tool):
        for t, b in self.tool_btns.items(): b.setChecked(t == tool)
        self.tool_changed.emit(tool)

class OverlayWindow(QWidget):
    solution_ready = Signal(str)
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
        self.note = StickyNote()
        self.solution_ready.connect(self.note.update_text)
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
                # Apply the X Offset to the target coordinate
                final_x = target[0] + cam_config["x_offset"]
                
                self.cur_x = (1-a)*self.cur_x + a*final_x
                self.cur_y = (1-a)*self.cur_y + a*target[1]
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
        self.note.move(50, geo.height() // 6); self.toolbar.show(); self.show(); self.raise_(); self.overlay_enabled = True

    def hide_board(self):
        self.setWindowFlag(Qt.WindowTransparentForInput, True); self.toolbar.hide(); self.note.hide(); self.hide(); self.overlay_enabled = False

    def solve_problem_from_lasso(self):
        if not self.items: return
        pts = self.items[-1]['pts']
        xs, ys = [p.x() for p in pts], [p.y() for p in pts]
        x, y, w, h = min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)
        self.toolbar.hide(); self.note.hide(); QCoreApplication.processEvents()
        pyautogui.screenshot(region=(x-10, y-10, w+20, h+20)).save("problem.png")
        self.toolbar.show(); self.note.show()
        def openai_task():
            try:
                self.solution_ready.emit("Generating Similar Problem...")
                with open("problem.png", "rb") as f: b64 = base64.b64encode(f.read()).decode('utf-8')
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": [{"type": "text", "text": "Generate a similar problem. No hints or formulas."}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}] }])
                self.solution_ready.emit(resp.choices[0].message.content)
            except Exception as e: self.solution_ready.emit(f"Error: {e}")
        threading.Thread(target=openai_task, daemon=True).start()

    def mousePressEvent(self, e): 
        if self.overlay_enabled: self.current_points = [e.position().toPoint()]
    def mouseMoveEvent(self, e): 
        if not self.overlay_enabled: return
        pos = e.position().toPoint()
        if self.current_tool == Tool.ERASER:
            rem = [item for item in self.items if all((pt - pos).manhattanLength() >= 20 for pt in item['pts'])]
            if len(rem) != len(self.items): self.items = rem; self.update()
        elif self.current_points: self.current_points.append(pos); self.update()
    def mouseReleaseEvent(self, e):
        if self.overlay_enabled and self.current_points:
            col, width = (QColor("#facc15"), 25) if self.current_tool == Tool.HIGHLIGHTER else (self.current_color, 6)
            if self.current_tool == Tool.HIGHLIGHTER: col.setAlpha(100)
            self.items.append({'pts': self.current_points[:], 'tool': self.current_tool, 'color': col, 'width': width})
            self.current_points = []; self.update()

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 1)) 
        for item in self.items:
            painter.setCompositionMode(QPainter.CompositionMode_DestinationOver if item['tool'] == Tool.HIGHLIGHTER else QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(item['color'], item['width'], Qt.SolidLine, Qt.SquareCap if item['tool'] == Tool.HIGHLIGHTER else Qt.RoundCap))
            for i in range(1, len(item['pts'])): painter.drawLine(item['pts'][i-1], item['pts'][i])
        if self.current_points:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#facc15") if self.current_tool == Tool.HIGHLIGHTER else self.current_color, 25 if self.current_tool == Tool.HIGHLIGHTER else 6))
            for i in range(1, len(self.current_points)): painter.drawLine(self.current_points[i-1], self.current_points[i])

# --- 5. ENGINE CLASSES ---
class SmartCamera(threading.Thread):
    def __init__(self, index, name, target_rect, hsv_low, hsv_high):
        super().__init__(daemon=True); self.index, self.name, self.target_rect = index, name, target_rect
        self.hsv_low, self.hsv_high = np.array(hsv_low), np.array(hsv_high)
        self.cap, self.connected, self.lock = None, False, threading.Lock()
        self.frame = np.zeros((H_CAM, W_CAM, 3), dtype=np.uint8); self.last_det, self.pts, self.homography = None, [], None
    def run(self):
        while True:
            if not self.connected:
                cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
                if cap.isOpened(): cap.set(3, 1280); cap.set(4, 720); self.cap, self.connected = cap, True
                else: time.sleep(2); continue
            ret, img = self.cap.read()
            if ret:
                hsv = cv2.cvtColor(cv2.GaussianBlur(img, (7,7), 0), cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, self.hsv_low, self.hsv_high)
                cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                det = None
                if cnts:
                    c = max(cnts, key=cv2.contourArea)
                    if cv2.contourArea(c) > 400:
                        x, y, w, h = cv2.boundingRect(c); det = (x+w//2, y+h//2)
                        cv2.rectangle(img, (x,y), (x+w, y+h), (0,0,0), 2)
                with self.lock: self.frame, self.last_det = img, det
            else: self.connected = False

class CustomCallEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())
    def __init__(self, action): super().__init__(self.EVENT_TYPE); self.action = action

def run_cv():
    active_idx = 0 
    while True:
        frames = []
        for i, c in enumerate(cams):
            with c.lock:
                f = cv2.resize(c.frame.copy(), (640, 360))
                if i == active_idx: cv2.rectangle(f, (0,0), (640,360), (0,255,0), 4)
                pts_scaled = [(int(p[0]/2), int(p[1]/2)) for p in c.pts]
                for pt in pts_scaled: cv2.circle(f, pt, 5, (0,0,255), -1)
                if len(pts_scaled) == 4:
                    poly = np.array(pts_scaled, np.int32).reshape((-1, 1, 2))
                    cv2.polylines(f, [poly], True, (255,0,0), 2)
                frames.append(f)
        grid = np.hstack(frames); cv2.rectangle(grid, (0,0), (1280, 50), (255,255,255), -1)
        if active_idx < len(cams):
            msg = f"CALIBRATING {cams[active_idx].name}: Point {len(cams[active_idx].pts)+1}/4. Press 'C' to capture."
        else:
            msg = "CALIBRATION COMPLETE. Window stays open. Press 'Q' to acknowledge."
        cv2.putText(grid, msg, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,0), 2); cv2.imshow("Monitor HUD", grid)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('c') and active_idx < len(cams):
            c = cams[active_idx]
            if c.last_det:
                c.pts.append(c.last_det)
                if len(c.pts) == 4: c.homography, _ = cv2.findHomography(np.array(c.pts, dtype="float32"), c.target_rect); active_idx += 1
        if key == ord('r'):
            active_idx = 0; [setattr(c, 'pts', []) for c in cams]
        if key == ord('q'): print("Main Tracking Acknowledged. Video remains active.")

if __name__ == "__main__":
    app = QApplication(sys.argv); sw, sh = pyautogui.size(); mid = sw // 2
    global cams
    cams = [SmartCamera(1, "RIGHT", np.array([[mid, 0], [sw, 0], [sw, sh], [mid, sh]], dtype="float32"), [10,70,100], [40,255,255]),
            SmartCamera(2, "LEFT", np.array([[0, 0], [mid, 0], [mid, sh], [0, sh]], dtype="float32"), [10,70,100], [40,255,255])]
    for c in cams: c.start()
    window = OverlayWindow(cams)
    def on_press(key):
        try:
            k = key.char.lower()
            if k == "k": QCoreApplication.postEvent(window, CustomCallEvent("show"))
            elif k == "j": QCoreApplication.postEvent(window, CustomCallEvent("hide"))
            elif k == "m": cam_config["mouse_enabled"] = not cam_config["mouse_enabled"]
            elif k == "s": window.solve_problem_from_lasso()
        except: pass
    threading.Thread(target=lambda: keyboard.Listener(on_press=on_press).start(), daemon=True).start()
    threading.Thread(target=start_udp_receiver, daemon=True).start()
    threading.Thread(target=run_cv, daemon=True).start()
    sys.exit(app.exec())