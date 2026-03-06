import cairosvg
import pygame
import pypboy
import settings
import requests
import game
import threading
import io
import numpy as np
import urllib
import os

# def load_svg(filename, width, height):
#     drawing = cairosvg.svg2png(url = filename)
#     byte_io = io.BytesIO(drawing)
#     image = pygame.image.load(byte_io).convert_alpha()
#     size = image.get_size()
#     scale = min(width / size[0], height / size[1])
#     if size[1] != height:
#         image = pygame.transform.smoothscale(image, (round(size[0] * scale), round(size[1] * scale)))
#     image.fill((0,230,0), None, pygame.BLEND_RGBA_MULT)
#     return image

class Module(pypboy.SubModule):
    label = "LOCAL MAP"
    zoom = settings.LOCAL_MAP_ZOOM
    map_top_edge = 128
    map_type = settings.MAP_TYPE
    map_width = 720
    map_height = 545
    map_rect = pygame.Rect(0, (map_width - 720) / 2, map_width, map_height - 45)

    def __init__(self, *args, **kwargs):
        super(Module, self).__init__(*args, **kwargs)
        # self.mapgrid = Map(self.map_width,self.map_height)

        if (settings.LOAD_CACHED_MAP):
            print("Loading cached map")
            self.mapgrid = Map(self.map_width,self.map_height,self.map_rect, "Loading cached map")
            self.mapgrid.load_map(settings.MAP_FOCUS, self.zoom, self.map_width, self.map_height, self.map_type)
        else:
            print("Loading map from the internet")
            self.mapgrid = Map(self.map_width,self.map_height,self.map_rect, "Loading map from the internet")
            self.mapgrid.fetch_map(settings.MAP_FOCUS, self.zoom, self.map_width, self.map_height, self.map_type)

        self.add(self.mapgrid)
        self.mapgrid.rect[0] = 0
        self.mapgrid.rect[1] = self.map_top_edge

        self.topmenu = pypboy.ui.TopMenu()
        self.add(self.topmenu)
        self.topmenu.label = "MAP"
        self.topmenu.title = settings.MODULE_TEXT


        settings.FOOTER_TIME[2] = "Map Data © Google"
        self.configure_footer(settings.FOOTER_TIME)

    def handle_action(self, action, value=0):
        if action == "zoom_in":
            self.zoomMap(1)
        if action == "zoom_out":
            self.zoomMap(-1)

    # def handle_resume(self):
    #     super(Module, self).handle_resume()

    def zoomMap(self, zoomFactor):
        self.zoom = self.zoom + zoomFactor
        if settings.LOAD_CACHED_MAP:
            print("Loading cached map")
            self.mapgrid.load_map(settings.MAP_FOCUS, self.zoom, self.map_width, self.map_height, self.map_type)
        else:
            print("Loading map from the internet")
            self.mapgrid.fetch_map(settings.MAP_FOCUS, self.zoom, self.map_width, self.map_height, self.map_type)

        self.add(self.mapgrid)
        self.mapgrid.rect[0] = 0
        self.mapgrid.rect[1] = self.map_top_edge

