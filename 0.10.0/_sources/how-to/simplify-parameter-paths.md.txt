# Simplify Parameter Paths with `set_path`

When fastcs-odin introspects an Odin server it walks the full JSON parameter tree and
builds an [`OdinParameter`](../../src/fastcs_odin/util.py) for every leaf, using the
complete path from the tree root as its URI.  That URI becomes the attribute name on the
fastcs controller (segments joined with `_`), which is often long and redundant once the
parameter is already scoped inside a sub-controller.

`set_path` allows the URI-derived name to be replaced with a shorter, tidier path.

## Background: how names are derived

| Field | Description |
|-------|-------------|
| `uri` | List of path segments used to construct HTTP requests to the Odin server |
| `path` | List of strings representing position within the parameter tree (initially derived from `uri`; overridden by `set_path`) |
| `name` | `"_".join(path)` — becomes the fastcs attribute name |

`set_path(path)` writes `_path` directly; the `path` property returns it in preference to
`uri`.

## When to call `set_path`

`set_path` should be called inside `initialise()` of an `OdinSubController` subclass,
**before** `add_attribute(parameter.name, ...)` is called.  At that point the
controller's own position in the hierarchy is known, so the parts of the path already
captured by that position can be removed.

## Common patterns

### Strip a leading index added by `ControllerVector`

`OdinDataAdapterController` is a `ControllerVector`.  During `initialise()` it groups
parameters by their leading integer index, creates a sub-controller for each index, and
stores it at `self[int(idx)]`.  `ControllerVector` automatically incorporates that index
into the sub-controller's path hierarchy, so the index in the parameter URI is now
redundant.  Strip it inside the sub-controller before creating attributes:

```python
async def initialise(self):
    for parameter in self.parameters:
        parameter.uri = parameter.uri[1:]          # ["0", "status", "hdf", "frames"] → ["status", "hdf", "frames"]
        parameter.set_path(parameter.uri[1:])      # also strip "status"/"config"
        #                                          # path: ["hdf", "frames"]
        #                                          # name: "hdf_frames"
        self.add_attribute(
            parameter.name,
            create_attribute(parameter=parameter, api_prefix=self._api_prefix),
        )
```

> **Note:** `parameter.uri` is also updated here so that any sub-controllers created
> afterwards receive a URI that no longer contains the stale index.

### Strip a status/config wrapper

Controllers sitting directly under a `status` or `config` node can remove that prefix.
`MetaWriterAdapterController` drops both the leading index and the `status`/`config`
segment in one step using a pattern match:

```python
async def initialise(self):
    for parameter in self.parameters:
        match parameter.uri:
            case ["0", "status" | "config", *_]:
                parameter.set_path(parameter.path[2:])
                # uri:  ["0", "status", "timestamp"]
                # path: ["timestamp"]
                # name: "timestamp"
```

### Strip the plugin name in a plugin sub-controller

When a `FrameProcessorPluginController` is created it receives parameters that already
have the leading `status`/`config` stripped, but still begin with the plugin name (`hdf`,
`blosc`, …).  Since the controller *is* that plugin, the name is redundant:

```python
async def initialise(self):
    for parameter in self.parameters:
        parameter.set_path(parameter.path[1:])   # remove leading plugin name
        # path before: ["hdf", "frames_written"]
        # path after:  ["frames_written"]
        # name:        "frames_written"
```

### Rename to resolve a clash

Sometimes two URIs would produce the same name after stripping, or the auto-generated
name conflicts with an existing hand-written attribute.  `set_path` can assign a unique,
descriptive name:

```python
if parameter.uri == ["status", "hdf", "file_path"]:
    parameter.set_path(["current_file_path"])

elif parameter.uri == ["status", "hdf", "acquisition_id"]:
    parameter.set_path(["current_acquisition_id"])
```

### Strip a fixed prefix for deeply nested parameters

For parameters nested several levels deep where the first N segments are always the same,
slicing by index removes the redundant prefix.  `FrameProcessorDatasetController` only
ever sees dataset parameters, so the `status/hdf/dataset` prefix carries no information:

```python
async def initialise(self):
    for parameter in self.parameters:
        # uri: ["status", "hdf", "dataset", "raw", "compression"]
        parameter.set_path(parameter.uri[3:])
        # path: ["raw", "compression"]
        # name: "raw_compression"
```

## What does *not* change

`set_path` only affects `OdinParameter.name`, which is used as the Python attribute name
on the controller and as the PV suffix in EPICS.  It has **no effect** on how the
parameter is read or written: HTTP request paths are always derived from `parameter.uri`
(and the `api_prefix` passed to `create_attribute`), not from `path`.
