from pathlib import Path

from fastcs.attributes import AttrRW
from fastcs.connections import IPConnectionSettings
from fastcs.control_system import FastCS
from fastcs.datatypes import Int, String
from fastcs.transports.epics import EpicsCAOptions, EpicsGUIOptions
from fastcs.transports.epics.ca.transport import EpicsCATransport

from fastcs_odin.controllers import OdinController, OdinControllerSettings
from fastcs_odin.io.config_fan_sender_attribute_io import ConfigFanAttributeIORef


class ExampleOdinController(OdinController):
    async def initialise(self):
        await super().initialise()

        self.file_path = AttrRW(
            String(),
            io_ref=ConfigFanAttributeIORef([self.FP.file_path]),
        )
        self.file_prefix = AttrRW(
            String(),
            io_ref=ConfigFanAttributeIORef([self.FP.file_prefix]),
        )
        self.frames = AttrRW(
            Int(),
            io_ref=ConfigFanAttributeIORef(
                [self.FP.frames, self.DETECTOR.config_frames]
            ),
        )


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
                output_dir=Path.cwd() / "opis" / "example.bob",
                title="Odin Example Detector",
            ),
        )
    ],
)

if __name__ == "__main__":
    fastcs.run()
