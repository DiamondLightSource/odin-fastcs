# Controller Architecture

fastcs-odin provides a set of controller classes that map an odin-control server's
REST API onto FastCS attributes and commands. This page explains each class and how
they relate to one another.

## `OdinController`

`OdinController` is the root FastCS `Controller` for an odin-control server. It is the starting point for
any driver that communicates with odin-control.

On `initialise` it:

1. Opens an HTTP connection to the server.
2. Queries `api/0.1/adapters` to discover registered adapters.
3. Fetches the full parameter tree for each adapter with metadata headers to determine
   the adapter's module type.
4. Dispatches to the correct sub-controller class based on the module type:

| Module type | Adapter Controller |
|---|---|
| `FrameProcessor` | `FrameProcessorAdapterController` |
| `FrameReceiver` | `FrameReceiverAdapterController` |
| `MetaWriter` | `MetaWriterAdapterController` |
| *(anything else)* | `OdinAdapterController` |

## Odin Controllers

### `OdinSubController`

`OdinSubController` is a common base class for sub-controllers. It holds:

- The shared `HTTPConnection`.
- The `list[OdinParameter]` assigned to this node in the parameter tree.
- The `api_prefix` string that identifies this node's URL.

It exposes two protected helpers that subclasses call from their own `initialise`:

#### `_create_attributes()`

Iterates `self.parameters` and registers a FastCS `Attribute` for each one. Attributes
are backed by `ParameterTreeAttributeIO`, which reads and writes via the REST API using
the parameter's URI.

#### `_create_commands(path=())`

GETs `<api_prefix>/command[/<path>]/allowed`, parses the response, and for each
allowed command name dynamically attaches a FastCS `Command` to the controller. The
command PUTs to `.../execute` when invoked. This means detector-specific commands
exposed through odin-control appear automatically without any extra code.

### `OdinAdapterController`

`OdinAdapterController` is a thin convenience wrapper around `OdinSubController`. Its entire `initialise`
is:

```python
async def initialise(self):
    await self._create_attributes()
    await self._create_commands()
```

It is the default used by `OdinController` for any adapter whose module type is not
recognised. For a simple adapter with no special tree structure it is all that is
needed, and it is a good starting point for a custom adapter controller.

## odin-data Controllers

These controllers are provided to connect to common odin-data applications; the
frame receiver, frame processor and meta writer.

### `OdinDataAdapterController`

`OdinDataAdapterController` is a FastCS `ControllerVector` that manages a numbered set
of identical child controllers — one per running odin-data process (frameReceiver or
frameProcessor application).

On `initialise` it:

1. Partitions `self.parameters` by leading numeric index in the URI
   (`0/status/...`, `1/status/...`, …).
2. Creates one `_subcontroller_cls` instance per index, scoped to
   `<api_prefix>/<idx>`.
3. Keeps parameters *without* a numeric prefix at the adapter level and creates
   attributes for them directly.
4. Calls `_create_config_fan_attributes()` to build fan-out write attributes at
   the adapter level. Any config parameter that appears in every child controller and
   is *not* listed in `_unique_config` gets a top-level attribute whose write
   propagates to all child controllers simultaneously.

Subclasses set three class variables to specialise behaviour:

| Variable | Purpose |
|---|---|
| `_subcontroller_cls` | The child controller type to instantiate per index |
| `_subcontroller_label` | Short label used to name child controllers (`FP`, `FR`, …) |
| `_unique_config` | Config keys that differ per process and must not be fan-out'd |

#### `FrameReceiverAdapterController` / `FrameReceiverController`

Merges the `decoder` and `decoder_config` sub-trees under a single `decoder` group
before calling `add_attribute`.

#### `FrameProcessorAdapterController` / `FrameProcessorController`

Declares class-level summary attributes backed by `StatusSummaryAttributeIORef` that
aggregate values across all FP instances — `frames_written` (sum) and `writing` (`any`).
Top-level `start_writing` and `stop_writing` commands fan out to the HDF plugin of every
child controller.

Queries `status/plugins/names` to discover loaded plugins and creates a
`FrameProcessorPluginController` sub-controller for each one. Each plugin controller
calls `_create_commands([plugin_name])` to auto-discover commands.

### `MetaWriterAdapterController`

A direct subclass of `OdinSubController` for the meta writer adapter. It combines
*static* class-level attributes (`acquisition_id`, `directory`, `file_prefix`,
`writing`, `written`) bound to hard-coded URIs with the *dynamic* attribute creation
inherited from `OdinSubController`. The `stop` command is also declared statically. The
`acquisitions` sub-tree (temporal per-acquisition state) is excluded during
`initialise`. This is to workaround the dynamic acquisitions the meta writer creates
that are not exposed via the parameter tree.

## Building a Detector-Specific Driver

The classes above are designed to be combined or extended for a particular detector.
The diagram below gives an overview: fastcs-odin (right) provides the base
classes; a detector package (left, with fastcs-detector as an example) inherits
from or composes them. The centre column shows a concrete `OdinController` at runtime
with the sub-controllers it creates, colour-matched to the base classes on the right.

---

```{raw} html
:file: ../images/controllers.excalidraw.svg
```

---

This allows a lot of flexibility when implementing a driver for a specific detector to
rely primarily on the base implementations while adding detector specific logic through
composition and inheritance. The two key patterns are to acheive this are:

- Creating base classes of the built-in controllers to add type hints that validate when
  running against a specific odin server that the given attributes are introspected for
  use in driver logic
- Sub classing `OdinController` and overriding `_create_adapter_controller` to create
  detector-specific adapter controllers that implement detector specific logic.

For a worked example of putting these pieces together, see the tutorial on
[](../tutorials/odin-detector.md).
