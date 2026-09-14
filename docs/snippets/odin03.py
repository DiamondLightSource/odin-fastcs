from pathlib import Path

from fastcs.attributes import AttrRW
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from fastcs.datatypes import Int
from fastcs.transports.epics import EpicsGUIOptions
from fastcs.transports.epics.ca.transport import EpicsCAOptions, EpicsCATransport


class ExampleOdinController(Controller):
    foo = AttrRW(Int())


controller = ExampleOdinController()
controller.set_path(["EXAMPLE"])

fastcs = FastCS(
    ExampleOdinController(),
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
