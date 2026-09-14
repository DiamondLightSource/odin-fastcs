from dataclasses import dataclass

from fastcs.attributes import AttributeIO
from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.controllers import BaseController, Controller

from fastcs_odin.controllers.odin_adapter_controller import OdinAdapterController
from fastcs_odin.controllers.odin_data.frame_processor import (
    FrameProcessorAdapterController,
)
from fastcs_odin.controllers.odin_data.frame_receiver import (
    FrameReceiverAdapterController,
)
from fastcs_odin.controllers.odin_data.meta_writer import MetaWriterAdapterController
from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.io.config_fan_sender_attribute_io import ConfigFanAttributeIO
from fastcs_odin.io.parameter_attribute_io import ParameterTreeAttributeIO
from fastcs_odin.io.status_summary_attribute_io import (
    StatusSummaryAttributeIO,
    initialise_summary_attributes,
)
from fastcs_odin.util import (
    REQUEST_METADATA_HEADER,
    AdapterType,
    OdinParameter,
    create_odin_parameters,
)


@dataclass
class OdinControllerSettings:
    connection_settings: IPConnectionSettings


class OdinController(Controller):
    """A root ``Controller`` for an odin control server."""

    API_PREFIX = "api/0.1"

    def __init__(self, settings: OdinControllerSettings) -> None:
        self.connection = HTTPConnection(
            settings.connection_settings.ip, settings.connection_settings.port
        )
        self._ios: list[AttributeIO] = [
            ParameterTreeAttributeIO(self.connection),
            StatusSummaryAttributeIO(),
            ConfigFanAttributeIO(),
        ]

        super().__init__(ios=self._ios)

    async def initialise(self) -> None:
        self.connection.open()

        adapters_response = await self.connection.get(f"{self.API_PREFIX}/adapters")
        match adapters_response:
            case {"adapters": [*adapter_list]}:
                adapters = tuple(a for a in adapter_list if isinstance(a, str))
                if len(adapters) != len(adapter_list):
                    raise ValueError(f"Received invalid adapters list:\n{adapter_list}")
            case _:
                raise ValueError(
                    f"Did not find valid adapters in response:\n{adapters_response}"
                )

        for adapter in adapters:
            # Get full parameter tree and split into parameters at the root and under
            # an index where there are N identical trees for each underlying process
            response = await self.connection.get(
                f"{self.API_PREFIX}/{adapter}", headers=REQUEST_METADATA_HEADER
            )
            # Extract the module name of the adapter
            match response:
                case {"module": {"value": str() as module}}:
                    pass
                case _:
                    module = ""

            adapter_controller = self._create_adapter_controller(
                self.connection, create_odin_parameters(response), adapter, module
            )
            if len(adapter) < 3:
                adapter = adapter.upper()
            self.add_sub_controller(adapter, adapter_controller)
            await adapter_controller.initialise()

        initialise_summary_attributes(self)

    def _create_adapter_controller(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        adapter: str,
        module: str,
    ) -> BaseController:
        """Create a sub controller for an adapter in an odin control server."""

        match module:
            case AdapterType.FRAME_PROCESSOR:
                return FrameProcessorAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}", self._ios
                )
            case AdapterType.FRAME_RECEIVER:
                return FrameReceiverAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}", self._ios
                )
            case AdapterType.META_WRITER:
                return MetaWriterAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}", self._ios
                )
            case _:
                return OdinAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}", self._ios
                )
