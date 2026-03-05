import time
import os
import pygame
import game
import pypboy.ui
import settings
from math import atan2, pi, degrees

from pypboy.modules import data
from pypboy.modules import items
from pypboy.modules import stats
from pypboy.modules import boot
from pypboy.modules import map
from pypboy.modules import radio


MODULE_DIR = os.path.dirname(__file__)
BASE_DIR = os.path.abspath(os.path.join(MODULE_DIR, "..", ".."))
SOUNDS_PATH = os.path.join(BASE_DIR, "sounds", "radio")
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


class Pypboy(game.core.Engine):
    currentModule = 0
    prev_fps_time = 0

    def __init__(self, *args, **kwargs):
        # Support rescaling
        # if hasattr(settings, 'OUTPUT_WIDTH') and hasattr(settings, 'OUTPUT_HEIGHT'):
        #     self.rescale = False

        # Initialize modules
        super(Pypboy, self).__init__(*args, **kwargs)
        self.init_persitant()
        self.init_modules()

        self.gpio_actions = {}
        # if settings.GPIO_AVAILABLE:
        # self.init_gpio_controls()

        self.prev_fps_time = 0

    def init_persitant(self):
        # self.background = pygame.image.load('images/background.png')
        overlay = pypboy.ui.Overlay()
        self.root_persitant.add(overlay)
        scanlines = pypboy.ui.Scanlines()
        self.root_persitant.add(scanlines)
        pass

    def init_modules(self):
        self.modules = {
            "radio": radio.Module(self),
            "map": map.Module(self),
            "data": data.Module(self),
            "items": items.Module(self),
            "stats": stats.Module(self),
            "boot": boot.Module(self),
            
        }
        self.switch_module(settings.STARTER_MODULE)  # Set the start screen

    def init_gpio_controls(self):
        for pin in settings.gpio_actions.keys():
            print("Initialing pin %s as action '%s'" % (pin, settings.gpio_actions[pin]))
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self.gpio_actions[pin] = settings.gpio_actions[pin]

    def check_gpio_input(self):
        for pin in self.gpio_actions.keys():
            if GPIO.input(pin) == False:
                self.handle_action(self.gpio_actions[pin])

    # def render(self):
    #     super(Pypboy, self).render()
    #     if hasattr(self, 'active'):
    #         self.active.render()

    def switch_module(self, module):
        # if not settings.hide_top_menu:
        if module in self.modules:
            if hasattr(self, 'active'):
                self.active.handle_action("pause")
                self.remove(self.active)
            self.active = self.modules[module]
            self.active.parent = self
            self.active.handle_action("resume")
            self.add(self.active)
        else:
            print("Module '%s' not implemented." % module)

    def handle_action(self, action):
        if action.startswith('module_'):
            self.switch_module(action[7:])
        else:
            if hasattr(self, 'active'):
                self.active.handle_action(action)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:  # Some key has been pressed
            radio = getattr(settings, "radio", None)
            # Persistent Events:
            if event.key == pygame.K_ESCAPE:  # ESC
                self.running = False

            elif event.key == pygame.K_PAGEUP:  # Volume up
                if radio:
                    radio.handle_radio_event(event)
            elif event.key == pygame.K_PAGEDOWN:  # Volume down
                if radio:
                    radio.handle_radio_event(event)
            elif event.key == pygame.K_END:  # Next Song
                if radio:
                    radio.handle_radio_event(event)
            elif event.key == pygame.K_HOME:  # Prev Song
                if radio:
                    radio.handle_radio_event(event)
            elif event.key == pygame.K_DELETE:
                if radio:
                    radio.handle_radio_event(event)
            elif event.key == pygame.K_INSERT:
                # Hidden dev toggle: Shift+Insert uncaps/re-caps frame rate.
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    if settings.fps_rate > 0:
                        settings.fps_rate = 0
                        print("DEV: FPS uncapped")
                    else:
                        settings.fps_rate = (1 / settings.frame_per_second)
                        print(f"DEV: FPS capped at {settings.frame_per_second}")
                elif radio:
                    radio.handle_radio_event(event)
            elif event.key == pygame.K_F9:
                settings.SHOW_FPS = not getattr(settings, "SHOW_FPS", True)
            else:
                if event.key in settings.ACTIONS:  # Check action based on key in settings
                    self.handle_action(settings.ACTIONS[event.key])

        elif event.type == pygame.QUIT:
            self.running = False

        elif event.type == settings.EVENTS['SONG_END']:
            if settings.SOUND_ENABLED:
                if hasattr(settings, 'radio'):
                    settings.radio.handle_radio_event(event)
        elif event.type == settings.EVENTS['PLAYPAUSE']:
            if settings.SOUND_ENABLED:
                if hasattr(settings, 'radio'):
                    settings.radio.handle_radio_event(event)

        if hasattr(self, 'active'):
            self.active.handle_event(event)

    def inRange(self, angle, init, end):
        return (angle >= init) and (angle < end)

    def run(self):
        self.running = True
        while self.running:
            self.check_gpio_input()
            for event in pygame.event.get():
                self.handle_event(event)

            # slow code debugger
            # debug_time = time.time()

            self.render()
            #
            # time_past = time.time() - debug_time
            # if time_past:
            #     max_fps = int(1 / time_past)
            #     print("self.render took:", time_past, "max fps:", max_fps)

        try:
            pygame.mixer.quit()
        except Exception as e:
            print(e)
