import json
import logging
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, TypeVar

from fastcs.attributes import AttrR, AttrRW
from fastcs.controllers import BaseController
from fastcs.datatypes import Bool, DataType, Float, Int, String
from fastcs.logging import logger
from fastcs.util import snake_to_pascal
from pydantic import BaseModel, ConfigDict, ValidationError

from fastcs_odin.io.parameter_attribute_io import ParameterTreeAttributeIORef

REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}

VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def is_metadata_object(v: Any) -> bool:
    return isinstance(v, dict) and "writeable" in v and "type" in v


class AdapterType(StrEnum):
    FRAME_PROCESSOR = "FrameProcessorAdapter"
    FRAME_RECEIVER = "FrameReceiverAdapter"
    META_WRITER = "MetaListenerAdapter"


class OdinParameterMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any
    name: str = ""
    description: str = ""
    units: str = ""
    display_precision: int = 0
    writeable: bool
    type: Literal["float", "int", "bool", "str"]
    allowed_values: dict[int, str] | None = None

    @property
    def fastcs_datatype(self) -> DataType:
        match self.type:
            case "float":
                return Float()
            case "int":
                return Int()
            case "bool":
                return Bool()
            case "str":
                return String()


class AllowedCommandsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: list[str]


@dataclass
class OdinParameter:
    uri: list[str]
    """Full URI."""
    metadata: OdinParameterMetadata
    """JSON response from GET of parameter."""

    _path: list[str] = field(default_factory=list)

    @property
    def path(self) -> list[str]:
        """Reduced path of parameter to override uri when constructing name."""
        return self._path or self.uri

    @property
    def name(self) -> str:
        """Unique name of parameter."""
        return "_".join(self.path)

    def set_path(self, path: list[str]):
        """Set reduced path of parameter to override uri when constructing name."""
        self._path = path


def create_odin_parameters(metadata: Mapping[str, Any]) -> list[OdinParameter]:
    """Walk metadata and create parameters for the leaves, flattening path with '/'s.

    Args:
        metadata: JSON metadata from odin server

    Returns":
        List of ``OdinParameter``

    """
    return [
        OdinParameter(uri=uri, metadata=metadata)
        for uri, metadata in _walk_odin_metadata(metadata, [])
    ]


def _walk_odin_metadata(
    tree: Mapping[str, Any], path: list[str]
) -> Iterator[tuple[list[str], OdinParameterMetadata]]:
    """Walk through tree and yield the leaves and their paths.

    Args:
        tree: Tree to walk
        path: Path down tree so far

    Returns:
        (path to leaf, value of leaf)

    """
    for node_name, node_value in tree.items():
        node_path = path + [node_name]

        if "command" in node_path:
            # Do not parse and yield any command attributes
            # They are handled by the individual controllers
            continue
        # Branches - dict or list[dict] to recurse through
        if isinstance(node_value, dict) and not is_metadata_object(node_value):
            yield from _walk_odin_metadata(node_value, node_path)
        elif (
            isinstance(node_value, list)
            and node_value  # Exclude parameters with an empty list as a value
            and all(isinstance(m, dict) for m in node_value)
        ):
            for idx, sub_node in enumerate(node_value):
                sub_node_path = node_path + [str(idx)]
                yield from _walk_odin_metadata(sub_node, sub_node_path)
        else:
            # Leaves
            if node_path[-1] in ("name", "description"):
                logger.warning(
                    "Ignoring parameter with name/description",
                    node=node_path,
                    value=node_value,
                )
                continue
            elif not all(VALID_NAME_RE.match(n) for n in node_path):
                logger.warning(
                    "Ignoring parameter with invalid path",
                    node=node_path,
                    value=node_value,
                )
                continue

            try:
                if isinstance(node_value, dict) and is_metadata_object(node_value):
                    yield (node_path, OdinParameterMetadata.model_validate(node_value))
                elif isinstance(node_value, list):
                    if "config" in node_path:
                        # Split list into separate parameters so they can be set
                        for idx, sub_node_value in enumerate(node_value):
                            sub_node_path = node_path + [str(idx)]
                            yield (
                                sub_node_path,
                                infer_metadata(sub_node_value, sub_node_path),
                            )
                    else:
                        # Convert read-only list to a string for display
                        yield (node_path, infer_metadata(str(node_value), node_path))

                else:
                    # TODO: This won't be needed when all parameters provide metadata
                    yield (node_path, infer_metadata(node_value, node_path))
            except ValidationError:
                logger.opt(exception=True).warning(
                    "Type not supported", path=node_path, value=node_value
                )


