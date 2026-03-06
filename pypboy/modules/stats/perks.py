import pypboy
import pygame
import game
import settings


class Module(pypboy.SubModule):

    label = "PERKS"

    def __init__(self, *args, **kwargs):
        super(Module, self).__init__(*args, **kwargs)

        self.topmenu = pypboy.ui.TopMenu()
        self.add(self.topmenu)

        self.topmenu.label = "STAT"
        self.topmenu.title = settings.MODULE_TEXT

        self.menu = pypboy.ui.Menu(settings.PERKS)
        self.menu.rect[0] = settings.menu_x
        self.menu.rect[1] = settings.menu_y
        self.add(self.menu)

        self.configure_footer(settings.STATUS_FOOTER)