class Map(game.Entity):
    _size = 0
    _fetching = None
    _map_surface = None
    _loading_size = 0
    _render_rect = None

    def __init__(self, width, height, render_rect=None, loading_type="Loading map...", *args, **kwargs):
        super(Map, self).__init__((width, height), *args, **kwargs)
        self._size = width
        self._map_surface = pygame.Surface((width, height))
        self._render_rect = render_rect
        self._cache_file = os.path.join(settings.ROOT_DIR, "localMap.cache")
        self._last_request = None
        self._player_marker = pygame.image.load(
            os.path.join(settings.ROOT_DIR, "images", "map_icons", "Player_Marker.svg")
        ).convert_alpha()
        self._player_marker.fill(settings.bright, None, pygame.BLEND_RGBA_MULT)
        text = settings.RobotoB[14].render(loading_type, True, settings.bright, (0, 0, 0))
        self.image.blit(text, (10, 10))

    def fetch_map(self, position, zoom, width, height, map_type):
        self._last_request = (position, zoom, width, height, map_type)
        self._fetching = threading.Thread(
            target=self._internal_fetch_map,
            args=(position, zoom, width, height, map_type),
            daemon=True,
        )
        self._fetching.start()

    def _internal_fetch_map(self, position, zoom, width, height, map_type):
        map_image = None
        lat = str(position[0])
        long = str(position[1])
        url = ("https://maps.googleapis.com/maps/api/staticmap?center=" + long + "," + lat +
               "&zoom=" + str(zoom) + "&size="
               + str(int(width/2)) + "x" + str(int(height/2))
               + "&scale=2"
               # + "&maptype=" + str(map_type)
               # + "&style=" + str(settings.MAP_STYLE)
               #+ "&markers=color:blue%7Clabel:S%7C40.702147,-74.015794" +
               #+ "&markers=color:green%7Clabel:G%7C40.711614,-74.012318" +
               #+  "&markers=color:red%7Clabel:C%7C40.718217,-73.998284" +
               + "&key=AIzaSyBGLrr7j1P_pMknv1vRbKD4X7xMScWxnzM"
               + "&map_id=f1a13570cd60f576"

               )
                # Note the API string here is restricted you will need your own API string

        print("Loading map image from:" + url)

        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            map_image = io.BytesIO(r.content)
            with open(self._cache_file, "wb") as cache_file:
                cache_file.write(r.content)
        except Exception as exc:
            print("Failed to load map image:", exc)
        if map_image:
            map_surf = pygame.image.load(map_image).convert()  # byte image to -> Surface

            arr = pygame.surfarray.pixels3d(map_surf)
            mean_arr = np.dot(arr[:, :, :], [0.216, 0.587, 0.144])
            mean_arr3d = mean_arr[..., np.newaxis]
            new_arr = np.repeat(mean_arr3d[:, :, :], 3, axis=2)
            map_surf = pygame.surfarray.make_surface(new_arr.astype(np.uint8))

            map_surf.fill((0, 230, 0), None, pygame.BLEND_RGBA_MULT)
            self._map_surface.blit(map_surf, (0, 0))

            self._map_surface.blit(self._player_marker, (settings.WIDTH / 2 - 20, self._render_rect.centery - 20))

        else:
            print("No map image")

        self.redraw_map()


    def load_map(self, position, zoom, width, height, map_type):
        self._last_request = (position, zoom, width, height, map_type)
        self._fetching = threading.Thread(target=self._internal_load_map, daemon=True)
        self._fetching.start()

    def _internal_load_map(self):
        try:
            with open(self._cache_file, "rb") as cache_file:
                cached_bytes = cache_file.read()
        except OSError:
            cached_bytes = None

        if cached_bytes:
            try:
                map_surf = pygame.image.load(io.BytesIO(cached_bytes)).convert()
                arr = pygame.surfarray.pixels3d(map_surf)
                mean_arr = np.dot(arr[:, :, :], [0.216, 0.587, 0.144])
                mean_arr3d = mean_arr[..., np.newaxis]
                new_arr = np.repeat(mean_arr3d[:, :, :], 3, axis=2)
                map_surf = pygame.surfarray.make_surface(new_arr.astype(np.uint8))
                map_surf.fill((0, 230, 0), None, pygame.BLEND_RGBA_MULT)
                self._map_surface.blit(map_surf, (0, 0))
                self._map_surface.blit(self._player_marker, (settings.WIDTH / 2 - 20, self._render_rect.centery - 20))
                self.redraw_map()
                return
            except pygame.error:
                # Older cache files may contain non-image map data.
                pass

        if self._last_request:
            self._internal_fetch_map(*self._last_request)

    def move_map(self, x, y):
        self._render_rect.move_ip(x, y)

    def redraw_map(self, coef=1):
        self.image.fill((0, 0, 0))

        self.image.blit(self._map_surface, (0, 0), area=self._render_rect)
