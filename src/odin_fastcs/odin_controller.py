import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fastcs.attributes import AttrR, AttrRW, AttrW, Handler
from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.controller import Controller, SubController
from fastcs.datatypes import Bool, Float, Int, String
from fastcs.util import snake_to_pascal

from odin_fastcs.http_connection import HTTPConnection
from odin_fastcs.util import (
    OdinParameter,
    create_odin_parameters,
    partition,
)

types = {"float": Float(), "int": Int(), "bool": Bool(), "str": String()}

REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}
IGNORED_ADAPTERS = ["od_fps", "od_frs", "od_mls"]


class AdapterResponseError(Exception): ...


@dataclass
class ParamTreeHandler(Handler):
    path: str
    update_period: float = 0.2
    allowed_values: dict[int, str] | None = None

    async def put(
        self,
        controller: "OdinSubController",
        attr: AttrW[Any],
        value: Any,
    ) -> None:
        try:
            response = await controller._connection.put(self.path, value)
            match response:
                case {"error": error}:
                    raise AdapterResponseError(error)
        except Exception as e:
            logging.error("Update loop failed for %s:\n%s", self.path, e)

    async def update(
        self,
        controller: "OdinSubController",
        attr: AttrR[Any],
    ) -> None:
        try:
            response = await controller._connection.get(self.path)

            # TODO: This would be nicer if the key was 'value' so we could match
            parameter = self.path.split("/")[-1]
            value = response.get(parameter, None)
            if value is None:
                raise ValueError(f"{parameter} not found in response:\n{response}")

            await attr.set(value)
        except Exception as e:
            logging.error("Update loop failed for %s:\n%s", self.path, e)


class OdinSubController(SubController):
    def __init__(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        api_prefix: str,
        path: list[str],
    ):
        """A ``SubController`` for a subsystem in an Odin control server.

        Args:
            connection: HTTP connection to communicate with Odin server
            parameter_tree: The parameter tree from the Odin server for this subsytem
            api_prefix: The base URL of this subsystem in the Odin server API
            path: ``SubController`` path

        """
        super().__init__(path)

        self._connection = connection
        self._parameters = parameters
        self._api_prefix = api_prefix

    async def initialise(self):
        self._process_parameters()
        self._create_attributes()

    def _process_parameters(self):
        """Hook to process ``OdinParameters`` before creating ``Attributes``.

        For example, renaming or removing a section of the parameter path.

        """
        pass

    def _create_attributes(self):
        """Create controller ``Attributes`` from ``OdinParameters``."""
        for parameter in self._parameters:
            if "writeable" in parameter.metadata and parameter.metadata["writeable"]:
                attr_class = AttrRW
            else:
                attr_class = AttrR

            if parameter.metadata["type"] not in types:
                logging.warning(f"Could not handle parameter {parameter}")
                # this is really something I should handle here
                continue

            allowed = (
                parameter.metadata["allowed_values"]
                if "allowed_values" in parameter.metadata
                else None
            )

            if len(parameter.path) >= 2:
                group = snake_to_pascal(f"{parameter.path[0]}")
            else:
                group = None

            attr = attr_class(
                types[parameter.metadata["type"]],
                handler=ParamTreeHandler(
                    "/".join([self._api_prefix] + parameter.uri), allowed_values=allowed
                ),
                group=group,
            )

            setattr(self, parameter.name.replace(".", ""), attr)


class OdinController(Controller):
    """A root ``Controller`` for an Odin control server."""

    API_PREFIX = "api/0.1"

    def __init__(self, settings: IPConnectionSettings) -> None:
        super().__init__()

        self._connection = HTTPConnection(settings.ip, settings.port)

        asyncio.run(self.initialise())

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
            if adapter in IGNORED_ADAPTERS:
                continue

            # Get full parameter tree and split into parameters at the root and under
            # an index where there are N identical trees for each underlying process
            response = await self._connection.get(
                f"{self.API_PREFIX}/{adapter}", headers=REQUEST_METADATA_HEADER
            )

            adapter_controller = self._create_adapter_controller(
                self._connection, create_odin_parameters(response), adapter
            )
            await adapter_controller.initialise()
            self.register_sub_controller(adapter_controller)

        await self._connection.close()

    def _create_adapter_controller(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        adapter: str,
    ) -> OdinSubController:
        """Create an ``OdinSubController`` for an adapter in an Odin control server."""

        match adapter:
            # TODO: May not be called "fp", it is configurable in the server
            case "fp":
                return OdinFPAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/fp", ["FP"]
                )
            case _:
                return OdinSubController(
                    connection,
                    parameters,
                    f"{self.API_PREFIX}/{adapter}",
                    [f"{adapter.upper()}"],
                )

    async def connect(self) -> None:
        self._connection.open()


class OdinFPAdapterController(OdinSubController):
    async def initialise(self):
        idx_parameters, self._parameters = partition(
            self._parameters, lambda p: p.uri[0].isdigit()
        )

        while idx_parameters:
            idx = idx_parameters[0].uri[0]
            fp_parameters, idx_parameters = partition(
                idx_parameters, lambda p, idx=idx: p.uri[0] == idx
            )

            adapter_controller = OdinFPController(
                self._connection,
                fp_parameters,
                f"{self._api_prefix}/{idx}",
                [f"FP{idx}"],
            )
            await adapter_controller.initialise()
            self.register_sub_controller(adapter_controller)

        self._create_attributes()


class OdinFPController(OdinSubController):
    async def initialise(self):
        plugins_response = await self._connection.get(
            f"{self._api_prefix}/status/plugins/names"
        )
        match plugins_response:
            case {"names": [*plugin_list]}:
                plugins = tuple(a for a in plugin_list if isinstance(a, str))
                if len(plugins) != len(plugin_list):
                    raise ValueError(f"Received invalid plugins list:\n{plugin_list}")
            case _:
                raise ValueError(
                    f"Did not find valid plugins in response:\n{plugins_response}"
                )

        self._process_parameters()
        await self._create_plugin_sub_controllers(plugins)
        self._create_attributes()

    def _process_parameters(self):
        for parameter in self._parameters:
            # Remove duplicate index from uri
            parameter.uri = parameter.uri[1:]
            # Remove redundant status/config from parameter path
            parameter.set_path(parameter.uri[1:])

    async def _create_plugin_sub_controllers(self, plugins: Sequence[str]):
        for plugin in plugins:

            def __parameter_in_plugin(
                parameter: OdinParameter, plugin: str = plugin
            ) -> bool:
                return parameter.path[0] == plugin

            plugin_parameters, self._parameters = partition(
                self._parameters, __parameter_in_plugin
            )
            plugin_controller = OdinFPPluginController(
                self._connection,
                plugin_parameters,
                f"{self._api_prefix}",
                self.path + [plugin.upper()],
            )
            await plugin_controller.initialise()
            self.register_sub_controller(plugin_controller)


class OdinFPPluginController(OdinSubController):
    def _process_parameters(self):
        for parameter in self._parameters:
            # Remove plugin name included in controller base path
            parameter.set_path(parameter.path[1:])


class FROdinController(OdinSubController):
    def __init__(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        api: str = "0.1",
    ):
        super().__init__(
            connection,
            parameters,
            f"api/{api}/fr",
            ["FR"],
        )


class MLOdinController(OdinSubController):
    def __init__(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        api: str = "0.1",
    ):
        super().__init__(
            connection,
            parameters,
            f"api/{api}/meta_listener",
            ["ML"],
        )
