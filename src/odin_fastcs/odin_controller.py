import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from fastcs.attributes import AttrR, AttrRW, AttrW, Handler
from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.controller import Controller
from fastcs.datatypes import Bool, Float, Int, String

from odin_fastcs.http_connection import HTTPConnection
from odin_fastcs.util import (
    create_odin_parameters,
    get_by_path,
    tag_key_clashes,
)

types = {"float": Float(), "int": Int(), "bool": Bool(), "str": String()}

REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}


class AdapterResponseError(Exception): ...


@dataclass
class ParamTreeHandler(Handler):
    path: str
    update_period: float = 0.2
    allowed_values: dict[int, str] | None = None

    async def put(
        self,
        controller: Any,
        attr: AttrW[Any],
        value: Any,
    ) -> None:
        try:
            response = await controller._connection.put(self.path, value)
            if "error" in response:
                raise AdapterResponseError(response["error"])
        except Exception as e:
            logging.error("Update loop failed for %s:\n%s", self.path, e)

    async def update(
        self,
        controller: Any,
        attr: AttrR[Any],
    ) -> None:
        try:
            response = await controller._connection.get(self.path)
            # TODO: Don't like this...
            value = response[self.path.split("/")[-1]]
            await attr.set(value)
        except Exception as e:
            logging.error("Update loop failed for %s:\n%s", self.path, e)


@dataclass
class OdinConfigurationHandler(Handler):
    path: str
    update_period: float = 0.2

    async def update(self, controller: Any, attr: AttrR[Any]) -> None:
        try:
            value = get_by_path(controller._cached_config_params, self.path)
            await attr.set(value)
        except Exception as e:
            logging.error("Update loop failed for %s:\n%s", self.path, e)


class OdinController(Controller):

    def __init__(
        self,
        settings: IPConnectionSettings,
        api_prefix: str,
        process_prefix: str,
        param_tree: bool = False,
        process_params: bool = False,
    ):
        super().__init__()
        self._ip_settings = settings
        self._api_prefix = api_prefix
        self._process_prefix = process_prefix
        self._path = process_prefix
        self._cached_config_params: dict[str, Any] = {}
        # used to determine if we need to connect the param tree or C++ params
        self._has_param_tree = param_tree
        self._has_process_params = process_params
        asyncio.run(self.initialise())

    async def initialise(self) -> None:
        self._connection = HTTPConnection(self._ip_settings.ip, self._ip_settings.port)
        self._connection.open()
        if self._has_param_tree:
            await self._connect_parameter_tree()
        if self._has_process_params:
            await self._connect_process_params()  # this will fail with merlin
        await self._connection.close()

    async def connect(self) -> None:
        for controller in self.get_sub_controllers():
            if isinstance(controller, OdinController):  # to satisfy mypy
                await controller.connect()
        self._connection.open()

    async def _connect_parameter_tree(self):
        response = await self._connection.get(
            self._api_prefix, headers=REQUEST_METADATA_HEADER
        )

        parameters = create_odin_parameters(response)
        tag_key_clashes(parameters)

        for parameter in parameters:
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
            attr = attr_class(
                types[parameter.metadata["type"]],
                handler=ParamTreeHandler(
                    f"{self._api_prefix}/{parameter.uri}", allowed_values=allowed
                ),
                group=(
                    f"{parameter.mode.capitalize()}{parameter.subsystem.capitalize()}"
                ),
            )

            setattr(self, parameter.name.replace(".", ""), attr)


class OdinTopController(Controller):
    """
    Connects all sub controllers on connect
    """

    async def connect(self) -> None:
        for controller in self.get_sub_controllers():
            if isinstance(controller, Controller):  # to satisfy mypy
                await controller.connect()


class FPOdinController(OdinController):
    def __init__(self, settings: IPConnectionSettings, api: str = "0.1"):
        super().__init__(
            settings, f"api/{api}/fp", "FP", param_tree=True, process_params=False
        )


class FROdinController(OdinController):
    def __init__(self, settings: IPConnectionSettings, api: str = "0.1"):
        super().__init__(
            settings, f"api/{api}/fr", "FR", param_tree=True, process_params=True
        )


class MLOdinController(OdinController):
    def __init__(self, settings: IPConnectionSettings, api: str = "0.1"):
        super().__init__(
            settings,
            f"api/{api}/meta_listener",
            "ML",
            param_tree=True,
            process_params=False,
        )


class OdinDetectorController(OdinController):
    def __init__(
        self, adapter_name: str, settings: IPConnectionSettings, api: str = "0.1"
    ):
        super().__init__(
            settings,
            f"api/{api}/{adapter_name}",
            adapter_name.capitalize(),
            param_tree=True,
            process_params=False,
        )
