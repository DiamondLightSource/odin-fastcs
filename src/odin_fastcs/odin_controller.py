from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.controller import Controller
from fastcs.datatypes import Bool, Float, Int, String

from odin_fastcs.eiger_fan import EigerFanAdapterController
from odin_fastcs.frame_processor import FrameProcessorAdapterController
from odin_fastcs.http_connection import HTTPConnection
from odin_fastcs.meta_writer import MetaWriterAdapterController
from odin_fastcs.odin_adapter_controller import OdinAdapterController
from odin_fastcs.util import OdinParameter, create_odin_parameters

types = {"float": Float(), "int": Int(), "bool": Bool(), "str": String()}

REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}


class AdapterResponseError(Exception): ...


class OdinController(Controller):
    """A root ``Controller`` for an odin control server."""

    API_PREFIX = "api/0.1"

    def __init__(self, settings: IPConnectionSettings) -> None:
        super().__init__()

        self._connection = HTTPConnection(settings.ip, settings.port)

    async def initialise(self) -> None:
        self._connection.open()

        adapters_response = await self._connection.get(f"{self.API_PREFIX}/adapters")
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
            response = await self._connection.get(
                f"{self.API_PREFIX}/{adapter}", headers=REQUEST_METADATA_HEADER
            )

            adapter_controller = self._create_adapter_controller(
                self._connection, create_odin_parameters(response), adapter
            )
            self.register_sub_controller(adapter.upper(), adapter_controller)
            await adapter_controller.initialise()

        await self._connection.close()

    def _create_adapter_controller(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        adapter: str,
    ) -> OdinAdapterController:
        """Create a sub controller for an adapter in an odin control server."""

        match adapter:
            # TODO: May not be called "fp", it is configurable in the server
            case "fp":
                return FrameProcessorAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/fp"
                )
            case "mw":
                return MetaWriterAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/mw"
                )
            case "ef":
                return EigerFanAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/ef"
                )
            case _:
                return OdinAdapterController(
                    connection,
                    parameters,
                    f"{self.API_PREFIX}/{adapter}",
                )

    async def connect(self) -> None:
        self._connection.open()
