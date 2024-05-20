from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar


def is_metadata_object(v: Any) -> bool:
    return isinstance(v, dict) and "writeable" in v and "type" in v


@dataclass
class OdinParameter:
    uri: list[str]
    """Full URI."""
    metadata: dict[str, Any]
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
        metadata: JSON metadata from Odin server

    Returns":
        List of ``OdinParameter``

    """
    return [
        OdinParameter(uri=uri, metadata=metadata)
        for uri, metadata in _walk_odin_metadata(metadata, [])
    ]


def _walk_odin_metadata(
    tree: Mapping[str, Any], path: list[str]
) -> Iterator[tuple[list[str], dict[str, Any]]]:
    """Walk through tree and yield the leaves and their paths.

    Args:
        tree: Tree to walk
        path: Path down tree so far

    Returns:
        (path to leaf, value of leaf)

    """
    for node_name, node_value in tree.items():
        node_path = path + [node_name]

        if isinstance(node_value, dict) and not is_metadata_object(node_value):
            yield from _walk_odin_metadata(node_value, node_path)
        elif isinstance(node_value, list) and all(
            isinstance(m, dict) for m in node_value
        ):
            for idx, sub_node in enumerate(node_value):
                sub_node_path = node_path + [str(idx)]
                yield from _walk_odin_metadata(sub_node, sub_node_path)
        else:
            # Leaves
            if isinstance(node_value, dict) and is_metadata_object(node_value):
                yield (node_path, node_value)
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


def infer_metadata(parameter: Any, uri: list[str]):
    """Create metadata for a parameter from its type and URI.

    Args:
        parameter: Value of parameter to create metadata for
        uri: URI of parameter in API

    """
    return {
        "value": parameter,
        "type": type(parameter).__name__,
        "writeable": "config" in uri,
    }


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
