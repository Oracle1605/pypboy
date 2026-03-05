#!/usr/bin/python3
import sys
import types
from unittest.mock import MagicMock

def _install_hardware_mocks():
    mock_gpio = MagicMock()
    mock_gpio.BCM = 11
    mock_gpio.OUT = 0
    mock_gpio.IN = 1
    mock_gpio.HIGH = 1
    mock_gpio.LOW = 0
    mock_gpio.PUD_UP = 20
    mock_gpio.PUD_DOWN = 21

    mock_rpi_pkg = types.ModuleType("RPi")
    mock_rpi_pkg.GPIO = mock_gpio
    sys.modules["RPi"] = mock_rpi_pkg
    sys.modules["RPi.GPIO"] = mock_gpio
    sys.modules["smbus"] = MagicMock()  # Often used for Pi-specific screens

    return mock_gpio


try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
    print("--- Hardware Mode Active: Using real RPi.GPIO ---")
except (ImportError, RuntimeError):
    GPIO = _install_hardware_mocks()
    GPIO_AVAILABLE = False
    print("--- Hardware Emulation Active: GPIO and SMBus Mocked ---")
except Exception:
    _, err, _ = sys.exc_info()
    GPIO = _install_hardware_mocks()
    GPIO_AVAILABLE = False
    print("GPIO UNAVAILABLE (%s) -> using mocks" % err)

import pygame
import optparse
import sys
import os
import settings
# pygcurse is provided by a lightweight local stub; no external package required
import pygcurse


#Enable use of cached map via "-c True" command
parser = optparse.OptionParser(usage='python %prog -c True\nor:\npython %prog -c True', version="0.0.1", prog=sys.argv[0])
parser.add_option('-c','--cached-map', action="store_true", help="Loads the cached map file stored in map.cache", dest="load_cached", default=False)
parser.add_option('--autoplay-system', action="store_true", help="Automatically load and play the System Test holotape on startup", dest="autoplay", default=False)
options, args = parser.parse_args()

settings.GPIO_AVAILABLE = GPIO_AVAILABLE

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
    fps_mode = "uncapped" if settings.fps_rate == 0 else f"capped@{settings.frame_per_second}"
    print(
        "[DEV] gpio_available=%s sound_enabled=%s fps_mode=%s cwd=%s root=%s"
        % (
            settings.GPIO_AVAILABLE,
            settings.SOUND_ENABLED,
            fps_mode,
            os.getcwd(),
            settings.ROOT_DIR,
        )
    )

    # optionally autoplay the System Test holotape for diagnostics
    if options.autoplay and "data" in boy.modules:
        data_module = boy.get_module("data")
        # locate holotape submodule
        hol_mod = None
        for sm in data_module.submodules:
            if hasattr(sm, "holotapes"):
                hol_mod = sm
                break
        if hol_mod:
            # pick the first holotape that actually contains audio files; the
            # previous implementation hard-coded "System_Calibration" which
            # meant autoplay always loaded the same tape and ignored others.
            import glob

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
                    # queue absolute paths so playback does not depend on CWD
                    files = [p for (p, _label) in audio_entries]
                    hol.load_audio_file(files)
                    break

    boy.run()
