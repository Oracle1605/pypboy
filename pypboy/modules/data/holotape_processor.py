import glob
# numpy is optional, used for waveform generation
try:
    import numpy as np
except ImportError:
    np = None
    print("holotape_processor: numpy not installed, audio waveform disabled")

import pypboy
import pygame
import game
import settings
# helper to log audio messages without causing a circular import

def _log(msg: str) -> None:
    try:
        from pypboy.modules.data import write_log
        write_log("audio.log", msg)
    except Exception:
        # if logging fails, we silently ignore to avoid crashing the player
        pass

# Use local pygcurse stub for text rendering
import pygcurse

import os
import time
import xml.etree.ElementTree as ET


class Module(pypboy.SubModule):
    label = "HOLOTAPES"

    def __init__(self, *args, **kwargs):
        super(Module, self).__init__(*args, **kwargs)

        self.holotape_folder = 'holotapes/'
        self.holotapes = []
        self.main_menu = []
        self.holotapes_data_set = []
        self.holotapes_data_set = self.get_data()

        self.grid = pygame.Surface((270, 270))

        for holotapes_data in self.holotapes_data_set:
            # holotapes_data = [holotape_name, folder_name, static_text, dynamic_text, menu, action, image]
            # Menu Structure: ["Menu item",Quantity,"Image (or folder for animation")","Description text",[["stats_text_1","stats_number_1"],["stats_text_2","stats_number_2"]]],
            holotape_name = holotapes_data[0]
            image = settings.holotape_generic
            self.main_menu.append([holotape_name, "", image])
            self.holotapes.append(HolotapeClass(holotape_name, holotapes_data))

        self.active_holotape = None

        # state used when prompting user to pick a specific audio track
        self.track_menu = None
        self.pending_audio_files = None

        holotapeCallbacks = []
        for i, holotape in enumerate(self.holotapes):
            holotapeCallbacks.append(lambda i=i: self.select_holotape(i))

        # build the menu objects once during initialization
        self.topmenu = pypboy.ui.TopMenu()
        self.topmenu.label = "DATA"
        self.topmenu.title = settings.MODULE_TEXT
        self.add(self.topmenu)

        self.menu = pypboy.ui.Menu(self.main_menu, holotapeCallbacks, 0)
        self.menu.rect[0] = settings.menu_x
        self.menu.rect[1] = settings.menu_y
        self.add(self.menu)

        settings.FOOTER_TIME[2] = ""
        self.footer = pypboy.ui.Footer(settings.FOOTER_TIME)
        self.footer.rect[0] = settings.footer_x
        self.footer.rect[1] = settings.footer_y
        self.add(self.footer)

        self.prev_static_text = None

    def _get_audio_list(self, base_dir):
        """Return ordered list of (path,label) for audio files in directory.

        If the directory contains a holotape.xml, use the <menu><item page="...">
        entries to establish order and human-friendly titles.  Falls back to a
        simple sorted glob of ``*.ogg`` if XML parsing fails or produces nothing.
        """
        audio_entries = []
        xmlpath = os.path.join(base_dir, 'holotape.xml')
        if os.path.isfile(xmlpath):
            try:
                root = ET.parse(xmlpath).getroot()
                for item in root.iter('item'):
                    page = item.get('page')
                    if page and page.lower().endswith('.ogg'):
                        label = item.text or os.path.basename(page)
                        path = os.path.join(base_dir, page)
                        audio_entries.append((path, label))
            except Exception as e:
                print(f"audio XML parse error: {e}")
                audio_entries = []
        if not audio_entries:
            import glob
            files = sorted(glob.glob(os.path.join(base_dir, '*.ogg')))
            audio_entries = [(f, os.path.basename(f)) for f in files]
        return audio_entries

    def start_audio_queue(self, start_index, files):
        """Helper used during track selection.

        ``files`` is a list of absolute paths; this converts them to
        relative, retains only the portion starting at ``start_index`` and
        pushes the result to the display object for playback.
        """
        _log(f"start_audio_queue index={start_index} files={files}")
        if not files or start_index >= len(files):
            return
        queue = files[start_index:]
        rels = [os.path.relpath(f, os.getcwd()) for f in queue]
        print("Now Playing:", os.path.abspath(rels[0]))
        if hasattr(self.active_holotape, 'load_audio_file'):
            self.active_holotape.load_audio_file(rels)

    def select_holotape(self, holotape):
        print(f"select_holotape called with index {holotape}")
        # simply mark the chosen tape as active; audio is **not** queued here
        # so that scanning through the list doesn't start playback.  the
        # actual queuing occurs when the user presses ENTER in
        # ``handle_event`` below.
        if hasattr(self, 'active_holotape') and self.active_holotape:
            self.remove(self.active_holotape)
            if self.active_holotape.alive():
                self.remove(self.active_holotape)
        self.active_holotape = self.holotapes[holotape]

    def handle_event(self, event):
        # debugging: log event arrival
        print(f"holotape_processor.handle_event: type={event.type} active_holotape={self.active_holotape}")
        # Pypboy.run currently delivers each pygame event twice: once via
        # Engine.handle_event and again when the engine forwards it to the
        # active module.  certain actions (ENTER) may therefore fire two
        # different code paths in the same frame, which caused the track
        # selector to be created and then immediately consumed by the
        # duplicate event.  We mark events we use here so the second pass can
        # ignore them and avoid instantly dismissing the menu.
        if getattr(event, '_holotape_consumed', False):
            print(f"[DEBUG] skipping already‑consumed event {event}")
            return

        # if we're currently displaying a track‑selection menu, let arrow
        # keys move within it and ENTER choose a file.
        if hasattr(self, 'track_menu') and self.track_menu:
            print(f"[DEBUG] event in track_menu: {event}")
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    # guard against duplicate delivery of the same press
                    if getattr(event, '_holotape_consumed', False):
                        print(f"[DEBUG] ignoring repeated ENTER in track_menu {event}")
                        return
                    event._holotape_consumed = True
                    idx = self.track_menu.selected
                    print(f"track menu selection {idx}")
                    # pending list now contains (path,label) tuples
                    paths = [p for (p, _l) in self.pending_audio_files]
                    self.start_audio_queue(idx, paths)
                    # clean up menu and restore original one
                    if self.track_menu.alive():
                        self.remove(self.track_menu)
                    self.track_menu = None
                    self.pending_audio_files = None
                    # restore scanline opacity now that menu is gone
                    settings.dim_scanlines = False
                    if hasattr(self, '_old_menu'):
                        # put the original menu back into the group and restore the
                        # reference so dial actions go to it again
                        self.menu = self._old_menu
                        self.add(self.menu)
                        del self._old_menu
                    # add holotape view now that a track has been chosen
                    if self.active_holotape:
                        print(f"[DEBUG] restoring active_holotape {self.active_holotape}")
                        self.add(self.active_holotape)
                    # hide the normal menus for playback
                    settings.hide_top_menu = True
                    settings.hide_submenu = True
                    settings.hide_main_menu = True
                    settings.hide_footer = False
                    # show the audio control page
                    if self.active_holotape and self.active_holotape.alive():
                        last = len(self.active_holotape.holotape_data[3]) - 1
                        self.active_holotape.write_display(last, True)
                    return
                # dial actions are processed elsewhere by handle_action
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:

                print("ENTER pressed on holotape menu (active_holotape=", self.active_holotape, ")")

                # gather audio files first so we know whether we'll need a
                # track‑selector.  delays hiding the main menu until after the
                # selection completes or is skipped.
                base = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'holotapes', self.active_holotape.directory)
                )
                audio_entries = []
                if os.path.isdir(base):
                    audio_entries = self._get_audio_list(base)

                if audio_entries:
                    self.pending_audio_files = audio_entries
                    if len(audio_entries) > 1:
                        # show track menu and keep the rest of the UI visible
                        settings.hide_top_menu = False
                        settings.hide_submenu = False
                        settings.hide_main_menu = False
                        # build a temporary menu listing each file title
                        labels = [[label, "", ""] for (_path, label) in audio_entries]
                        print("[DEBUG] creating track_menu with labels", labels)
                        self.track_menu = pypboy.ui.Menu(labels, [], 0)
                        # when the temporary track selector is active we dim the
                        # scanline overlay so text remains legible
                        settings.dim_scanlines = True
                        self.track_menu.rect[0] = settings.menu_x
                        self.track_menu.rect[1] = settings.menu_y
                        # take the existing menu out of the render list
                        # if the holotape view is currently drawn it will obscure the
                        # temporary track selector, so take it out of the group and put it
                        # back later (we already restore it after a choice is made).
                        if self.active_holotape:
                            print(f"[DEBUG] hiding active_holotape {self.active_holotape}")
                            # remove from any groups so it won't cover the menu
                            try:
                                self.remove(self.active_holotape)
                            except Exception:
                                pass

                        self._old_menu = self.menu
                        self.remove(self._old_menu)
                        # switch pointer and add new track selector
                        self.menu = self.track_menu
                        self.add(self.track_menu)
                        # ensure the menu is rendered at least once so the user can
                        # actually see the titles without having to dial around
                        # (previously the surface was left black until the first
                        # dial_move caused a redraw).
                        self.track_menu.select(0)
                        # mark the original pygame event so the engine's second
                        # delivery doesn't immediately treat it as a selection.
                        event._holotape_consumed = True
                        return
                    else:
                        # single track, queue immediately
                        # extract path only
                        only = [audio_entries[0][0]]
                        self.start_audio_queue(0, only)

                # at this point either there were no audio files or the user
                # chose one; proceed to open holotape view and hide menus.
                # add the holotape view to the layer stack so it becomes
                # visible immediately
                self.add(self.active_holotape)

                if self.active_holotape.alive():
                    settings.hide_top_menu = True
                    settings.hide_submenu = True
                    settings.hide_main_menu = True
                    settings.hide_footer = False
                    print("Loading Holotape:", self.active_holotape.label)

                    # show the audio control page rather than the first
                    # page of the tape; this matches the behaviour users expect
                    # when they select a holotape in other versions
                    last = len(self.active_holotape.holotape_data[3]) - 1
                    print(f"writing display page {last}")
                    # display entire page immediately (skip typewriter)
                    self.active_holotape.write_display(last, True)

                if self.active_holotape and not self.active_holotape.skip and self.active_holotape.crawling:
                    self.active_holotape.handle_event(event)

            elif event.key == pygame.K_BACKSPACE:
                self.handle_resume()
                print("Back to main holotape menu")

        if self.active_holotape and self.active_holotape.waiting_for_input:
            self.active_holotape.handle_event(event)

    def handle_resume(self):
        """Called when the user backs out of a holotape or the module is
        re‑activated.

        The base implementation only clears the ``paused`` flag and plays a
        sound; we also need to make sure all of the hide_* flags are reset so
        the holotape list is actually visible again.  Without this the menu
        appears "empty" even though ``self.holotapes`` is untouched.
        """
        super(Module, self).handle_resume()
        if hasattr(self, 'active_holotape') and self.active_holotape:
            self.active_holotape.clear_display()
        if self.active_holotape.alive():
            self.remove(self.active_holotape)
        # restore visibility for all menu layers
        settings.hide_top_menu = False
        settings.hide_submenu = False
        settings.hide_main_menu = False
        settings.hide_footer = False
        # make sure scanlines go full‑opacity again
        settings.dim_scanlines = False

        if self.paused:
            self.paused = False
            settings.hide_top_menu = False
            settings.hide_submenu = False
            settings.hide_main_menu = False
            settings.hide_footer = False

    def handle_pause(self):
        # print("Holotape paused")
        self.active_holotape.clear_display()

    def get_data(self):
        # Get list of folders
        folders = []
        holotapes_data = []
        holotape_name = None
        holotape_type = None
        folder_name = None

        for f in sorted(os.listdir(self.holotape_folder)):
            if not f.endswith("/"):
                folders.append(self.holotape_folder + f)

        for folder in folders:
            holotape_page_data = []
            folder_name = os.path.basename(folder)  # Get the folder name without the full path
            if len(glob.glob(folder + "/holotape.xml")) == 0:
                print("No holotape.xml file in:", folder)
                continue
            menu_file = ("./" + folder + "/" + "holotape.xml")

            try:
                holotape_xml = ET.parse(menu_file).getroot()

                for element in holotape_xml.iter("title"):
                    holotape_name = element.text
                for element in holotape_xml.iter("type"):
                    holotape_type = element.text

                pages = []
                for page in holotape_xml.iter("page"):
                    page_data = []
                    static_text = None
                    static_texts = []
                    try:
                        static_text = page.find("static_text").text
                        self.prev_static_text = static_text
                    except:
                        if self.prev_static_text:
                            static_text = self.prev_static_text
                        else:
                            static_text = None

                    dynamic_text = None
                    try:
                        dynamic_text = page.find("dynamic_text").text
                    except:
                        dynamic_text = None

                    menu = []
                    action = []
                    try:
                        for element in page.find("menu"):
                            menu.append(element.text)
                            try:
                                attribute = element.attrib
                                if attribute["page"]:
                                    action.append(attribute["page"])
                            except:
                                action.append("0")
                    except:
                        # print("No menu found in:",page)
                        menu = ["[< Back]"]
                        action = ["Previous"]
                    page_data.append(static_text)
                    page_data.append(dynamic_text)
                    page_data.append(menu)
                    page_data.append(action)
                    pages.append(page_data)
                    # print("********************")
                    # print(page_data)
                    # print("********************")

            except Exception as e:
                holotape_name = folder_name
                print(str(e), ' could not read xml file in', folder_name)

            holotape_page_data = [holotape_name, folder_name, holotape_type, pages]
            # print("xxxxxxxxxxxxxxxxxxxxxxxxxxxx")
            # print(holotape_page_data)
            # print("xxxxxxxxxxxxxxxxxxxxxxxxxxxx")

            holotapes_data.append(holotape_page_data)

        return holotapes_data


