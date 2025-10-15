#!/usr/bin/env python
import subprocess
import time
from datetime import datetime

# --- Global state ---
prevstat = "OFF"
pause = "OFF"
lastsong = ""
currentSongTitle = ""
proc = None
screen_on = False
last_active_time = time.time()
manual_override = None  # None, "OFF", or "ON"

# --- Configuration ---
INACTIVITY_TIMEOUT = 300  # seconds (5 minutes)
CONTROL_FILE = "/tmp/screen_control"


# --- Core functions ---
def moodeCurrentSong():
    """Read and parse current song info from moOde currentsong.txt"""
    info = ""
    try:
        with open('/var/local/www/currentsong.txt', 'r') as f:
            info = f.read()

        song = {}
        for line in info.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                song[key] = value

        # Handle Spotify state
        if song.get('file') == "Spotify Active":
            if song.get('outrate') == "Not playing":
                song['state'] = 'stop'
                song['title'] = 'Spotify Inactive'
            else:
                song['state'] = 'play'
                song['title'] = f"Spotify - {song.get('outrate', 'Unknown')}"

        # Default values
        song.setdefault('state', 'stop')
        song.setdefault('title', song.get('file', 'Unknown'))

    except Exception as e:
        print(f"Error reading currentsong.txt: {e}")
        song = {'state': 'stop', 'title': 'Error'}

    return song


def blank_screen():
    """Turn off the screen backlight"""
    try:
        subprocess.run(["bash", "-c", "echo 1 | sudo tee /sys/class/backlight/*/bl_power"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Screen blanked")
        return True
    except Exception as e:
        print(f"Error blanking screen: {e}")
        return False


def unblank_screen():
    """Turn on the screen backlight"""
    try:
        subprocess.run(["bash", "-c", "echo 0 | sudo tee /sys/class/backlight/*/bl_power"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Screen unblanked")
        return True
    except Exception as e:
        print(f"Error unblanking screen: {e}")
        return False


def check_manual_override():
    """Check for manual screen ON/OFF command via /tmp/screen_control"""
    global manual_override
    try:
        with open(CONTROL_FILE, "r") as f:
            cmd = f.read().strip().upper()
        if cmd in ["ON", "OFF"]:
            manual_override = cmd
            print(f"Manual override detected: Screen {cmd}")
        else:
            manual_override = None
    except FileNotFoundError:
        manual_override = None


def graph_monitor():
    """Main monitor loop that manages PeppyMeter and screen state"""
    global prevstat, lastsong, proc, screen_on, last_active_time, manual_override

    progname = "DISPLAY=:0 python /home/yan/PeppyMeter/peppymeter.py"
    song = moodeCurrentSong()
    currentSongTitle = song['title']

    print(f"Debug - State: {song['state']}, Title: {currentSongTitle}, PrevStat: {prevstat}, File: {song.get('file', 'N/A')}")

    # --- Manage PeppyMeter ---
    if song.get('file') == "Spotify Active" and prevstat == "OFF":
        prevstat = "ON"
        lastsong = currentSongTitle
        print("Starting PeppyMeter - Spotify connected...")
        time.sleep(4)
        proc = subprocess.Popen([progname], shell=True)

    elif song.get('file') != "Spotify Active" and prevstat == "ON":
        prevstat = "OFF"
        print("Stopping PeppyMeter - Spotify disconnected...")
        subprocess.run(["sudo", "pkill", "-f", "peppymeter.py"])

    if song.get('file') == "Spotify Active" and lastsong != currentSongTitle and prevstat == "ON":
        if proc and proc.poll() is not None:
            print("PeppyMeter process died, restarting...")
            prevstat = "OFF"
            lastsong = currentSongTitle

    # --- Screen control logic (improved) ---
    check_manual_override()

    # Manual override (takes precedence)
    if manual_override == "OFF" and screen_on:
        print(">>> MANUAL SCREEN OFF <<<")
        if blank_screen():
            screen_on = False
        return
    elif manual_override == "ON" and not screen_on:
        print(">>> MANUAL SCREEN ON <<<")
        if unblank_screen():
            screen_on = True
        return

    # Determine Spotify connection and playback state
    is_spotify_connected = (song.get('file') == "Spotify Active")
    is_spotify_playing = is_spotify_connected and (song.get('outrate') != "Not playing")

    # Update last active time if playing
    if is_spotify_playing:
        last_active_time = time.time()

    inactivity = time.time() - last_active_time

    # --- Screen behavior rules ---
    if is_spotify_playing:
        # Screen ON while Spotify is playing
        if not screen_on:
            print(">>> TURNING SCREEN ON - Spotify playing <<<")
            if unblank_screen():
                screen_on = True

    elif is_spotify_connected and not is_spotify_playing:
        # Spotify connected but idle
        if inactivity > INACTIVITY_TIMEOUT and screen_on:
            print(f">>> TURNING SCREEN OFF - Spotify idle {inactivity:.0f}s <<<")
            if blank_screen():
                screen_on = False

    else:
        # Spotify disconnected entirely
        if screen_on:
            print(">>> TURNING SCREEN OFF - Spotify disconnected <<<")
            if blank_screen():
                screen_on = False


def main():
    global screen_on
    now = datetime.now()
    print("Starting fda_autopeppy at", now.strftime("%d/%m/%Y %H:%M:%S"))

    print("Initially blanking screen...")
    if blank_screen():
        screen_on = False

    while True:
        try:
            graph_monitor()
            time.sleep(0.5)
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
        unblank_screen()
        subprocess.run(["sudo", "pkill", "-f", "peppymeter.py"], stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Unexpected error: {e}")
        unblank_screen()
        subprocess.run(["sudo", "pkill", "-f", "peppymeter.py"], stderr=subprocess.DEVNULL)
