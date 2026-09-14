from pathlib import Path

from fastcs.attributes import AttrRW
from fastcs.connections import IPConnectionSettings
from fastcs.control_system import FastCS
from fastcs.datatypes import Int
from fastcs.transports.epics import EpicsGUIOptions
from fastcs.transports.epics.ca.transport import EpicsCAOptions, EpicsCATransport

from fastcs_odin.controllers import OdinController, OdinControllerSettings


class ExampleOdinController(OdinController):
    foo = AttrRW(Int())


controller = ExampleOdinController(
    OdinControllerSettings(IPConnectionSettings("127.0.0.1", 8888))
)
controller.set_path(["EXAMPLE"])

fastcs = FastCS(
    controller,
    [
        EpicsCATransport(
            EpicsCAOptions(),
            gui=EpicsGUIOptions(
                output_dir=Path.cwd() / "opis",
                title="Odin Example Detector",
            ),
        )
    ],
)

if __name__ == "__main__":
    fastcs.run()