class HolotapeDisplay(game.Entity):
    def __init__(self, *args, **kwargs):
        super(HolotapeDisplay, self).__init__((settings.WIDTH, settings.HEIGHT - 100), *args, **kwargs)

        self.holotape_image_width = settings.WIDTH - 10
        self.holotape_image = pygame.Surface((self.holotape_image_width, settings.HEIGHT - 100))
        self.holotape_image.fill((0, 0, 0))
        self.rect[0] = 11
        self.rect[1] = 51

        self.cursor_x = 0
        self.cursor_y = 0
        self.prev_x = 0
        self.prev_y = 0

        self.prev_time = 0
        self.current_time = 0
        self.button = None
        self.cursor_time = 1  # Cursor blink speed
        self.prev_cursor_time = 0
        self.char_index = 0
        self.menu_index = 0
        self.prev_line = 0
        self.blink = False
        self.static_text_index = 0
        self.dynamic_text_index = 0
        self.menu_text_index = 0
        self.menu_start = 0
        self.menu_end = 0
        self.line = 0
        self.waiting_for_input = False
        self.crawling = False

        # Audio holotape related:
        self.holotape_waveform_width, self.holotape_waveform_height = 250, 250
        self.holotape_waveform_image = pygame.Surface((self.holotape_waveform_width, self.holotape_waveform_height))
        self.holotape_waveform_animation_time = 1 / settings.waveform_fps
        self.grid = pygame.Surface((270, 270))

        self.prev_time = 0
        self.index = 0
        self.current_time = 0
        self.delta_time = 0
        self.prev_waveform_time = 0
        self.holotape_waveform = None
        self.holotape_waveform_length = None
        self.audio_file = None
        self.audio_file_length = 0
        self.sound_object = None
        self.max_length = 0
        self.page = 0
        self.previous_page = 0
        self.skip = False
        self.console_text = None
        self.saved_song = None
        self.saved_song_pos = None

        if settings.SOUND_ENABLED:
            self.sfx_dial_move = pygame.mixer.Sound('./sounds/pipboy/RotaryVertical/UI_PipBoy_RotaryVertical_01.ogg')
            self.sfx_dial_move.set_volume(settings.VOLUME)
            self.sfx_text = pygame.mixer.Sound('./sounds/terminal/UI_Terminal_CharScroll_LP.ogg')
            self.sfx_text.set_volume(settings.VOLUME / 3)
            self.sfx_ok = pygame.mixer.Sound('./sounds/pipboy/UI_Pipboy_OK_Press.ogg')
            self.sfx_ok.set_volume(settings.VOLUME)

        self.font = settings.TechMono[25]
        self.char_width, self.char_height = self.font.size("X")
        self.max_chars = int(settings.WIDTH / self.char_width) - 5
        self.max_lines = int((settings.HEIGHT - 100) / self.char_height) - 1


        # Create the text surface; our stub handles rendering to
        # ``self.holotape_image`` so we never need to guard for its
        # absence.
        self.holotape_screen = pygcurse.PygcurseSurface(
            self.max_chars,
            self.max_lines + 1,
            self.font,
            settings.bright,
            settings.black,
            self.holotape_image,
            True,
            1000,
        )
        # disable any automatic updates; drawing is managed manually
        self.holotape_screen._autoupdate = False
        self.holotape_screen._autodisplayupdate = False

    def write_display(self, page, skip=False):
        # print ("Drawing page:", page, "self.previous_page = ",self.previous_page,'Skip=',skip)
        self.waiting_for_input = False
        self.skip = skip
        self.previous_page = self.page
        self.page = page
        settings.hide_top_menu = True
        settings.hide_submenu = True
        settings.hide_main_menu = True
        settings.hide_footer = True
        self.line = 0
        self.static_text_index = 0
        self.dynamic_text_index = 0
        self.menu_text_index = 0
        self.char_index = 0
        self.holotape_screen.cursor = (0, 0)

        if self.page >= len(self.holotape_data[3]):
            print("Selected an invalid page", self.page, len(self.holotape_data[3]))
            self.page = 0

        self.static_text, self.dynamic_text, self.menu, self.actions = self.fetch_page(self.holotape_data, self.page)

        # ensure menu/actions lists exist to avoid attribute errors later
        self.menu = self.menu or []
        self.actions = self.actions or []

        self.static_text = self.static_text.replace('\\n', '\n').replace('\\t', '\t')

        if self.dynamic_text:
            self.dynamic_text = self.dynamic_text.replace('\\n', '\n').replace('\\t', '\t')

    def clear_display(self):
        self.holotape_image.fill((0, 0, 0))
        self.static_text_index = 0
        self.dynamic_text_index = 0
        self.menu_text_index = 0
        self.char_index = 0
        self.waiting_for_input = False
        settings.hide_top_menu = False
        settings.hide_submenu = False
        settings.hide_main_menu = False
        settings.hide_footer = False
        self.line = 0
        self.skip = False
        self.holotape_screen.cursor = (0, 0)

        if self.holotape_waveform:
            print("Clearing waveform")
            self.holotape_waveform_image.fill((0, 0, 0))
            pygame.mixer.music.stop()
            self.audio_file = None
            self.holotape_waveform = None
            pygame.mixer.music.set_endevent(settings.EVENTS['SONG_END'])
            pygame.event.post(pygame.event.Event(settings.EVENTS['SONG_END']))

        print("Clear Holotape")
        self.image.fill((0, 0, 0))

    def handle_event(self, event):
        if event.type == settings.EVENTS['HOLOTAPE_END']:
            # log the fact that the current track ended
            if self.audio_file:
                msg = f"Track finished: {self.audio_file}"  
                print(msg)
                _log(msg)
            # if we're in the middle of a queued list, advance instead of clearing
            if hasattr(self, 'audio_queue') and self.audio_queue:
                if self.current_track_index < len(self.audio_queue) - 1:
                    self.current_track_index += 1
                    msg = f"Queue advancing to next track: {self.audio_queue[self.current_track_index]}"
                    print(msg)
                    _log(msg)
                    # use channel playback for smoother transition
                    self.play_current_from_queue()
                    return
                else:
                    # queue finished – drop the list so normal handling runs
                    print("Queue completed")
                    _log("Queue completed")
                    self.audio_queue = []
                    self.current_track_index = 0
            if self.holotape_waveform:
                print("End of Audio Holotape")
                self.holotape_waveform = None
                self.holotape_image.fill((0, 0, 0))
                self.write_display(self.previous_page, True)
            if self.saved_song:
                # pygame.event.post(pygame.event.Event(settings.EVENTS['SONG_END']))
                # print("Resuming song", self.saved_song, "at position", self.saved_song_pos)
                pygame.mixer.music.load(self.saved_song)
                try:
                    pygame.mixer.music.play(0, self.saved_song_pos)
                except:
                    pygame.mixer.music.play(0, 0)
                self.saved_song = None
                self.saved_song_pos = None
                pygame.mixer.music.set_endevent(settings.EVENTS['SONG_END'])

        if self.waiting_for_input:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.update_cursor("Up")
                if event.key == pygame.K_DOWN:
                    self.update_cursor("Down")
                if event.key == pygame.K_RETURN:
                    self.update_cursor("Enter")
        elif not self.skip:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    if settings.SOUND_ENABLED:
                        self.sfx_ok.play()
                    self.skip = True

    def fetch_page(self, holotape_data, page):
        try:
            static_text = holotape_data[3][page][0]
        except:
            static_text = None
        try:
            dynamic_text = holotape_data[3][page][1]
        except:
            dynamic_text = None
        try:
            menu = holotape_data[3][page][2]
        except:
            menu = []
        try:
            actions = holotape_data[3][page][3]
        except:
            actions = []

        return static_text, dynamic_text, menu, actions

    def strip_end_block(self, line):
        if not self.holotape_screen:
            return ""
        text = self.holotape_screen.getchars((0, self.line, self.max_chars, 1))
        text = str(text[0])
        text = text.rstrip()
        text = text.rstrip("▯")
        return text

    def draw_holotape_screen(self):
        # the text surface is always available thanks to our stub
        if not self.holotape_screen:
            # defensive, but should never happen
            return
        self.line = self.holotape_screen.cursory
        self.holotape_screen.erase((0,0,self.max_chars,self.max_lines))

        if self.alive():
            if not self.skip:
                self.crawling = True
                # Draw static text
                if self.static_text_index < len(self.static_text):
                    # print("Drawing static_text", self.static_text)
                    if not self.page:  # Draw static text slowly on first screen only
                        self.holotape_screen.write(self.static_text[self.static_text_index])
                        self.holotape_screen.putchar("▯", self.holotape_screen.cursorx, self.holotape_screen.cursory)
                        self.static_text_index += 1
                    else:
                        self.holotape_screen.write(self.static_text, 0, 0)
                        self.static_text_index = 1000

                # Draw dynamic text
                elif self.dynamic_text and self.dynamic_text_index < len(self.dynamic_text):
                    # print("Drawing dynamic_text", self.dynamic_text)
                    text = str(self.dynamic_text[self.dynamic_text_index])
                    self.holotape_screen.write(self.dynamic_text[self.dynamic_text_index])
                    self.holotape_screen.putchar("▯", self.holotape_screen.cursorx, self.holotape_screen.cursory)
                    self.dynamic_text_index += 1
                    self.menu_start = self.holotape_screen.cursory

                # Draw menu
                elif self.menu and self.menu_index < len(self.menu):
                    if self.menu_text_index < len(self.menu[self.menu_index]):
                        self.holotape_screen.write(self.menu[self.menu_index][self.menu_text_index])
                        self.holotape_screen.putchar("▯", self.holotape_screen.cursorx, self.holotape_screen.cursory)
                        self.menu_text_index += 1
                    else:
                        self.menu_text_index = 0
                        self.menu_index += 1
                        self.holotape_screen.cursory += 1
                        self.holotape_screen.cursorx = 0
                elif self.menu and self.menu_index == len(self.menu):
                    self.menu_text_index = 0
                    self.menu_end = self.holotape_screen.cursory - 1
                    self.menu_index += 1
                    self.skip = True

            if self.line != self.holotape_screen.cursory:
                text = self.strip_end_block(self.line)
                self.holotape_screen.putchars(text + " ", 0, self.line)

            # Skip and just draw everything at once
            if self.skip:
                self.crawling = False
                print("Skip text crawl", self.skip)
                self.holotape_screen.fill(" ")
                self.holotape_screen.write(self.static_text, 0, 0)
                if self.dynamic_text:
                    self.holotape_screen.write(self.dynamic_text, 0, self.holotape_screen.cursory)
                if self.menu:
                    self.menu_start = self.holotape_screen.cursory
                    for each in self.menu:
                        self.holotape_screen.write(each, 0, self.holotape_screen.cursory)
                        self.menu_end = self.holotape_screen.cursory
                        self.holotape_screen.cursory += 1
                    self.holotape_screen.reversecolors((0, self.menu_start, self.max_chars, 1))
                    self.holotape_screen.cursorx = 0
                    self.holotape_screen.cursory = self.menu_start
                    self.cursor_x = self.holotape_screen.cursorx
                    self.cursor_y = self.holotape_screen.cursory
                self.waiting_for_input = True
                self.skip = False

            # Play sound on each action
            if settings.SOUND_ENABLED:
                self.sfx_text.play()

    def render(self, *args, **kwargs):
        # if the terminal screen module isn't available there's nothing to
        # draw. still run the parent class in case it needs to update state.
        super(HolotapeDisplay, self).render(self, *args, **kwargs)
        if not self.holotape_screen:
            return

        # Always keep a running clock regardless of waveform state; the
        # previous implementation only updated ``current_time`` when a
        # waveform existed, which meant nothing ever drew if audio failed to
        # queue.  Update the timer first so the rest of the method can use it.
        self.current_time = time.time()

        # maintain a simple debug timer for occasional logging
        if not hasattr(self, 'debug_time') or self.debug_time is None:
            self.debug_time = self.current_time

        time_past = self.current_time - self.debug_time
        if time_past:
            max_fps = int(1 / time_past)
            print("Holotape render took:", time_past, "max fps:", max_fps)
            self.debug_time = self.current_time

        print("Rendering Holotape")

        if self.alive():
            if (self.current_time - self.prev_time) >= settings.fps_rate:
                self.prev_time = self.current_time
                print("Should be showing holotape", self.label)

                self.image.fill((128, 128, 0))

                if not self.waiting_for_input:
                    self.draw_holotape_screen()
                else:
                    # Blink cursor at the bottom
                    if self.current_time - self.prev_cursor_time >= self.cursor_time:
                        self.prev_cursor_time = self.current_time
                        for char in range(self.max_chars):
                            self.holotape_screen.putchar(' ', char, self.max_lines)
                        self.holotape_screen.putchar(">", 0, self.max_lines)
                        if self.console_text:
                            self.holotape_screen.putchars(self.console_text, 2, self.max_lines)
                        else:
                            if self.blink:
                                self.holotape_screen.putchar(' ', 2, self.max_lines)
                                self.blink = False
                            else:
                                self.holotape_screen.putchar('▯', 2, self.max_lines)
                                self.blink = True
                self.holotape_screen.update()
                self.image.blit(self.holotape_image, (0, 0))

        if self.holotape_waveform:
            self.console_text = "Playing Holotape Audio..."
            self.draw_grid()
            self.render_holotape_waveform()
            self.image.blit(self.grid, (225, 230))

        self.image.blit(self.holotape_waveform_image, (225, 230))
        if not pygame.mixer.music.get_busy():
            pygame.draw.line(self.holotape_waveform_image, settings.bright,
                             [0, self.holotape_waveform_height / 2 + 10],
                             [self.holotape_waveform_width, self.holotape_waveform_height / 2 + 10], 2)
        else:
            self.holotape_waveform_image.fill((0, 0, 0))
            self.grid.fill((0, 0, 0))
            self.console_text = None
    
     #

    def draw_grid(self):
        self.grid.fill((0, 0, 0))
        long_line = 14
        long_lines = 10
        short_line = 9
        short_lines = long_lines * 3
        line_start = 0
        bottom = self.grid.get_rect().bottom
        right = self.grid.get_rect().right

        pygame.draw.lines(self.grid, settings.light, False, [(0, 268), (268, 268), (268, 0)], 3)

        line_x = int(self.grid.get_rect().height / long_lines)
        while long_lines >= 1:
            line_start += line_x
            pygame.draw.line(self.grid, settings.light, (line_start, bottom), (line_start, bottom - long_line), 2)
            pygame.draw.line(self.grid, settings.light, (right, line_start), (right - long_line, line_start), 2)
            long_lines -= 1

        line_start = 0
        line_x = int(self.grid.get_rect().height / short_lines)
        while short_lines > 2:
            line_start += line_x
            pygame.draw.line(self.grid, settings.light, (line_start, bottom), (line_start, bottom - short_line), 2)
            pygame.draw.line(self.grid, settings.light, (right, line_start), (right - short_line, line_start), 2)
            short_lines -= 1

    def expand(self, oldvalue, oldmin, oldmax, newmin, newmax):
        oldRange = oldmax - oldmin
        newRange = newmax - newmin
        newvalue = ((oldvalue - oldmin) * newRange / oldRange) + newmin
        return newvalue

    def load_audio_file(self, file):
        """Begin playback of a holotape audio file or queue.

        This method is heavily instrumented to record the absolute path that is
        attempted and whether it actually exists. Entries are written to
        ``audio.log`` so we can see why playback might fail during normal
        execution.
        """
        _log(f"load_audio_file called with {file}")
        # announce to console when each track begins
        if isinstance(file, str) and file.lower().endswith('.ogg'):
            msg = f"Starting playback: {file}"
            print(msg)
            _log(msg)

        # Converts relative paths to absolute based on the project root so
        # working directory doesn't matter.
        # Silently handles missing sound support or numpy.
        # sanity checks
        if not settings.SOUND_ENABLED:
            print("load_audio_file: sound disabled, skipping audio request")
            return

        # accept a directory path and turn it into a queue automatically
        if isinstance(file, str) and os.path.isdir(file):
            # list contained ogg files and recurse
            import glob

            files = sorted(glob.glob(os.path.join(file, "*.ogg")))
            if files:
                self.load_audio_file(files)
            return

        # support an explicit queue of files
        if isinstance(file, (list, tuple)):
            import traceback
            trace = ''.join(traceback.format_stack(limit=10))
            _log(f"queue load invoked, stack:\n{trace}")
            # make each path absolute too (same base as single-file case)
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
            queue = [os.path.normpath(os.path.join(base, f)) if not os.path.isabs(f) else f for f in file]
            # store the list
            self.audio_queue = queue
            self.current_track_index = 0
            # play first track using the channel-based helper (avoids repeated music.load)
            self.play_current_from_queue()
            return

        # make path absolute relative to project root if necessary
        # ``holotapes`` sits next to the top-level ``pypboy`` package, so we
        # need to climb three levels from this module file to reach it.
        if file and not os.path.isabs(file):
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
            file = os.path.normpath(os.path.join(base, file))

        # handle single audio file path
        if file and isinstance(file, str) and file.lower().endswith(".ogg"):
            # verify existence
            if not os.path.exists(file):
                msg = f"Audio file not found: {file}"
                print(msg)
                _log(msg)
                return

            print("Loading holotape page")
            # ensure we have pages to display; skip if terminal unavailable
            if hasattr(self, 'holotape_data') and self.holotape_data and self.holotape_screen:
                self.write_display(len(self.holotape_data[3]) - 1, True)
            # record the current audio file path
            self.audio_file = file

            if settings.CURRENT_SONG:
                # save/ pause any currently playing music
                self.saved_song = settings.CURRENT_SONG
                self.saved_song_pos = pygame.mixer.music.get_pos()
                pygame.mixer.music.pause()

            try:
                pygame.mixer.music.load(self.audio_file)  # Load for streaming playback
                pygame.mixer.music.set_endevent(settings.EVENTS['HOLOTAPE_END'])
                pygame.mixer.music.play()
            except Exception as e:
                msg = f"Failed to start music playback: {e}"
                print(msg)
                _log(msg)

            # compute waveform asynchronously to avoid blocking audio thread
            if np and self.sound_object:
                self.audio_file_length = self.sound_object.get_length()

                def compute_waveform():
                    try:
                        amplitude = pygame.sndarray.array(self.sound_object)
                        amplitude = amplitude.flatten()
                        amplitude = amplitude[::settings.frame_skip]
                        amplitude = amplitude.astype('float64')
                        amplitude = (
                            self.holotape_waveform_height
                            * (amplitude - np.min(amplitude))
                            / np.ptp(amplitude)
                        ).astype(int)
                        self.holotape_waveform = [
                            int(self.holotape_waveform_height / 2)
                        ] * self.holotape_waveform_height + list(amplitude + 27)
                        self.holotape_waveform_length = len(self.holotape_waveform)
                    except Exception as e:
                        print(f"Waveform generation failed: {e}")
                        self.holotape_waveform = None
                        self.holotape_waveform_length = 0

                import threading

                thread = threading.Thread(target=compute_waveform, daemon=True)
                thread.start()
            else:
                # numpy not available, no waveform
                self.holotape_waveform = None
                self.holotape_waveform_length = 0

    def play_current_from_queue(self):
        """Play the currently indexed track in ``self.audio_queue``.
        """
        if not hasattr(self, 'audio_queue') or not self.audio_queue:
            return

        if self.current_track_index < len(self.audio_queue):
            track = self.audio_queue[self.current_track_index]
            try:
                sound = pygame.mixer.Sound(track)
                channel = pygame.mixer.Channel(5)
                channel.play(sound)

                # This allows the HUD to show "Part 1 of 10"
                self.hud_status = f"Playing: {self.current_track_index + 1}/{len(self.audio_queue)}"
                msg = f"Now Playing: {track}"
                print(msg)
                _log(msg)
            except Exception as e:
                    msg = f"Queue Error: {e}"
                    print(msg)
                    _log(msg)
    def render_holotape_waveform(self):
        self.current_time = time.time()
        self.delta_time = self.current_time - self.prev_waveform_time
        if self.delta_time >= self.holotape_waveform_animation_time:
            file_pos = self.holotape_waveform_length
            self.prev_waveform_time = self.current_time
            self.holotape_waveform_image.fill((0, 0, 0))
            length = int(self.audio_file_length * 1000)
            if pygame.mixer.music.get_busy():
                file_pos = pygame.mixer.music.get_pos()

            self.index = int(
                self.expand(file_pos, 0, length, 0, self.holotape_waveform_length))

            if self.index < self.holotape_waveform_length and pygame.mixer.music.get_busy():
                prev_x, prev_y = 0, self.holotape_waveform[self.index]
                for x, y in enumerate(
                        self.holotape_waveform[self.index + 1:self.index + 1 + self.holotape_waveform_width][::1]):
                    pygame.draw.line(self.holotape_waveform_image, settings.bright, [prev_x, prev_y], [x, y], 2)
                    prev_x, prev_y = x, y
                    # Credit to https://github.com/prtx/Music-Visualizer-in-Python/blob/master/music_visualizer.py

    def update_cursor(self, button=None):
        # Logic here executes regardless of the underlying text backend
        # "Enter" to execute. Only skip visual cursor updates when the
        # screen object is missing.

        visual = bool(self.holotape_screen)

        if button == "Down":
            self.line = self.cursor_y
            self.cursor_y = self.cursor_y + 1
            print("Down")
        elif button == "Up":
            self.line = self.cursor_y
            self.cursor_y = self.cursor_y - 1
            print("Up")

        if visual and (button == "Down" or button == "Up"):
            # Constrain the position to selectable areas
            if self.cursor_y < self.menu_start:
                self.cursor_y = self.menu_start
                self.cursor_x = 0
            elif self.cursor_y > self.menu_end:
                self.cursor_y = self.menu_end
                self.cursor_x = 0

            if self.cursor_y != self.line:
                if settings.SOUND_ENABLED:
                    self.sfx_dial_move.play()
                self.holotape_screen.cursor = (0, self.cursor_y)
                self.holotape_screen.reversecolors((0, self.line, self.max_chars, 1))
                self.holotape_screen.reversecolors((0, self.cursor_y, self.max_chars, 1))
        
        if button == "Enter":
            print("Return")
            if settings.SOUND_ENABLED:
                self.sfx_ok.play()
            if self.menu and self.actions:
                if len(self.actions) > 1:
                    menu_selection = int(
                        self.expand(self.cursor_y, self.menu_start, self.menu_end, 0, len(self.menu) - 1))
                else:
                    menu_selection = 0

                action = self.actions[menu_selection]
                # print("Action=", action, "Actions =", self.actions)

                if str.isdigit(action):
                    action = int(action)
                    self.clear_display()
                    # print("Jumping to page", action)
                    self.write_display(action)
                else:
                    if isinstance(action, str) and action.lower().endswith(".ogg"):
                        msg = f"Found audio file: {action}"
                        print(msg)
                        _log(msg)
                        self.load_audio_file("holotapes/" + self.directory + "/" + action)
                    elif action == "Exit":
                        settings.hide_top_menu = False
                        settings.hide_submenu = False
                        settings.hide_main_menu = False
                        settings.hide_footer = False
                        self.clear_display()
                    elif action == "Previous":
                        if self.page > 0:
                            self.page = self.previous_page
                            self.clear_display()
                            self.write_display(self.page, True)
                            print("Previous page")
                    elif action == "Pause":
                        print("Pausing/Resuming Holotape", self.page, self.previous_page)
                        if pygame.mixer.music.get_busy():
                            pygame.mixer.music.pause()
                        else:
                            pygame.mixer.music.unpause()
                    else:
                        settings.hide_top_menu = False
                        settings.hide_submenu = False
                        settings.hide_main_menu = False
                        settings.hide_footer = False
                        self.clear_display()
                        print("Exiting to main menu")
            else:
                settings.hide_top_menu = False
                settings.hide_submenu = False
                settings.hide_main_menu = False
                settings.hide_footer = False
        
        return self.cursor_y, self.cursor_x

        if button == "Down" or button == "Up":
            # Constrain the position to selectable areas
            if self.cursor_y < self.menu_start:
                self.cursor_y = self.menu_start
                self.cursor_x = 0
            elif self.cursor_y > self.menu_end:
                self.cursor_y = self.menu_end
                self.cursor_x = 0

            if self.cursor_y != self.line:
                if settings.SOUND_ENABLED:
                    self.sfx_dial_move.play()
                self.holotape_screen.cursor = (0, self.cursor_y)
                self.holotape_screen.reversecolors((0, self.line, self.max_chars, 1))
                self.holotape_screen.reversecolors((0, self.cursor_y, self.max_chars, 1))
                # print("prev_y = ", self.prev_y, "cursor_y =", self.cursor_y, "menu_start=", self.menu_start, "menu_end = ",
                #       self.menu_end)

        elif button == "Enter":
            print("Return")
            if settings.SOUND_ENABLED:
                self.sfx_ok.play()
            if self.menu and self.actions:
                if len(self.actions) > 1:
                    menu_selection = int(
                        self.expand(self.cursor_y, self.menu_start, self.menu_end, 0, len(self.menu) - 1))
                else:
                    menu_selection = 0

                action = self.actions[menu_selection]
                # print("Action=", action, "Actions =", self.actions)

                if str.isdigit(action):
                    action = int(action)
                    self.clear_display()
                    # print("Jumping to page", action)
                    self.write_display(action)
                else:
                    if isinstance(action, str) and action.lower().endswith(".ogg"):
                        msg = f"Found audio file: {action}"
                        print(msg)
                        _log(msg)
                        self.load_audio_file("holotapes/" + self.directory + "/" + action)
                    elif action == "Exit":
                        settings.hide_top_menu = False
                        settings.hide_submenu = False
                        settings.hide_main_menu = False
                        settings.hide_footer = False
                        self.clear_display()
                    elif action == "Previous":
                        # print("Going to previous page", self.page, self.previous_page)
                        if self.page > 0:
                            self.page = self.previous_page
                            self.clear_display()
                            self.write_display(self.page, True)
                            print("Previous page")
                    elif action == "Pause":
                        print("Pausing/Resuming Holotape", self.page, self.previous_page)
                        if pygame.mixer.music.get_busy():
                            pygame.mixer.music.pause()
                        else:
                            pygame.mixer.music.unpause()
                    else:
                        settings.hide_top_menu = False
                        settings.hide_submenu = False
                        settings.hide_main_menu = False
                        settings.hide_footer = False
                        self.clear_display()
                        print("Exiting to main menu")
            else:
                settings.hide_top_menu = False
                settings.hide_submenu = False
                settings.hide_main_menu = False
                settings.hide_footer = False
                self.clear_display()
                print("Going back to main menu")

        return self.cursor_y, self.cursor_x

    def __le__(self, other):
        if type(other) is not HolotapeDisplay:
            return 0
        else:
            return self.label <= other.label

    def __ge__(self, other):
        if type(other) is not HolotapeDisplay:
            return 0
        else:
            return self.label >= other.label


