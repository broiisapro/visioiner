# lets import all the cool stuff we need lol
import cv2  # for camera stuff
import mediapipe as mp  # google's ai magic
import subprocess
import time
import math
import numpy as np
import os
import sys
from screeninfo import get_monitors
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QScreen
from PyQt6.QtCore import Qt, QPoint, QTimer, QRectF

# --- epic gamer settings ---
SHOULD_CALIBRATE = True  # set to True if you want to eye track
LOOK_AWAY_THRESHOLD_H = 0.3  # idk what this does but it works
TIME_BEFORE_PAUSE = 2  # seconds before it pauses youtube (dont make it too small or it gets annoying)
CHECK_FOR_ADS_SPEED = 0.01  # how fast it checks for those annoying ads
LEFT_EYE_DOT = 473  # some random numbers that make the eye tracking work
RIGHT_EYE_DOT = 468  # more random numbers lol
CHROME_PATH = os.path.join(os.path.dirname(__file__), 'chromedriver-mac-arm64', 'chromedriver')
PORT_NUMBER = "9222"  # my teacher said to use this port

# stuff to detect those annoying youtube ads (thank you stack overflow)
THINGS_TO_LOOK_FOR = [
    ".video-ads",  # ad container
    ".ytp-ad-player-overlay",  # more ad stuff
    ".ytp-ad-text",  # ad text
    ".ytp-ad-skip-button",  # the skip button everyone loves
    ".ytp-ad-preview-container"  # that annoying yellow bar
]

# chatgpt suggested this section.
APPLESCRIPT_PAUSE_YOUTUBE = """
osascript -e '
if application "Arc" is running then
    tell application "Arc"
        try
            set activeTabURL to URL of active tab of front window
            if activeTabURL contains "youtube.com" then
                tell application "System Events" to key code 40
                return "Attempted pause on YouTube tab."
            else
                return "Active tab in Arc is not YouTube."
            end if
        on error errMsg number errorNum
             return "Error accessing Arc tab: " & errMsg
        end try
    end tell
else
    return "Arc is not running."
end if
'
"""

# trying to figure out how big the screen is cuz retina macbooks are dumb with inconsistent resolutions
try:
    my_screen = [m for m in get_monitors() if m.is_primary][0]
    SCREEN_W = my_screen.width 
    SCREEN_H = my_screen.height
    print(f"Found my screen! Its {SCREEN_W}x{SCREEN_H}")
except IndexError:
    print("oops cant find screen size... using 1920x1080 cuz why not ¯\_(ツ)_/¯")
    SCREEN_W = 1920
    SCREEN_H = 1080

