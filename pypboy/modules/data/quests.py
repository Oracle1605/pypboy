import pypboy
import settings


class Module(pypboy.SubModule):

    label = "QUESTS"

    def __init__(self, *args, **kwargs):
        super(Module, self).__init__(*args, **kwargs)

        self.menu = pypboy.ui.Menu(settings.QUESTS)
        self.menu.rect[0] = settings.menu_x
        self.menu.rect[1] = settings.menu_y
        self.add(self.menu)

        self.topmenu = pypboy.ui.TopMenu()
        self.add(self.topmenu)
        self.topmenu.label = "DATA"
        self.topmenu.title = settings.MODULE_TEXT

        settings.FOOTER_TIME[2] = ""
        self.configure_footer(settings.FOOTER_TIME)
