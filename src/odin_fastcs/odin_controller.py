import asyncio
import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from fastcs.attributes import AttrR, AttrRW, AttrW, Handler, Sender, Updater
from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.controller import BaseController, Controller, SubController
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
UNIQUE_FP_CONFIG = [
    "rank",
    "number",
    "ctrl_endpoint",
    "meta_endpoint",
    "fr_ready_cnxn",
    "fr_release_cnxn",
]


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
            logging.error("Put %s = %s failed:\n%s", self.path, value, e)

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


T = TypeVar("T")


@dataclass
class StatusSummaryUpdater(Updater):
    path_filter: list[str | re.Pattern]
    parameter: str
    accumulator: Callable[[Iterable[T]], T]
    update_period: float = 0.2

    async def update(self, controller: "OdinSubController", attr: AttrR):
        values = []
        for sub_controller in filter_sub_controllers(controller, self.path_filter):
            sub_attribute: AttrR = getattr(sub_controller, self.parameter)
            values.append(sub_attribute.get())

        await attr.set(self.accumulator(values))


@dataclass
class ConfigFanSender(Sender):
    """Handler to fan out puts to underlying Attributes."""

    attributes: list[AttrW]

    async def put(self, _controller: "OdinSubController", attr: AttrW, value: Any):
        for attribute in self.attributes:
            await attribute.process(value)

        if isinstance(attr, AttrRW):
            await attr.set(value)


def filter_sub_controllers(
    controller: BaseController, path_filter: Sequence[str | tuple[str] | re.Pattern]
) -> Iterable[SubController]:
    sub_controller_map = controller.get_sub_controllers()

    if len(path_filter) == 1:
        yield sub_controller_map[path_filter[0]]
        return

    step = path_filter[0]
    match step:
        case str() as key:
            if key not in sub_controller_map:
                raise ValueError(f"SubController {key} not found in {controller}")

            sub_controllers = (sub_controller_map[key],)
        case tuple() as keys:
            for key in keys:
                if key not in sub_controller_map:
                    raise ValueError(f"SubController {key} not found in {controller}")

            sub_controllers = tuple(sub_controller_map[k] for k in keys)
        case pattern:
            sub_controllers = tuple(
                sub_controller_map[k]
                for k in sub_controller_map.keys()
                if pattern.match(k)
            )

    for sub_controller in sub_controllers:
        yield from filter_sub_controllers(sub_controller, path_filter[1:])


class OdinSubController(SubController):
    def __init__(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        api_prefix: str,
    ):
        """A ``SubController`` for a subsystem in an Odin control server.

        Args:
            connection: HTTP connection to communicate with Odin server
            parameter_tree: The parameter tree from the Odin server for this subsystem
            api_prefix: The base URL of this subsystem in the Odin server API

        """
        super().__init__()

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
    ) -> OdinSubController:
        """Create an ``OdinSubController`` for an adapter in an Odin control server."""

        match adapter:
            # TODO: May not be called "fp", it is configurable in the server
            case "fp":
                return OdinFPAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/fp"
                )
            case _:
                return OdinSubController(
                    connection,
                    parameters,
                    f"{self.API_PREFIX}/{adapter}",
                )

    async def connect(self) -> None:
        self._connection.open()


class OdinFPAdapterController(OdinSubController):
    frames_written: AttrR = AttrR(
        Int(),
        handler=StatusSummaryUpdater([re.compile("FP*"), "HDF"], "frames_written", sum),
    )
    writing: AttrR = AttrR(
        Bool(),
        handler=StatusSummaryUpdater([re.compile("FP*"), "HDF"], "writing", any),
    )

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
            )
            self.register_sub_controller(f"FP{idx}", adapter_controller)
            await adapter_controller.initialise()

        self._create_attributes()
        self._create_config_fan_attributes()

    def _create_config_fan_attributes(self):
        """Search for config attributes in sub controllers to create fan out PVs."""
        parameter_attribute_map: dict[str, tuple[OdinParameter, list[AttrW]]] = {}
        for sub_controller in get_all_sub_controllers(self):
            for parameter in sub_controller._parameters:
                mode, key = parameter.uri[0], parameter.uri[-1]
                if mode == "config" and key not in UNIQUE_FP_CONFIG:
                    try:
                        attr = getattr(sub_controller, parameter.name)
                    except AttributeError:
                        print(
                            f"Controller has parameter {parameter}, "
                            f"but no corresponding attribute {parameter.name}"
                        )

                    if parameter.name not in parameter_attribute_map:
                        parameter_attribute_map[parameter.name] = (parameter, [attr])
                    else:
                        parameter_attribute_map[parameter.name][1].append(attr)

        for parameter, sub_attributes in parameter_attribute_map.values():
            setattr(
                self,
                parameter.name,
                sub_attributes[0].__class__(
                    sub_attributes[0]._datatype,
                    group=sub_attributes[0].group,
                    handler=ConfigFanSender(sub_attributes),
                ),
            )


def get_all_sub_controllers(
    controller: "OdinSubController",
) -> list["OdinSubController"]:
    return list(_walk_sub_controllers(controller))


def _walk_sub_controllers(controller: BaseController) -> Iterable[SubController]:
    for sub_controller in controller.get_sub_controllers().values():
        yield sub_controller
        yield from _walk_sub_controllers(sub_controller)


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
            )
            self.register_sub_controller(plugin.upper(), plugin_controller)
            await plugin_controller.initialise()


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
        )
