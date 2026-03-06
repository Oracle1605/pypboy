import pypboy
import settings

class Module(pypboy.SubModule):

	label = "MISC"



	def __init__(self, *args, **kwargs):
		super(Module, self).__init__(*args, **kwargs)

		self.topmenu = pypboy.ui.TopMenu()
		self.add(self.topmenu)
		self.topmenu.label = "DATA"
		self.topmenu.title = settings.MODULE_TEXT

		settings.FOOTER_TIME[2] = ""
		self.configure_footer(settings.FOOTER_TIME)
