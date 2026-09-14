from fastcs.launch import launch

from fastcs_odin import __version__

from .controllers.odin_controller import OdinController

launch(controller_classes=[OdinController], version=__version__)
