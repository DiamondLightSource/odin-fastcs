# Creating an Odin Detector Driver

## Introduction

This tutorial walks through creating a FastCS driver for a detector controlled by
[Odin](https://github.com/odin-detector). The
`fastcs-odin` package builds on FastCS to provide an `OdinController` that introspects
an Odin server and creates sub controllers and attributes for each adapter it finds.

This tutorial will walk through the creation of a driver that can:

- Introspect an Odin deployment and expose all parameters as PVs
- Configure and run detector acquisitions from a single top-level API
- Display a live view of captured frames
- Use logging and tracing to debug the data path

## Set Up

### Odin Deployment

The odin-data-example deployment container should be started:

```bash
docker run --rm -it --security-opt label=disable \
    -v /dev/shm:/dev/shm -v /tmp:/tmp --net=host \
    ghcr.io/odin-detector/odin-data-example-runtime:0.2.3
```

All applications should start without errors.

### Python Environment

Clone [fastcs-odin](https://github.com/DiamondLightSource/fastcs-odin) and open it in
VS Code. Reopen in the dev container and install the dependencies:

```bash
pip install 'fastcs[epics]' pillow aioca
```

An `example.py` file should be created in the project root.

### Phoebus

A [Phoebus container](https://github.com/epics-containers/ec-phoebus) should be started.
A settings file will likely be needed to configure name servers for both PVA and CA.

## A Minimal Controller

The core of a FastCS device driver is the `Controller`. An `ExampleOdinController`
should be created that inherits from `Controller` with a single read-write integer
attribute, and launched with `FastCS`.

::::{admonition} Code 1
:class: dropdown, hint

:::{literalinclude} /snippets/odin01.py
:::

::::

The application will start and drop into an interactive shell. The attribute can be read
and written from the shell:

```
In [1]: controller.foo.get()
Out[1]: 0

In [2]: await controller.foo.put(1)

In [3]: controller.foo.get()
Out[3]: 1
```

:::{note}
There is also a helper if there are errors about running on the wrong event loop:
```python
run(controller.foo.put(1))
```
:::

## Adding an EPICS Transport

An EPICS CA transport can be added to expose the controller's attributes as PVs. The PV
prefix should be unique.

::::{admonition} Code 2
:class: dropdown, hint

:::{literalinclude} /snippets/odin02.py
:emphasize-lines: 5,6,15
:::

::::

The IOC will now be serving PVs. They can be listed in the interactive shell and
interacted with from a terminal:

```
In [1]: dbl()
EXAMPLE:Foo_RBV
EXAMPLE:Foo
EXAMPLE:PVI_PV
```

```bash
❯ caget EXAMPLE:Foo_RBV
EXAMPLE:Foo_RBV            1
❯ caput EXAMPLE:Foo 5
Old : EXAMPLE:Foo                1
New : EXAMPLE:Foo                5
❯ caget EXAMPLE:Foo_RBV
EXAMPLE:Foo_RBV            5
```

## Generating a Phoebus UI

FastCS can be configured to generate a Phoebus `.bob` file for a UI.

::::{admonition} Code 3
:class: dropdown, hint

:::{literalinclude} /snippets/odin03.py
:emphasize-lines: 1,7,20-22
:::

::::

`opis/example.bob` should appear and can be opened in Phoebus with
File > Open > example.bob. Values can be set from the UI to verify it works.

## Connecting to Odin

The controller should be updated to inherit from `OdinController` instead of
`Controller`. This controller connects to an Odin server, introspects all of its adapters, and
creates sub controllers and attributes for each one automatically.

::::{admonition} Code 4
:class: dropdown, hint

:::{literalinclude} /snippets/odin04.py
:emphasize-lines: 4,10,13,18
:::

::::

:::{note}
Warnings about parameters failing to be read are expected for some adapter parameters.
:::

The PVs can be listed in the interactive shell to see what has been created:

```
In [1]: dbl()
EXAMPLE:DETECTOR:ConfigExposureTime_RBV
...
EXAMPLE:FP:0:HDF:FileUseNumbers_RBV
...
EXAMPLE:FR:2:DecoderEnablePacketLogging_RBV
...
EXAMPLE:DETECTOR:Start
```

The controller now has sub controllers for each adapter:

```
In [2]: controller.sub_controllers
Out[2]:
{'DETECTOR': OdinAdapterController(path=DETECTOR, sub_controllers=None),
 'FR': FrameReceiverAdapterController(path=FR, sub_controllers=['0', '1', '2', '3']),
 'FP': FrameProcessorAdapterController(path=FP, sub_controllers=['0', '1', '2', '3']),
 'LIVE': OdinAdapterController(path=LIVE, sub_controllers=None),
 'SYSTEM': OdinAdapterController(path=SYSTEM, sub_controllers=None)}
```

Sub controllers for adapters can be mapped to specific classes, or the
fallback `OdinAdapterController`, which introspects the parameter tree and adds no
additional logic.

### Phoebus UI

The display can be reloaded in Phoebus (right-click > Re-load display). There should now
be buttons for each sub controller.

- Open the DETECTOR screen. Pressing Start should cause the frame counter to
  tick up.
- The FP screen has top-level attributes that read/write each individual FP instance.
  Things that must differ per instance (like `CtrlEndpoint`) are excluded. These can be
  seen in the screen for the specific instance, e.g. `FP0`.
- The FP screen also has PVs for the `example` dataset. These are detector-specific
  and defined in the Odin config file.

## Running an Acquisition

An acquisition can now be run using the sub controller screens:

1. Set `FP.FilePath` = `/tmp`
2. Set `FP.FilePrefix` = `test`
3. Set `FP.Frames` = `10`
4. Press `FP.StartWriting`
5. Check that `FP.Writing` is set
6. Set `DETECTOR.Frames` = `10`
7. Press `DETECTOR.Start`
8. Watch `FP.FramesWritten` count up to 10 and then `FP.Writing` unset

The interactive shell will show the parameters that are being set.

## Improving the API

Navigating between sub screens is fiddly. Top-level attributes can be added that fan
values out to the relevant sub controllers. The `foo` attribute should be removed and an
`initialise` method added to create new attributes after the Odin introspection has
completed.

::::{admonition} Code 5
:class: dropdown, hint

:::{literalinclude} /snippets/odin05.py
:emphasize-lines: 6,12,15-33
:::

::::

After running and reloading the display, the new PVs will appear on the top screen.

:::{note}
`FP` and `DETECTOR` are accessed as attributes of `self`, but they are unknown to static
type checkers because they are only created at runtime during Odin introspection. There
will be no autocompletion for them yet.
:::

## Type Hints for Sub Controllers

FastCS validates type-hinted attributes, methods and sub controllers during
initialisation to fail early if something is wrong. Typed sub controller classes can be
created and type hints added to `ExampleOdinController`.

An `ExampleFrameProcessorAdapterController` inheriting from
`FrameProcessorAdapterController` with a `frames` attribute hint, and an
`ExampleDetectorAdapterController` inheriting from `OdinAdapterController` with a
`config_frames` attribute hint should be created.

:::{note}
`frames` has since been added to the parent `FrameProcessorAdapterController`, but is
kept here as an example of the pattern that can be applied to any other attribute on the
parent controller.
:::

Type hints for `FP` and `DETECTOR` should be added on `ExampleOdinController`, and
`_create_adapter_controller` overridden so that the correct controller types are
instantiated.

::::{admonition} Code 6
:class: dropdown, hint

:::{literalinclude} /snippets/odin06.py
:emphasize-lines: 6,12-15,19-27,31,32,53-72
:::

::::

Without overriding `_create_adapter_controller`, the application will fail with:

```
RuntimeError: Controller 'ExampleOdinController' introspection of hinted sub controller
'DETECTOR' does not match defined type. Expected 'ExampleDetectorAdapterController'
got 'OdinAdapterController'.
```

Type hints for attributes or sub controllers that don't exist will also fail:

```
RuntimeError: Controller `ExampleOdinController` failed to introspect hinted
controller `FOO` during initialisation
```

```
RuntimeError: Controller `ExampleOdinController` failed to introspect hinted
attribute `foo` during initialisation
```

## Adding Commands

Parameters can now be set from the top screen, but acquisitions cannot be run yet.
`start` and `stop` type hints should be added on `ExampleDetectorAdapterController`,
along with `acquire` and `stop` command methods on `ExampleOdinController`.

::::{admonition} Code 7
:class: dropdown, hint

:::{literalinclude} /snippets/odin07.py
:emphasize-lines: 8,29,30,37-45
:::

::::

:::{note}
`FrameProcessorAdapterController` already has `start_writing` and `stop_writing` defined
statically, so they do not need to be added to
`ExampleFrameProcessorAdapterController`.
:::

After running and reloading Phoebus, an acquisition can now be started and stopped from
the top screen.

## Adding Status Attributes

The top screen can trigger acquisitions but has no status. `status_acquiring` and
`status_frames` type hints should be added to `ExampleDetectorAdapterController`, and
top-level summary attributes created that aggregate status from multiple sub
controllers.

::::{admonition} Code 8
:class: dropdown, hint

:::{literalinclude} /snippets/odin08.py
:emphasize-lines: 3,7,19,30,31,69-80
:::

::::

The `StatusSummaryAttributeIORef` aggregates values from multiple attributes. The `any`
function is used for `acquiring` (true if any source is active) and `min` for
`frames_captured` (the lowest count across sources).

## Controller Logic

There is a risk that the file writer is slower to start than the detector and frames will
be missed. `wait_for_value` can be used to ensure that the file writers have started
before starting the detector.

::::{admonition} Code 9
:class: dropdown, hint

:::{literalinclude} /snippets/odin09.py
:emphasize-lines: 44
:::

::::

## Live View with Scan Methods

The live view adapter can be used to see frames as they pass through. A `Waveform`
attribute can be added to display the image along with a `@scan` method to periodically
query the live view adapter for images.

::::{admonition} Code 10
:class: dropdown, hint

:::{literalinclude} /snippets/odin10.py
:emphasize-lines: 1,4,9,10,13,44,46-57
:::

::::

:::{note}
The image dimensions and dtype could be queried from `LIVE.Shape` and `LIVE.FrameDtype`
at runtime to create `live_view_image` dynamically.
:::

The EPICS CA transport does not support 2D arrays, so it will give a warning and the
`LiveViewImage` PV will not be created via CA.

## Adding PV Access

An `EpicsPVATransport` can be added alongside the existing `EpicsCATransport` to serve
both transports simultaneously. PVA supports 2D array attributes, so the
`LiveViewImage` PV will be available over PVA.

::::{admonition} Code 11
:class: dropdown, hint

:::{literalinclude} /snippets/odin11.py
:emphasize-lines: 13,131-137
:::

::::

An acquisition can be run and the live view watched (LiveViewImage button):

1. Set `DETECTOR.Frames` = `0` (continuous)
2. Press `DETECTOR.Start`

## Logging and Tracing

There is a custom logger built into fastcs that allows structured logging and
trace-level logging that can be enabled at runtime per-attribute.

Add INFO level log statements to the `acquire` and `stop` commands to record when
writing starts and stops.

::::{admonition} Code 12
:class: dropdown, hint

:::{literalinclude} /snippets/odin12.py
:emphasize-lines: 10,63,71,128
:::

::::

Running an acquisition will then produce log output:

```
[2025-12-23 12:07:31.615+0000 I] Starting writing
[2025-12-23 12:07:32.012+0000 I] Stopping writing
```

TRACE level logging must be configured for trace messages to appear. This will not
produce additional output until tracing is enabled at runtime, although it will enable
DEBUG level output. There are trace level messages logged throughout the fastcs
codebase to enable debugging live systems. All classes that inherit `Tracer` can call
`log_event` to emit trace messages, which can be enabled at runtime by calling
`enable_tracing`. For example, `Attribute`s:

```
In [1]: controller.FP[0].HDF.file_path.enable_tracing()
[2025-12-23 12:07:31.615+0000 T] Query for parameter [ParameterTreeAttributeIO] uri=api/0.1/fp/0/config/hdf/file/path, response={'path': '/tmp'}
...
In [2]: controller.FP[0].HDF.file_path.disable_tracing()
```