def infer_metadata(parameter: Any, uri: list[str]):
    """Create metadata for a parameter from its type and URI.

    Args:
        parameter: Value of parameter to create metadata for
        uri: URI of parameter in API.

    Raises:
        pydantic.ValidationError: if inferred metadata is not valid

    """
    metadata_dict = {
        "value": parameter,
        "type": type(parameter).__name__,
        "writeable": "config" in uri,
    }

    return OdinParameterMetadata.model_validate(metadata_dict)


T = TypeVar("T")


def partition(
    elements: list[T], predicate: Callable[[T], bool]
) -> tuple[list[T], list[T]]:
    """Split a list of elements in two based on predicate.

    If the predicate returns ``True``, the element will be placed in the truthy list,
    if it does not, it will be placed in the falsy list.

    Args:
        elements: List of T
        predicate: Predicate to filter the list with

    Returns:
        (truthy, falsy)

    """
    truthy: list[T] = []
    falsy: list[T] = []
    for parameter in elements:
        if predicate(parameter):
            truthy.append(parameter)
        else:
            falsy.append(parameter)

    return truthy, falsy


def get_all_sub_controllers(controller: BaseController) -> list[BaseController]:
    return list(_walk_sub_controllers(controller))


def _walk_sub_controllers(controller: BaseController) -> Iterable[BaseController]:
    for sub_controller in controller.sub_controllers.values():
        yield sub_controller
        yield from _walk_sub_controllers(sub_controller)


def unpack_status_arrays(parameters: list[OdinParameter], uris: list[list[str]]):
    """Takes a list of OdinParameters and a list of uris. Search the parameter
    for elements that match the values in the uris list and split them into one
    new OdinParameter for each value.

    Args:
        parameters: List of OdinParameters
        uris: List of uris to search and replace

    Returns:
        Original list of parameters with elements in uris replaced with
        their indexed equivalent
    """
    removelist = []
    for parameter in parameters:
        if parameter.uri in uris:
            try:
                status_list = json.loads(parameter.metadata.value.replace("'", '"'))
            except (json.JSONDecodeError, AssertionError) as e:
                logging.warning(f"Failed to parse {parameter} value as a list:\n{e}")
                continue
            for idx, value in enumerate(status_list):
                parameters.append(
                    OdinParameter(
                        uri=parameter.uri + [str(idx)],
                        metadata=OdinParameterMetadata(
                            value=value,
                            type=parameter.metadata.type,
                            writeable=parameter.metadata.writeable,
                        ),
                    )
                )
            removelist.append(parameter)

    for value in removelist:
        parameters.remove(value)

    return parameters


def create_attribute(
    parameter: OdinParameter, api_prefix: str, group: str | None = None
):
    """Create ``Attribute`` from ``OdinParameter``."""
    if parameter.metadata.writeable:
        attr_class = AttrRW
    else:
        attr_class = AttrR

    if group is None:
        if len(parameter.path) >= 2:
            group = snake_to_pascal(f"{parameter.path[0]}")

    return attr_class(
        parameter.metadata.fastcs_datatype,
        io_ref=ParameterTreeAttributeIORef(
            "/".join([api_prefix] + parameter.uri),
        ),
        group=group,
    )