# --- Gaze Overlay Window (PyQt6) ---
class GazeOverlayWindow(QWidget):
    GAZE_CIRCLE_DIAMETER = 100
    GAZE_DOT_DIAMETER = 8
    GAZE_CIRCLE_COLOR = QColor(0, 150, 255, 100)
    GAZE_DOT_COLOR = QColor(255, 0, 0, 200)

    def __init__(self):
        super().__init__()
        self.gaze_point = QPoint(SCREEN_W // 2, SCREEN_H // 2)
        self.initUI()

    def initUI(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(0, 0, SCREEN_W, SCREEN_H)
        self.setWindowTitle('Gaze Overlay')
        self.show()

    def update_gaze(self, x, y):
        x = max(0, min(SCREEN_W - 1, x))
        y = max(0, min(SCREEN_H - 1, y))
        self.gaze_point = QPoint(x, y)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        circle_radius = self.GAZE_CIRCLE_DIAMETER // 2
        painter.setBrush(QBrush(self.GAZE_CIRCLE_COLOR))
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.drawEllipse(self.gaze_point, circle_radius, circle_radius)

        dot_radius = self.GAZE_DOT_DIAMETER // 2
        painter.setBrush(QBrush(self.GAZE_DOT_COLOR))
        painter.drawEllipse(self.gaze_point, dot_radius, dot_radius)

# making the eye tracking smoother
smooth_x = SCREEN_W / 2
smooth_y = SCREEN_H / 2
SMOOTH_FACTOR = 0.2  # makes movement less jittery
CENTER_PULL = 0.15  # how much it pulls to center (idk why this helps but it does)

# calibration stuff (boring but necessary)
eye_points = {
    "top_left": None,
    "top_right": None,
    "bottom_left": None,
    "bottom_right": None,
    "center": None
}
calibration_order = ["center", "top_left", "top_right", "bottom_left", "bottom_right"]
calibration_step = 0
is_calibrating = True

def calibrate_gaze(left_iris_lm, right_iris_lm):
    global eye_points, calibration_step, is_calibrating

    avg_iris_x_norm = (left_iris_lm.x + right_iris_lm.x) / 2.0
    avg_iris_y_norm = (left_iris_lm.y + right_iris_lm.y) / 2.0

    eye_points[calibration_order[calibration_step]] = (avg_iris_x_norm, avg_iris_y_norm)

    calibration_step += 1
    if calibration_step >= len(calibration_order):
        is_calibrating = False
        print("Calibration complete!")
        print(eye_points) # Print calibration data for debugging

def map_gaze_to_screen(left_iris_lm, right_iris_lm, frame_width, frame_height):
    # this function is like GPS for your eyes lol
    global smooth_x, smooth_y

    # get the average of both eyes (cuz cross-eyed people exist)
    avg_iris_x_norm = (left_iris_lm.x + right_iris_lm.x) / 2.0
    avg_iris_y_norm = (left_iris_lm.y + right_iris_lm.y) / 2.0

    # if we're still calibrating or something's wrong, just look at the middle
    if is_calibrating or any(value is None for value in eye_points.values()):
        return SCREEN_W // 2, SCREEN_H // 2

    # grab all our calibration points
    top_left = eye_points["top_left"]
    top_right = eye_points["top_right"]
    bottom_left = eye_points["bottom_left"]
    bottom_right = eye_points["bottom_right"]
    center = eye_points["center"]

    # some tiny number to avoid dividing by zero
    epsilon = 1e-2
    
    try:
        # some crazy math that works (copied from some forum tbh)
        x_range = abs(top_right[0] - top_left[0])
        y_range = abs(bottom_left[1] - top_left[1])
        
        # make sure we don't divide by zero
        x_range = max(x_range, epsilon)
        y_range = max(y_range, epsilon)
        
        # figure out how far we are from the center
        dx = (avg_iris_x_norm - center[0]) / x_range
        dy = (avg_iris_y_norm - center[1]) / y_range

        dx = np.clip(dx, -1.5, 1.5)
        dy = np.clip(dy, -1.5, 1.5)

        # convert to actual screen coordinates
        screen_x = int(SCREEN_W * (0.5 + dx * 0.4))
        screen_y = int(SCREEN_H * (0.5 + dy * 0.4))

        # find the middle of the screen
        center_x = SCREEN_W // 2
        center_y = SCREEN_H // 2
        
        # make it pull towards the center a bit
        screen_x = int((1 - CENTER_PULL) * screen_x + CENTER_PULL * center_x)
        screen_y = int((1 - CENTER_PULL) * screen_y + CENTER_PULL * center_y)

        # smooth it out so it's not so jittery
        smooth_x = int(SMOOTH_FACTOR * screen_x + 
                            (1 - SMOOTH_FACTOR) * smooth_x)
        smooth_y = int(SMOOTH_FACTOR * screen_y + 
                            (1 - SMOOTH_FACTOR) * smooth_y)

        # make sure we stay on screen (duh)
        smooth_x = np.clip(smooth_x, 0, SCREEN_W - 1)
        smooth_y = np.clip(smooth_y, 0, SCREEN_H - 1)

        return smooth_x, smooth_y

    except Exception as e:
        # if something breaks, just look at the center
        print(f"Error in gaze mapping: {e}")
        return SCREEN_W // 2, SCREEN_H // 2

# this function figures out where my head is pointing
def estimate_head_orientation(face_landmarks, frame_width, frame_height):
    # no face detected so we output that
    if not face_landmarks:
        return "NO_FACE"

    # grab important face points
    nose_tip = face_landmarks.landmark[1]  # the tip of my nose
    left_eye_inner = face_landmarks.landmark[133]  # left eye corner
    right_eye_inner = face_landmarks.landmark[362]  # right eye corner

    # make sure we got all the points we need
    if not all([nose_tip, left_eye_inner, right_eye_inner]):
        return "AWAY"  # if we're missing any points, assume we're looking away

    # convert the coordinates to screen pixels
    nose_x = nose_tip.x * frame_width
    left_eye_x = left_eye_inner.x * frame_width
    right_eye_x = right_eye_inner.x * frame_width

    # calculate how far apart my eyes are
    eye_dist = abs(right_eye_x - left_eye_x)
    if eye_dist < 1e-6:  # if eyes are too close
        return "AWAY"

    # find where my nose is compared to the center of my eyes
    eye_center_x = (left_eye_x + right_eye_x) / 2
    nose_displacement_x = nose_x - eye_center_x
    normalized_displacement_h = nose_displacement_x / eye_dist

    # figure out which way I'm looking based on where my nose is
    if normalized_displacement_h > LOOK_AWAY_THRESHOLD_H:
        return "RIGHT"  # nose is to the right = looking right
    elif normalized_displacement_h < -LOOK_AWAY_THRESHOLD_H:
        return "LEFT"   # nose is to the left = looking left
    else:
        return "CENTER" # nose is in the middle = looking center

# --- Selenium Helper Functions ---
def get_arc_driver(chrome_path, debugger_address):
    # try to connect to the browser
    try:
        options = Options()
        options.add_experimental_option("debuggerAddress", debugger_address)
        service = Service(executable_path=chrome_path)
        driver = webdriver.Chrome(service=service, options=options)
        print(f"Successfully connected to browser on {debugger_address}")
        return driver
    except WebDriverException as e:
        # something went wrong with the browser connection
        print(f"Error connecting to browser via WebDriver: {e}")
        print("Make sure Arc was launched with --remote-debugging-port={port} and chromedriver path is correct.".format(port=debugger_address.split(':')[1]))
        return None
    except Exception as e:
        # something else broke
        print(f"An unexpected error occurred during WebDriver initialization: {e}")
        return None

def is_youtube_ad_playing(driver):
    # if we don't have a browser connection, obviously no ad is playing
    if not driver:
        return False

    try:
        # check if we're even on youtube
        current_url = driver.current_url
        if "youtube.com/watch" not in current_url:
            return False

        # look for all the ad stuff on youtube
        wait = WebDriverWait(driver, 0.1)
        for selector in THINGS_TO_LOOK_FOR:
            try:
                elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                for element in elements:
                    if element.is_displayed():
                        print(f"Ad indicator found: {selector}")
                        return True
            except (NoSuchElementException, TimeoutException):
                # this selector wasn't found, try the next one
                continue
            except Exception as e:
                print(f"Error checking selector '{selector}': {e}")
                continue

        return False

    except WebDriverException as e:
        print(f"WebDriver error during ad check: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error during ad check: {e}")
        return False

def pause_youtube_via_selenium(driver):
    if not driver:
        return

    try:
        html_elem = driver.find_element(By.TAG_NAME, 'html')
        html_elem.send_keys('k')
        print("YouTube video paused via Selenium.")
    except WebDriverException as e:
        print(f"WebDriverException while pausing YouTube: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while pausing YouTube: {e}")

# --- Other Helper Functions ---
def run_applescript(script):
    try:
        process = subprocess.Popen(script, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        if error:
            print(f"AppleScript error: {error.decode()}")
        return output.decode().strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing AppleScript: {e}")
        return None

# --- Main ---
def main():
    global is_calibrating
    is_calibrating = SHOULD_CALIBRATE
    
    # initialize everything we need
    app = QApplication(sys.argv)  # qt app for the cool overlay
    gaze_overlay = GazeOverlayWindow()  # make a window to show where we're looking
    
    # start up the face detector
    mp_face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1,  # one face is enough
        refine_landmarks=True,  # make it super accurate
        min_detection_confidence=0.5,  # 50% sure is good enough
        min_tracking_confidence=0.5    # same here
    )

    # stuff for drawing on the debug window
    mp_drawing = mp.solutions.drawing_utils
    drawing_spec_connections = mp_drawing.DrawingSpec(
        thickness=1, 
        circle_radius=1, 
        color=(200, 200, 200)  # grey lines cuz we like that
    )
    iris_drawing_spec = {
        'color': (0, 0, 255),  # blue dots for eyes
        'thickness': 2, 
        'radius': 3
    }

    # turn on the webcam (cheese! 📸)
    cap = cv2.VideoCapture(1)
    # check if we have a webcam (if not, this is awkward)
    if not cap.isOpened():
        print("Can't open webcam")
        return

    # connect to the browser
    print(f"Trying to hack into Arc... jk just connecting to port {PORT_NUMBER}")
    driver = get_arc_driver(CHROME_PATH, f"localhost:{PORT_NUMBER}")
    if not driver:
        print("Browser connection didn't work")
        cap.release()
        return
    
    # all the variables we need to keep track of stuff
    last_pause_time = 0  # cooldown timer
    looking_away = False  # are we distracted?
    last_ad_check_time = 0  # when did we last check for those pesky ads
    is_ad_currently_playing = False  # is youtube trying to sell us stuff?
    was_paused_by_script = False  # did we pause it or did the user?
    screen_gaze_x, screen_gaze_y = SCREEN_W // 2, SCREEN_H // 2  # looking at center by default

    print("Let's go! Press 'q' to quit when you're done")

    # --- The Infinite Loop of Fun™ ---
    try:
        while cap.isOpened():  # while the camera is working
            app.processEvents()  # keep qt from having a meltdown

            # get a new frame
            success, frame = cap.read()
            if not success:
                print("Camera went bye bye")  # technical terminology
                continue

            # flip the image cuz mirrors are hard
            frame = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            frame_height, frame_width, _ = frame.shape

            # let the AI do its thing
            frame.flags.writeable = False
            results = mp_face_mesh.process(frame)
            frame.flags.writeable = True

            # back to BGR because opencv is picky
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            # did we find a face?
            face_found = results.multi_face_landmarks and len(results.multi_face_landmarks) > 0
            orientation = "NO_FACE"  # default to no face found

            if face_found:  # if we found a face
                face_landmarks = results.multi_face_landmarks[0]
                orientation = estimate_head_orientation(face_landmarks, frame_width, frame_height)

                # check if we can see the eyes
                if len(face_landmarks.landmark) > max(LEFT_EYE_DOT, RIGHT_EYE_DOT):
                    left_iris_lm = face_landmarks.landmark[LEFT_EYE_DOT]
                    right_iris_lm = face_landmarks.landmark[RIGHT_EYE_DOT]

                    # either calibrate or track the eyes
                    if is_calibrating:
                        calibrate_gaze(left_iris_lm, right_iris_lm)
                        screen_gaze_x, screen_gaze_y = SCREEN_W // 2, SCREEN_H // 2
                    else:
                        screen_gaze_x, screen_gaze_y = map_gaze_to_screen(
                            left_iris_lm, right_iris_lm, frame_width, frame_height
                        )

                    # update where we're looking
                    gaze_overlay.update_gaze(screen_gaze_x, screen_gaze_y)

                    # draw circles on the eyes (looks cool)
                    for eye in [LEFT_EYE_DOT, RIGHT_EYE_DOT]:
                        lm = face_landmarks.landmark[eye]
                        x, y = int(lm.x * frame_width), int(lm.y * frame_height)
                        cv2.circle(frame, (x, y), **iris_drawing_spec)

            # check for ads (the eternal battle)
            current_time = time.time()
            if current_time - last_ad_check_time > CHECK_FOR_ADS_SPEED:
                try:
                    is_ad_currently_playing = is_youtube_ad_playing(driver)
                    last_ad_check_time = current_time
                except WebDriverException as e:
                    print("Browser went bye bye, trying to reconnect...")
                    time.sleep(1)  # take a breather
                    driver = get_arc_driver(CHROME_PATH, f"localhost:{PORT_NUMBER}")

            # handle looking away from screen
            if orientation in ["LEFT", "RIGHT", "AWAY", "NO_FACE"]:
                if not looking_away:
                    print(f"Status: Looking {orientation} -> Triggering check")
                    looking_away = True
                    if current_time - last_pause_time > TIME_BEFORE_PAUSE:
                        if is_ad_currently_playing:
                            print("Action: Pausing YouTube (Ad)")
                            pause_youtube_via_selenium(driver)
                            last_pause_time = current_time
                            was_paused_by_script = True
                        else:
                            print("Action: Looked Away (No Ad)")
                    else:
                        print("Action: Pause on Cooldown")

            elif orientation == "CENTER":
                if looking_away:
                    print("Status: Looking CENTER")
                    if was_paused_by_script and is_ad_currently_playing:
                        print("Action: Resuming YouTube")
                        pause_youtube_via_selenium(driver)
                        was_paused_by_script = False
                    looking_away = False

            # put some cool text on the screen (because why not?)
            status_color = (0, 0, 255) if looking_away else (0, 255, 0)  # red if looking away, green if not
            cv2.putText(frame, f"Status: {orientation}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2, cv2.LINE_AA)
            
            # show if there's an ad playing
            ad_status_text = "AD: YES" if is_ad_currently_playing else "AD: NO"
            ad_status_color = (0, 0, 255) if is_ad_currently_playing else (0, 255, 0)
            cv2.putText(frame, ad_status_text, (10, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, ad_status_color, 2, cv2.LINE_AA)

            # figure out what to tell the user we're doing
            action_text = ""  # start with nothing
            action_color = (255, 255, 255)  # white by default

            # complicated if-else stuff to show what's happening
            if looking_away:  # if we're not looking at the screen
                if current_time - last_pause_time <= TIME_BEFORE_PAUSE:
                    action_text = "ACTION: PAUSED (Cooldown)"  # we're waiting for the cooldown
                    action_color = (0, 165, 255)  # orange-ish
                elif not is_ad_currently_playing:
                    action_text = "ACTION: Look Away (No Ad)"  # looking away but no ad
                    action_color = (255, 255, 0)  # yellow
                else:
                    action_text = "ACTION: PAUSED (Ad)"  # paused because of ad
                    action_color = (0, 0, 255)  # red
            elif was_paused_by_script and is_ad_currently_playing:
                action_text = "ACTION: Look Center (Ad Playing)"  # we paused it
                action_color = (0, 165, 255)  # orange-ish
            elif not looking_away:
                action_text = "ACTION: Watching"  # everything's normal
                action_color = (0, 255, 0)  # green

            # show the action text if we have any
            if action_text:
                cv2.putText(frame, action_text, (10, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, action_color, 2, cv2.LINE_AA)

            # show the debug window
            cv2.imshow('Eye Tracker Debug - Press Q to Quit', frame)

            # check if user pressed 'q' to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    # cleanup
    finally:
        cap.release()  # let the camera go
        cv2.destroyAllWindows()  # close all windows
        if 'mp_face_mesh' in locals() and mp_face_mesh:
            mp_face_mesh.close()  # tell google we're done
        if driver:
            try:
                pass  # browser cleanup
            except WebDriverException as e:
                print(f"Error during cleanup (but it's probably fine): {e}")
        app.quit()  # bye bye Qt
        print("Eye tracker stopped. Thanks for wasting your time with me! :)")

# the moment of pain and suffering ending
if __name__ == "__main__":
    main()  # i wouln't wish the pain of making this on anyone