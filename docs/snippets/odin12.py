from io import BytesIO
from pathlib import Path

import numpy as np
from fastcs.attributes import AttrR, AttrRW
from fastcs.connections import IPConnectionSettings
from fastcs.control_system import FastCS
from fastcs.controllers import BaseController
from fastcs.datatypes import Bool, Int, String, Waveform
from fastcs.logging import LogLevel, configure_logging, logger
from fastcs.methods import Command, command, scan
from fastcs.transports.epics import EpicsCAOptions, EpicsGUIOptions
from fastcs.transports.epics.ca.transport import EpicsCATransport
from PIL import Image

from fastcs_odin.controllers import OdinController, OdinControllerSettings
from fastcs_odin.controllers.odin_adapter_controller import OdinAdapterController
from fastcs_odin.controllers.odin_data.frame_processor import (
    FrameProcessorAdapterController,
)
from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.io.config_fan_sender_attribute_io import ConfigFanAttributeIORef
from fastcs_odin.io.status_summary_attribute_io import StatusSummaryAttributeIORef
from fastcs_odin.util import OdinParameter


class ExampleFrameProcessorAdapterController(FrameProcessorAdapterController):
    frames: AttrRW[int]


class ExampleDetectorAdapterController(OdinAdapterController):
    config_frames: AttrRW[int]

    status_acquiring: AttrR[bool]
    status_frames: AttrR[int]

    start: Command
    stop: Command


class ExampleOdinController(OdinController):
    FP: ExampleFrameProcessorAdapterController
    DETECTOR: ExampleDetectorAdapterController

    live_view_image = AttrR(Waveform("uint8", shape=(256, 256)))

    @scan(1)
    async def monitor_live_view(self):
        response, image_bytes = await self.connection.get_bytes(
            f"{self.API_PREFIX}/live/image"
        )

        if response.status != 200:
            return

        image = Image.open(BytesIO(image_bytes))
        numpy_array = np.asarray(image)
        await self.live_view_image.update(numpy_array[:, :, 0])

    @command()
    async def acquire(self):
        logger.info("Starting writing")
        await self.FP.start_writing()
        await self.FP.writing.wait_for_value(True, timeout=1)

        await self.DETECTOR.start()

    @command()
    async def stop(self):
        logger.info("Stopping writing")
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

        self.acquiring = AttrR(
            Bool(),
            io_ref=StatusSummaryAttributeIORef(
                [], "", any, [self.FP.writing, self.DETECTOR.status_acquiring]
            ),
        )
        self.frames_captured = AttrR(
            Int(),
            io_ref=StatusSummaryAttributeIORef(
                [], "", min, [self.DETECTOR.status_frames, self.FP.frames_written]
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


configure_logging(LogLevel.TRACE)

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
