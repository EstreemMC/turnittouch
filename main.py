import cv2
import numpy as np
import threading
import time
import pyautogui

# --- SETTINGS ---
W, H = 640, 480
pyautogui.FAILSAFE = False

config = {
    "low_h": 15, "high_h": 35,
    "low_s": 100, "high_s": 255,
    "low_v": 100, "high_v": 255,
    "mouse_smoothing": 0.15,
    "mouse_enabled": False
}

class SmartCamera(threading.Thread):
    def __init__(self, index):
        super().__init__(daemon=True)
        self.index = index
        self.cap = None
        self.connected = False
        self.lock = threading.Lock()
        self.frame = np.zeros((H, W, 3), dtype=np.uint8)
        self.last_det = None 
        self.pts = [] 
        self.homography = None

    def connect(self):
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
            self.cap = cap
            self.connected = True
            return True
        return False

    def run(self):
        while True:
            if not self.connected:
                if not self.connect(): time.sleep(2); continue
            ret, img = self.cap.read()
            if ret:
                img = cv2.resize(img, (W, H))
                hsv = cv2.cvtColor(cv2.GaussianBlur(img, (5,5), 0), cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array([config["low_h"], config["low_s"], config["low_v"]]),
                                   np.array([config["high_h"], config["high_s"], config["high_v"]]))
                
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                det = None
                if contours:
                    best_cnt = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(best_cnt) > 400:
                        x, y, w_obj, h_obj = cv2.boundingRect(best_cnt)
                        det = (x + w_obj//2, y + h_obj//2)
                        cv2.rectangle(img, (x, y), (x + w_obj, y + h_obj), (0, 0, 0), 1)

                # Draw the specific Quadrant Boundary
                if len(self.pts) == 4:
                    poly = np.array(self.pts, np.int32).reshape((-1, 1, 2))
                    cv2.polylines(img, [poly], True, (0, 0, 0), 2)
                
                for i, p in enumerate(self.pts):
                    cv2.circle(img, (int(p[0]), int(p[1])), 4, (0, 0, 0), -1)

                with self.lock:
                    self.frame = img
                    self.last_det = det
            else: self.connected = False

if __name__ == "__main__":
    cam = SmartCamera(1)
    cam.start()
    
    sw, sh = pyautogui.size() 
    cur_x, cur_y = sw//2, sh//2

    # Map desk points to the Bottom-Right Quadrant of the monitor
    # Format: [X coordinate, Y coordinate]
    quad_pts = np.array([
        [sw//2, sh//2], # 1. Middle-Center
        [sw, sh//2],    # 2. Right-Center
        [sw, sh],       # 3. Bottom-Right
        [sw//2, sh]     # 4. Bottom-Center
    ], dtype="float32")

    while True:
        with cam.lock:
            display = cam.frame.copy()
            det = cam.last_det

        if det and cam.homography is not None and config["mouse_enabled"]:
            # Limitation Check: Only move if tool is inside the calibrated box
            dist = cv2.pointPolygonTest(np.array(cam.pts, np.float32), (det[0], det[1]), False)
            
            if dist >= 0:
                p_matrix = np.array([[[det[0], det[1]]]], dtype=float)
                tr = cv2.perspectiveTransform(p_matrix, cam.homography)[0][0]
                
                alpha = config["mouse_smoothing"]
                cur_x = (1-alpha)*cur_x + alpha*tr[0]
                cur_y = (1-alpha)*cur_y + alpha*tr[1]
                
                # Bounds clamping (Center to Bottom-Right)
                final_x = int(max(sw//2, min(sw, cur_x)))
                final_y = int(max(sh//2, min(sh, cur_y)))
                pyautogui.moveTo(final_x, final_y)

        # HUD
        cv2.rectangle(display, (0, 0), (W, 50), (255, 255, 255), -1)
        if len(cam.pts) < 4:
            labels = ["CENTER", "RIGHT-CENTER", "BOTTOM-RIGHT", "BOTTOM-CENTER"]
            cv2.putText(display, f"MOVE TO {labels[len(cam.pts)]} -> PRESS 'C'", (10, 35), 1, 1.2, (0,0,0), 2)
        else:
            status = "ON" if config["mouse_enabled"] else "OFF"
            cv2.putText(display, f"QUADRANT BOUND: {status} | 'M' TOGGLE | 'R' RESET", (10, 35), 1, 1.1, (0,0,0), 2)

        cv2.imshow("Bottom-Right Quadrant Only", display)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('c') and len(cam.pts) < 4:
            if det:
                cam.pts.append(det)
                if len(cam.pts) == 4:
                    src = np.array(cam.pts, dtype="float32")
                    cam.homography, _ = cv2.findHomography(src, quad_pts)
        
        if key == ord('m'): config["mouse_enabled"] = not config["mouse_enabled"]
        if key == ord('r'): 
            cam.pts = []; cam.homography = None
        if key == ord('q'): break

    cv2.destroyAllWindows()