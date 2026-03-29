import cv2
import numpy as np
import threading
import time
import pyautogui

# --- 720p RESOLUTION ---
W, H = 1280, 720 
pyautogui.FAILSAFE = False

config = {
    # Fine-tuned for the Golden Metallic tool in your photo
    "low_h": 10,  "high_h": 32,
    "low_s": 90,  "high_s": 255,
    "low_v": 130, "high_v": 255,
    "mouse_smoothing": 0.1, # Lower for higher precision
    "mouse_enabled": False
}

class SmartCamera(threading.Thread):
    def __init__(self, index, name, target_rect):
        super().__init__(daemon=True)
        self.index = index
        self.name = name
        self.target_rect = target_rect 
        self.cap = None
        self.connected = False
        self.lock = threading.Lock()
        self.frame = np.zeros((H, W, 3), dtype=np.uint8)
        self.last_det = None 
        self.pts = [] 
        self.homography = None

    def connect(self):
        # Using DSHOW for high-res stability on Windows
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
            cap.set(cv2.CAP_PROP_FPS, 30)
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
                # 720p detection logic
                hsv = cv2.cvtColor(cv2.GaussianBlur(img, (7,7), 0), cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, np.array([config["low_h"], config["low_s"], config["low_v"]]),
                                   np.array([config["high_h"], config["high_s"], config["high_v"]]))
                
                # Morphological cleaning for metallic reflections
                mask = cv2.erode(mask, None, iterations=1)
                mask = cv2.dilate(mask, None, iterations=2)
                
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                det = None
                if contours:
                    best_cnt = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(best_cnt) > 600: # Increased area threshold for 720p
                        x, y, w_obj, h_obj = cv2.boundingRect(best_cnt)
                        det = (x + w_obj//2, y + h_obj//2)
                        cv2.rectangle(img, (x, y), (x + w_obj, y + h_obj), (0, 0, 0), 2)

                # Draw Polygon
                if len(self.pts) == 4:
                    poly = np.array(self.pts, np.int32).reshape((-1, 1, 2))
                    cv2.polylines(img, [poly], True, (0, 0, 0), 3)
                for p in self.pts:
                    cv2.circle(img, (int(p[0]), int(p[1])), 6, (0, 0, 0), -1)
                
                with self.lock:
                    self.frame = img
                    self.last_det = det
            else: self.connected = False

if __name__ == "__main__":
    sw, sh = pyautogui.size()
    mid_x = sw // 2
    
    # CAM 1 -> RIGHT SCREEN | CAM 2 -> LEFT SCREEN
    c1_dest = np.array([[mid_x, 0], [sw, 0], [sw, sh], [mid_x, sh]], dtype="float32")
    c2_dest = np.array([[0, 0], [mid_x, 0], [mid_x, sh], [0, sh]], dtype="float32")

    cams = [
        SmartCamera(1, "CAM 1 (RIGHT)", c1_dest),
        SmartCamera(2, "CAM 2 (LEFT)", c2_dest)
    ]
    
    for c in cams: c.start(); time.sleep(2)
    
    cur_x, cur_y = sw//2, sh//2
    active_idx = 0

    while True:
        frames = []
        target = None

        for c in cams:
            with c.lock:
                # Resize only for the monitor display (to fit your screen)
                frames.append(cv2.resize(c.frame.copy(), (640, 360)))
                
                if c.homography is not None and c.last_det:
                    dist = cv2.pointPolygonTest(np.array(c.pts, np.float32), (c.last_det[0], c.last_det[1]), False)
                    if dist >= 0:
                        p_mat = np.array([[[c.last_det[0], c.last_det[1]]]], dtype=float)
                        tr = cv2.perspectiveTransform(p_mat, c.homography)[0][0]
                        target = tr

        if target is not None and config["mouse_enabled"]:
            alpha = config["mouse_smoothing"]
            cur_x = (1-alpha)*cur_x + alpha*target[0]
            cur_y = (1-alpha)*cur_y + alpha*target[1]
            pyautogui.moveTo(int(cur_x), int(cur_y))

        # HUD display at 720p total width (1280)
        grid = np.hstack(frames)
        cv2.rectangle(grid, (0, 0), (1280, 50), (255, 255, 255), -1)
        
        if active_idx < len(cams):
            c = cams[active_idx]
            cv2.putText(grid, f"720p CALIB {c.name}: PT {len(c.pts)+1}/4 -> 'C'", (10, 35), 1, 1.5, (0,0,0), 2)
        else:
            status = "ON" if config["mouse_enabled"] else "OFF"
            cv2.putText(grid, f"720p DUAL: {status} | 'M' TOGGLE | 'R' RESET", (10, 35), 1, 1.3, (0,0,0), 2)

        cv2.imshow("720p Precision Monitor", grid)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('c') and active_idx < len(cams):
            c = cams[active_idx]
            if c.last_det:
                c.pts.append(c.last_det)
                if len(c.pts) == 4:
                    src = np.array(c.pts, dtype="float32")
                    c.homography, _ = cv2.findHomography(src, c.target_rect)
                    active_idx += 1
        
        if key == ord('m'): config["mouse_enabled"] = not config["mouse_enabled"]
        if key == ord('r'): 
            active_idx = 0
            for c in cams: c.pts = []; c.homography = None
        if key == ord('q'): break

    cv2.destroyAllWindows()