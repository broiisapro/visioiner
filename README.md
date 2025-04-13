# Visioiner - YouTube Ad Auto-Pauser

## What is this?
Visioiner is a Python-based eye tracking system that automatically pauses YouTube ads when you look away from the screen. It's like having a friend who pauses ads for you when you're not watching!

## Features
- Real-time eye tracking using your webcam
- Automatic YouTube ad detection
- Pauses ads when you look away from the screen
- Cool visual overlay showing where you're looking
- Debug window with status information
- Works with Arc browser

## Prerequisites
- Python 3.9.21
- macOS (currently only supports Arc browser)
- Webcam
- Arc browser with remote debugging enabled

## Dependencies
```bash
pip install opencv-python mediapipe selenium screeninfo PyQt6 numpy
```

2. Download ChromeDriver for Arc:
   - Place it in the `chromedriver-mac-arm64` folder
   - Make sure it matches your Arc browser version

3. Launch Arc with remote debugging:
```bash
/Applications/Arc.app/Contents/MacOS/Arc --remote-debugging-port=9222
```

4. Give necessary permissions:
   - Allow camera access
   - Enable Accessibility permissions for Arc (System Settings > Privacy & Security > Accessibility)

## Usage
1. Run the program:
```bash
python eye_tracker.py
```

2. Start watching YouTube:
   - Green status = Looking at screen
   - Red status = Looking away
   - Orange status = Cooldown period
   - The program will automatically pause ads when you look away!

## Controls
- Press 'q' in the debug window to quit
- Look away from screen to trigger pause
- Look back at screen to resume playback

## Configuration
You can adjust these settings in `eye_tracker.py`:
- `SHOULD_CALIBRATE`: Enable/disable eye tracking
- `TIME_BEFORE_PAUSE`: Delay before pausing (seconds)
- `CHECK_FOR_ADS_SPEED`: How often to check for ads
- `LOOK_AWAY_THRESHOLD_H`: Sensitivity for head movement

## Troubleshooting
1. "Can't open webcam":
   - Make sure your webcam isn't being used by another application
   - Check camera permissions

2. "Browser connection didn't work":
   - Verify Arc is running with remote debugging
   - Check if ChromeDriver version matches Arc

3. "Calibration issues":
   - Make sure you're in a well-lit environment
   - Keep your head relatively still during calibration
   - Try adjusting your distance from the camera

## Known Limitations
- Only works with Arc browser on macOS
- Requires good lighting conditions
- May not detect all types of YouTube ads

## Contributing
Feel free to submit issues and pull requests. This is a fun project and all help is appreciated!

Readme made with the assistance of AI