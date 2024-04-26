from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal


def is_metadata_object(v: Any) -> bool:
    return isinstance(v, dict) and "writeable" in v and "type" in v


@dataclass
class OdinParameter:
    uri: str
    """Full URI."""
    subsystem: str
    """Subsystem within detector API."""
    subsubsystem: str
    """Subsubsystem within subsystem."""
    mode: Literal["status", "config", ""]
    """Mode of parameter within subsystem."""
    metadata: dict[str, Any]
    """JSON response from GET of parameter."""
    has_unique_key: bool = True
    """Whether this parameter has a unique key across all subsystems."""

    @property
    def key(self) -> str:
        return self.uri.split("/")[-1]

    @property
    def name(self) -> str:
        """Unique name of parameter across all subsystems."""
        return (
            self.key
            if self.has_unique_key
            else f"{self.subsubsystem or self.subsystem}_{self.key}"
        )


def create_odin_parameters(metadata: Mapping[str, Any]) -> list[OdinParameter]:
    """_walk metadata and create parameters for the leaves, flattening path with '/'s.

    Args:
        metadata: JSON metadata from Odin server

    Returns":
        List of ``OdinParameter``

    """
    odin_metadata = _walk_odin_metadata(metadata)

    odin_parameters = []
    for uri, metadata in odin_metadata:
        uri_path = uri.split("/")
        odin_parameters.append(
            OdinParameter(
                uri=uri,
                mode=uri_path[1] if len(uri_path) >= 3 else "",
                # TODO: Sanitise Group name more generically
                subsystem=uri_path[2].replace("_", "") if len(uri_path) >= 4 else "",
                subsubsystem=uri_path[3] if len(uri_path) >= 5 else "",
                metadata=metadata,
            )
        )

    return odin_parameters


def _walk_odin_metadata(
    tree: dict[str, Any], prefix: str = ""
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Walk through tree and yield the leaves and their paths.

    Args:
        tree: Tree to walk
        prefix: Path so far

    Returns:
        (path to leaf, value of leaf)

    """
    for node_name, node_value in tree.items():
        node_path = "/".join((prefix, node_name)) if prefix else node_name

        if isinstance(node_value, dict) and not is_metadata_object(node_value):
            yield from _walk_odin_metadata(node_value, node_path)
        elif isinstance(node_value, list) and all(
            isinstance(m, dict) for m in node_value
        ):
            for sub_node in node_value:
                # TODO: Insert index into path?
                yield from _walk_odin_metadata(sub_node, node_path)
        else:
            if isinstance(node_value, dict):
                metadata = node_value
            else:
                # TODO: This won't be needed when all parameters provide metadata
                metadata = {
                    "value": node_value,
                    "type": type(node_value).__name__,
                    "writeable": "/status/" not in node_path,
                }

            yield (node_path, metadata)


def tag_key_clashes(parameters: list[OdinParameter]):
    """Find key clashes between subsystems and tag parameters to use extended name.

    Modifies list of parameters in place.

    Args:
        parameters: Parameters to search

    """
    for idx, parameter in enumerate(parameters):
        for other in parameters[idx + 1 :]:
            if parameter.key == other.key:
                parameter.has_unique_key = False
                other.has_unique_key = False
                break


def get_by_path(config: Mapping[str, Any], path: str, delimiter: str = "/") -> Any:
    parts = path.split("/")
    if len(parts) == 1:
        return config[parts[0]]
    elif parts[0] in config:
        return get_by_path(config[parts[0]], delimiter.join(parts[1:]))
    else:
        raise ValueError(f"Could not retrieve {parts[-1]} from mapping.")
