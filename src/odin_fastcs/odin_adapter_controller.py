import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from fastcs.attributes import AttrR, AttrRW, AttrW, Handler, Sender, Updater
from fastcs.controller import BaseController, SubController
from fastcs.datatypes import Bool, Float, Int, String
from fastcs.util import snake_to_pascal

from odin_fastcs.http_connection import HTTPConnection
from odin_fastcs.util import (
    OdinParameter,
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
        controller: "OdinAdapterController",
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
        controller: "OdinAdapterController",
        attr: AttrR[Any],
    ) -> None:
        try:
            response = await controller._connection.get(self.path)

            # TODO: This would be nicer if the key was 'value' so we could match
            parameter = self.path.split("/")[-1]
            if parameter not in response:
                raise ValueError(f"{parameter} not found in response:\n{response}")

            value = response.get(parameter)
            await attr.set(value)
        except Exception as e:
            logging.error("Update loop failed for %s:\n%s", self.path, e)


T = TypeVar("T")


@dataclass
class StatusSummaryUpdater(Updater):
    """Updater to accumulate underlying attributes into a high-level summary.

    Args:
        path_filter: A list of filters to apply to the sub controller hierarchy. This is
        used to match one or more sub controller paths under the parent controller. Each
        element can be a string or tuple of string for one or more exact matches, or a
        regular expression to match on.
        attribute_name: The name of the attribute to get from the sub controllers
        matched by `path_filter`.
        accumulator: A function that takes a sequence of values from each matched
        attribute and returns a summary value.
    """

    path_filter: list[str | tuple[str] | re.Pattern]
    attribute_name: str
    accumulator: Callable[[Iterable[T]], T]
    update_period: float = 0.2

    async def update(self, controller: "OdinAdapterController", attr: AttrR):
        values = []
        for sub_controller in _filter_sub_controllers(controller, self.path_filter):
            sub_attribute: AttrR = getattr(sub_controller, self.attribute_name)
            values.append(sub_attribute.get())

        await attr.set(self.accumulator(values))


@dataclass
class ConfigFanSender(Sender):
    """Handler to fan out puts to underlying Attributes.

    Args:
        attributes: A list of attributes to fan out to.
    """

    attributes: list[AttrW]

    async def put(self, _controller: "OdinAdapterController", attr: AttrW, value: Any):
        for attribute in self.attributes:
            await attribute.process(value)

        if isinstance(attr, AttrRW):
            await attr.set(value)


def _filter_sub_controllers(
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
        yield from _filter_sub_controllers(sub_controller, path_filter[1:])


class OdinAdapterController(SubController):
    """Base class for exposing parameters from an odin control adapter.

    Introspection should work for any odin adapter that implements its API using
    ParameterTree. To implement logic for a specific adapter, make a subclass and
    implement `_process_parameters` to modify the parameters before creating attributes
    and/or statically define additional attributes.
    """

    def __init__(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        api_prefix: str,
    ):
        """
        Args:
            connection: HTTP connection to communicate with odin server
            parameters: The parameters in the adapter
            api_prefix: The base URL of this adapter in the odin server API
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
