#!/usr/bin/python3
import sys
from unittest.mock import MagicMock

# 1. Create a dummy GPIO module in memory
mock_gpio = MagicMock()
# Add the constants the code expects to find
mock_gpio.BCM = 11
mock_gpio.OUT = 0
mock_gpio.IN = 1
mock_gpio.HIGH = 1
mock_gpio.LOW = 0
mock_gpio.PUD_UP = 20
mock_gpio.PUD_DOWN = 21

# 2. Inject it into the system modules
sys.modules["RPi.GPIO"] = mock_gpio
sys.modules["smbus"] = MagicMock() # Often used for Pi-specific screens

print("--- Hardware Emulation Active: GPIO and SMBus Mocked ---")

import pygame
import optparse
import sys
import settings
# pygcurse is provided by a lightweight local stub; no external package required
import pygcurse


#Enable use of cached map via "-c True" command
parser = optparse.OptionParser(usage='python %prog -c True\nor:\npython %prog -c True', version="0.0.1", prog=sys.argv[0])
parser.add_option('-c','--cached-map', action="store_true", help="Loads the cached map file stored in map.cache", dest="load_cached", default=False)
parser.add_option('--autoplay-system', action="store_true", help="Automatically load and play the System Test holotape on startup", dest="autoplay", default=False)
options, args = parser.parse_args()

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    # Mock GPIO class for non-Pi systems
    class GPIO_Mock:
        BOARD = BCM = IN = OUT = HIGH = LOW = PUD_UP = PUD_DOWN = 0
        def setmode(self, *args): pass
        def setup(self, *args, **kwargs): pass
        def output(self, *args): pass
        def input(self, *args): return 0
        def cleanup(self): pass
        def add_event_detect(self, *args, **kwargs): pass
    GPIO = GPIO_Mock()
    print("Running in non-Pi mode: GPIO disabled.")
    # GPIO.setmode(GPIO.BCM)
    settings.GPIO_AVAILABLE = True
except Exception:
    _, err, _ = sys.exc_info()
    print("GPIO UNAVAILABLE (%s)" % err)
    settings.GPIO_AVAILABLE = False

if settings.GPIO_AVAILABLE:
    pass

try:
    # larger buffer reduces stuttering on slower disks/CPUs
    pygame.mixer.pre_init(44100, -16, 1, 4096)
    settings.SOUND_ENABLED = True
except Exception as e:
    settings.SOUND_ENABLED = False

from pypboy.core import Pypboy

if __name__ == "__main__":
    boy = Pypboy('Pip-Boy 3000 MK IV', settings.WIDTH, settings.HEIGHT)
    print("RUN")

    # optionally autoplay the System Test holotape for diagnostics
    if options.autoplay and "data" in boy.modules:
        # locate holotape submodule
        hol_mod = None
        for sm in boy.modules["data"].submodules:
            if hasattr(sm, "holotapes"):
                hol_mod = sm
                break
        if hol_mod:
            # pick the first holotape that actually contains audio files; the
            # previous implementation hard-coded "System_Calibration" which
            # meant autoplay always loaded the same tape and ignored others.
            import glob, os

            for i, tape in enumerate(hol_mod.holotapes):
                base = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "holotapes", tape.directory)
                )
                audio_entries = []
                if os.path.isdir(base):
                    audio_entries = hol_mod._get_audio_list(base)
                if audio_entries:
                    print(f"autoplay: selecting holotape {tape.label}")
                    hol_mod.select_holotape(i)
                    hol = hol_mod.active_holotape
                    # also make the holotape panel visible so the user sees
                    # the play/pause menu when autoplay triggers
                    hol_mod.add(hol)
                    last_page = len(hol.holotape_data[3]) - 1
                    hol.write_display(last_page, False)
                    # convert to relative paths and queue them
                    rels = [os.path.relpath(p, os.getcwd()) for (p, _label) in audio_entries]
                    hol.load_audio_file(rels)
                    break

    boy.run()
