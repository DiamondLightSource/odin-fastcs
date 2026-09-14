from pathlib import Path

from fastcs.attributes import AttrRW
from fastcs.connections import IPConnectionSettings
from fastcs.control_system import FastCS
from fastcs.controllers import BaseController
from fastcs.datatypes import Int, String
from fastcs.methods import Command, command
from fastcs.transports.epics import EpicsCAOptions, EpicsGUIOptions
from fastcs.transports.epics.ca.transport import EpicsCATransport

from fastcs_odin.controllers import OdinController, OdinControllerSettings
from fastcs_odin.controllers.odin_adapter_controller import OdinAdapterController
from fastcs_odin.controllers.odin_data.frame_processor import (
    FrameProcessorAdapterController,
)
from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.io.config_fan_sender_attribute_io import ConfigFanAttributeIORef
from fastcs_odin.util import OdinParameter


class ExampleFrameProcessorAdapterController(FrameProcessorAdapterController):
    frames: AttrRW[int]


class ExampleDetectorAdapterController(OdinAdapterController):
    config_frames: AttrRW[int]

    start: Command
    stop: Command


class ExampleOdinController(OdinController):
    FP: ExampleFrameProcessorAdapterController
    DETECTOR: ExampleDetectorAdapterController

    @command()
    async def acquire(self):
        await self.FP.start_writing()
        await self.DETECTOR.start()

    @command()
    async def stop(self):
        await self.FP.stop_writing()
        await self.DETECTOR.stop()

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

    def _create_adapter_controller(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        adapter: str,
        module: str,
    ) -> BaseController:
        match module:
            case "ExampleDetectorAdapter":
                return ExampleDetectorAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}", self._ios
                )
            case "FrameProcessorAdapter":
                return ExampleFrameProcessorAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}", self._ios
                )
            case _:
                return super()._create_adapter_controller(
                    connection, parameters, adapter, module
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