class HolotapeClass(HolotapeDisplay):
    def __init__(self, holotape_name, holotape_data, *args, **kwargs):
        super(HolotapeClass, self).__init__(self, *args, **kwargs)
        # holotapes_data = [holotape_name, folder_name, holotape_type, static_text, dynamic_text, menu, action]
        self.label = holotape_name
        self.directory = holotape_data[1]
        self.holotape_type = holotape_data[2]
        holotape_display_page = ['Welcome to ROBCO Industries (TM) Termlink\\n\\n', 'Holotape Audio\\n\\n', [
            '[< Back]', '[Play / Pause]'], ['Previous', 'Pause']]
        holotape_data[3].append(holotape_display_page)

        self.holotape_data = holotape_data


class Health(game.Entity):

    def __init__(self):
        super(Health, self).__init__()

        self.image = pygame.Surface((settings.WIDTH, settings.HEIGHT - 180))
        self.image.fill((0, 0, 0))
        #
        # # Bottom Boxes
        # pygame.draw.rect(self.image, settings.dim, (0, 501, 166, 38)) #Hit point background
        # pygame.draw.rect(self.image, settings.dim, (170, 501, 370, 38)) #Level bar background
        # pygame.draw.lines(self.image, settings.mid,True,[(282,515),(529,515),(529,529),(282,529)], 3) #Level bar surround
        # pygame.draw.rect(self.image, settings.bright, (285, 517, 179, 11)) #Level bar fill
        # pygame.draw.rect(self.image, settings.dim, (544, 501, 176, 38)) #Actiion background

        # Middle Boxes
        pygame.draw.rect(self.image, settings.dim, (203, 358, 64, 62))  # Gun box
        pygame.draw.rect(self.image, settings.dim, (273, 358, 38, 62))  # Ammo box
        pygame.draw.rect(self.image, settings.dim, (328, 358, 64, 62))  # Helmet box
        pygame.draw.rect(self.image, settings.dim, (398, 358, 38, 62))  # Armor box
        pygame.draw.rect(self.image, settings.dim, (440, 358, 38, 62))  # Energy box
        pygame.draw.rect(self.image, settings.dim, (483, 358, 38, 62))  # Radiation box

        # Icons
        self.image.blit(pygame.image.load('images/stats/gun.png').convert_alpha(), (210, 374))
        self.image.blit(pygame.image.load('images/stats/reticle.png').convert_alpha(), (284, 363))
        self.image.blit(pygame.image.load('images/stats/helmet.png').convert_alpha(), (338, 373))
        self.image.blit(pygame.image.load('images/stats/shield.png').convert_alpha(), (410, 362))
        self.image.blit(pygame.image.load('images/stats/bolt.png').convert_alpha(), (453, 362))
        self.image.blit(pygame.image.load('images/stats/radiation.png').convert_alpha(), (491, 363))

        # Health Bars
        pygame.draw.line(self.image, settings.bright, (344, 32), (379, 32), 9)
        pygame.draw.line(self.image, settings.bright, (465, 134), (500, 134), 9)
        pygame.draw.line(self.image, settings.bright, (465, 266), (500, 266), 9)
        pygame.draw.line(self.image, settings.bright, (344, 318), (379, 318), 9)
        pygame.draw.line(self.image, settings.bright, (216, 266), (251, 266), 9)
        pygame.draw.line(self.image, settings.bright, (216, 134), (251, 134), 9)

        # Stat text
        settings.FreeRobotoB[24].render_to(self.image, (281, 395), "18", settings.bright)  # Ammo count
        settings.FreeRobotoB[24].render_to(self.image, (406, 395), "10", settings.bright)  # Armor count
        settings.FreeRobotoB[24].render_to(self.image, (447, 395), "20", settings.bright)  # Energy count
        settings.FreeRobotoB[24].render_to(self.image, (490, 395), "10", settings.bright)  # Rad count
        #
        # # Bottom text
        # settings.FreeRobotoB[30].render_to(self.image, (7, 509), "HP 115/115", settings.bright)
        # settings.FreeRobotoB[24].render_to(self.image, (188, 513), "LEVEL 66", settings.bright)
        # settings.FreeRobotoB[30].render_to(self.image, (602, 509), "AP 90/90", settings.bright)

        # User name
        settings.FreeRobotoB[24].render_to(self.image, (301, 448), settings.name, settings.bright)

    # def handle_resume(self):
    #     pass
    #     super(Module, self).handle_resume()
