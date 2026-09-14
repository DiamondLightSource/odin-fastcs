import json
import re
from functools import partial
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastcs.attributes import AttrR, AttrRW
from fastcs.connections import IPConnectionSettings
from fastcs.controllers import Controller
from fastcs.datatypes import Bool, Float, Int, String
from pytest_mock import MockerFixture

from fastcs_odin.controllers.odin_adapter_controller import OdinAdapterController
from fastcs_odin.controllers.odin_controller import (
    OdinController,
    OdinControllerSettings,
)
from fastcs_odin.controllers.odin_data.frame_processor import (
    FrameProcessorAdapterController,
    FrameProcessorController,
    FrameProcessorPluginController,
)
from fastcs_odin.controllers.odin_data.frame_receiver import (
    FrameReceiverAdapterController,
)
from fastcs_odin.controllers.odin_data.meta_writer import MetaWriterAdapterController
from fastcs_odin.controllers.odin_subcontroller import OdinSubController
from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.io.config_fan_sender_attribute_io import (
    ConfigFanAttributeIO,
    ConfigFanAttributeIORef,
)
from fastcs_odin.io.parameter_attribute_io import (
    AdapterResponseError,
    ParameterTreeAttributeIO,
    ParameterTreeAttributeIORef,
)
from fastcs_odin.io.status_summary_attribute_io import (
    StatusSummaryAttributeIO,
    StatusSummaryAttributeIORef,
    initialise_summary_attributes,
)
from fastcs_odin.util import (
    AdapterType,
    OdinParameter,
    OdinParameterMetadata,
    create_attribute,
)

HERE = Path(__file__).parent


def test_create_attributes():
    parameters = [
        OdinParameter(
            uri=["read_int"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
        ),
        OdinParameter(
            uri=["write_bool"],
            metadata=OdinParameterMetadata(value=True, type="bool", writeable=True),
        ),
        OdinParameter(
            uri=["group", "float"],
            metadata=OdinParameterMetadata(value=0.1, type="float", writeable=True),
        ),
    ]
    controller = OdinSubController(HTTPConnection("", 0), parameters, "api/0.1", [])

    for parameter in controller.parameters:
        controller.add_attribute(
            parameter.name,
            create_attribute(parameter=parameter, api_prefix=controller._api_prefix),
        )

    match controller.attributes:
        case {
            "read_int": AttrR(datatype=Int()),
            "write_bool": AttrRW(datatype=Bool()),
            "group_float": AttrR(datatype=Float(), group="Group"),
        }:
            pass
        case _:
            pytest.fail("Controller Attributes not as expected")


@pytest.mark.asyncio
async def test_create_commands(mocker: MockerFixture):
    mock_connection = mocker.AsyncMock()
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    mock_connection.get.side_effect = [
        {"allowed": response[str(0)]["command"]["hdf"]["allowed"]},
        {"response": "No commands, path invalid"},
    ]

    controller = FrameProcessorPluginController(mock_connection, [], "api/0.1", [])
    controller._path = ["hdf"]

    await controller._create_commands()

    # Call the command methods that have been bound to the controller
    await controller.command1()  # type: ignore
    await controller.command2()  # type: ignore

    controller = FrameProcessorPluginController(mock_connection, [], "api/0.1", [])
    controller._path = ["offset"]

    await controller._create_commands()


@pytest.mark.asyncio
async def test_fp_process_parameters_during_initialise(mocker: MockerFixture):
    parameters = [
        OdinParameter(
            ["0", "status", "hdf", "frames_written"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
        ),
        OdinParameter(
            ["0", "config", "hdf", "frames"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=True),
        ),
    ]

    mock_connection = mocker.AsyncMock()
    mock_connection.get.return_value = {"names": ["plugin_a", "plugin_b"]}

    fpc = FrameProcessorController(mock_connection, parameters, "api/0.1", [])

    await fpc.initialise()
    assert fpc.parameters == [
        OdinParameter(
            uri=["status", "hdf", "frames_written"],
            _path=["hdf", "frames_written"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
        ),
        OdinParameter(
            uri=["config", "hdf", "frames"],
            _path=["hdf", "frames"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=True),
        ),
    ]


@pytest.mark.asyncio
async def test_create_adapter_controller(mocker: MockerFixture):
    controller = OdinController(OdinControllerSettings(IPConnectionSettings("", 0)))
    controller.connection = mocker.AsyncMock()
    parameters = [
        OdinParameter(
            ["0"], metadata=OdinParameterMetadata(value=0, type="int", writeable=False)
        )
    ]

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "fp", AdapterType.FRAME_PROCESSOR
    )
    assert isinstance(ctrl, FrameProcessorAdapterController)

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "fr", AdapterType.FRAME_RECEIVER
    )
    assert isinstance(ctrl, FrameReceiverAdapterController)

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "mw", AdapterType.META_WRITER
    )
    assert isinstance(ctrl, MetaWriterAdapterController)

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "od", "OtherAdapter"
    )
    assert isinstance(ctrl, OdinSubController)


@pytest.mark.parametrize(
    "mock_get, expected_controller, expected_commands",
    [
        [
            [
                {"adapters": ["test_adapter"]},
                {"": {"value": "test_module"}},
                {"allowed": ["start", "stop"]},
            ],
            OdinAdapterController,
            ("start", "stop"),
        ],
        [
            [
                {"adapters": ["test_adapter"]},
                {"": {"value": "test_module"}},
                {
                    "response": "FrameProcessorAdapter GET error: "
                    "Invalid path: 0/command/test_adapter/allowed"
                },
            ],
            OdinAdapterController,
            (),
        ],
        [
            [
                {"adapters": ["test_adapter"]},
                {"module": {"value": "FrameProcessorAdapter"}},
            ],
            FrameProcessorAdapterController,
            (),
        ],
    ],
)
@pytest.mark.asyncio
async def test_controller_initialise(
    mocker: MockerFixture, mock_get, expected_controller, expected_commands
):
    # Status summary attributes won't work without real sub controllers
    mocker.patch(
        "fastcs_odin.controllers.odin_controller.initialise_summary_attributes"
    )
    mocker.patch(
        "fastcs_odin.controllers.odin_data.odin_data_adapter.initialise_summary_attributes"
    )

    controller = OdinController(OdinControllerSettings(IPConnectionSettings("", 0)))

    controller.connection = mocker.AsyncMock()
    controller.connection.open = mocker.MagicMock()

    controller.connection.get.side_effect = mock_get

    await controller.initialise()

    assert isinstance(controller.test_adapter, expected_controller)  # type: ignore
    assert all(c in controller.test_adapter.command_methods for c in expected_commands)  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.asyncio
async def test_controller_initialise_short_adapter_name_is_uppercased(
    mocker: MockerFixture,
):
    mocker.patch(
        "fastcs_odin.controllers.odin_controller.initialise_summary_attributes"
    )
    mocker.patch(
        "fastcs_odin.controllers.odin_data.odin_data_adapter.initialise_summary_attributes"
    )

    controller = OdinController(OdinControllerSettings(IPConnectionSettings("", 0)))
    controller.connection = mocker.AsyncMock()
    controller.connection.open = mocker.MagicMock()
    controller.connection.get.side_effect = [
        {"adapters": ["fp", "xspress"]},
        {"module": {"value": "FrameProcessorAdapter"}},
        {"module": {"value": "XspressProcessorAdapter"}},
    ]

    await controller.initialise()

    assert "FP" in controller.sub_controllers
    assert "xspress" in controller.sub_controllers


@pytest.mark.asyncio
async def test_fp_create_plugin_sub_controllers(mocker: MockerFixture):
    mock_connection = mocker.AsyncMock()
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    mock_connection.get.side_effect = [
        {"allowed": response[str(0)]["command"]["hdf"]["allowed"]},
    ]

    parameters = [
        OdinParameter(
            uri=["config", "ctrl_endpoint"],
            _path=["ctrl_endpoint"],
            metadata=OdinParameterMetadata(value="", type="str", writeable=True),
        ),
        OdinParameter(
            uri=["status", "hdf", "frames_written"],
            _path=["hdf", "frames_written"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
        ),
        OdinParameter(
            uri=["status", "hdf", "dataset", "compressed_size", "compression"],
            _path=["hdf", "dataset", "compressed_size", "compression"],
            metadata=OdinParameterMetadata(value="", type="str", writeable=False),
        ),
    ]

    fpc = FrameProcessorController(mock_connection, parameters, "api/0.1", [])

    await fpc._create_plugin_sub_controllers(["hdf"])

    # Check that hdf parameter has been split into a sub controller
    assert fpc.parameters == [
        OdinParameter(
            uri=["config", "ctrl_endpoint"],
            _path=["ctrl_endpoint"],
            metadata=OdinParameterMetadata(value="", type="str", writeable=True),
        )
    ]
    controllers = fpc.sub_controllers
    match controllers:
        case {
            "HDF": FrameProcessorPluginController(
                parameters=[
                    OdinParameter(
                        uri=["status", "hdf", "frames_written"],
                        _path=["frames_written"],
                        metadata=OdinParameterMetadata(
                            value=0, type="int", writeable=False
                        ),
                    )
                ]
            )
        }:
            sub_controllers = controllers["HDF"].sub_controllers
            assert "DS" in sub_controllers
            assert isinstance(sub_controllers["DS"], OdinSubController)
            assert sub_controllers["DS"].parameters == [
                OdinParameter(
                    uri=["status", "hdf", "dataset", "compressed_size", "compression"],
                    _path=["compressed_size", "compression"],
                    metadata=OdinParameterMetadata(
                        value="", type="str", writeable=False
                    ),
                )
            ]
        case _:
            pytest.fail("Sub controllers not as expected")


@pytest.mark.asyncio
async def test_param_tree_io_update(mocker: MockerFixture):
    connection = mocker.AsyncMock()
    io = ParameterTreeAttributeIO(connection)
    attr = AttrR(Int(), io_ref=ParameterTreeAttributeIORef("hdf/frames_written"))

    connection.get.return_value = {"frames_written": 20}
    await io.update(attr)
    connection.get.assert_called_once_with("hdf/frames_written")
    assert attr.get() == 20

    # Check validate called to cast value
    connection.get.return_value = {"frames_written": "20"}
    await io.update(attr)
    assert attr.get() == 20

    # Check parsing "value" key
    connection.get.return_value = {"value": 30}
    await io.update(attr)
    assert attr.get() == 30

    # Check fail to parse raises exception
    connection.get.return_value = {"frames_wrotten": 40}
    with pytest.raises(ValueError, match="Failed to parse response"):
        await io.update(attr)
    assert attr.get() == 30


@pytest.mark.asyncio
async def test_param_tree_io_update_get_exception(mocker: MockerFixture, loguru_caplog):
    connection = mocker.AsyncMock()
    connection.get.side_effect = RuntimeError("connection failed")
    io = ParameterTreeAttributeIO(connection)
    attr = AttrR(Int(), io_ref=ParameterTreeAttributeIORef("hdf/frames_written"))

    with pytest.raises(RuntimeError, match="connection failed"):
        await io.update(attr)

    assert "Failed to get parameter" in loguru_caplog.text


@pytest.mark.asyncio
async def test_param_tree_io_send(mocker: MockerFixture):
    connection = mocker.AsyncMock()
    io = ParameterTreeAttributeIO(connection)
    attr = AttrRW(Int(), io_ref=ParameterTreeAttributeIORef("hdf/frames"))

    await io.send(attr, 10)

    connection.put.assert_called_once_with("hdf/frames", 10)


@pytest.mark.asyncio
async def test_param_tree_handler_send_exception(mocker: MockerFixture):
    connection = mocker.AsyncMock()
    connection.put.return_value = {"error": "No, you can't do that"}
    io = ParameterTreeAttributeIO(connection)
    attr = AttrRW(Int(), io_ref=ParameterTreeAttributeIORef("hdf/frames"))

    with pytest.raises(AdapterResponseError, match="No, you can't do that"):
        await io.send(attr, -1)

    connection.put.assert_called_once_with("hdf/frames", -1)


@pytest.mark.asyncio
async def test_status_summary_attribute_io():
    controller = Controller()
    fpa_controller = Controller()
    fp1_controller = Controller()
    fp2_controller = Controller()
    hdf1_controller = Controller()
    hdf2_controller = Controller()

    controller.add_sub_controller("FP", fpa_controller)
    fpa_controller.add_sub_controller("FP0", fp1_controller)
    fpa_controller.add_sub_controller("FP1", fp2_controller)
    fp1_controller.add_sub_controller("HDF", hdf1_controller)
    fp2_controller.add_sub_controller("HDF", hdf2_controller)

    io = StatusSummaryAttributeIO()

    frames_written = AttrR(
        Int(),
        io_ref=StatusSummaryAttributeIORef(
            ["FP", re.compile("FP*"), "HDF"], "frames_written", partial(sum, start=0)
        ),
    )
    controller.frames_written = frames_written
    writing = AttrR(
        Bool(),
        io_ref=StatusSummaryAttributeIORef(
            ["FP", re.compile("FP*"), ("HDF",)], "writing", any
        ),
    )
    controller.writing = writing

    hdf1_controller.frames_written = AttrR(Int(), initial_value=50)
    hdf2_controller.frames_written = AttrR(Int(), initial_value=100)
    hdf1_controller.writing = AttrR(Bool(), initial_value=False)
    hdf_writing = AttrR(Bool(), initial_value=True)
    hdf2_controller.writing = hdf_writing

    initialise_summary_attributes(controller)

    await io.update(frames_written)
    assert frames_written.get() == 150

    await io.update(writing)
    assert writing.get()

    await hdf_writing.update(False)
    await io.update(writing)
    assert not writing.get()


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_sub_controller", ("FP", ("FP",), re.compile("FP")))
async def test_status_summary_updater_raise_exception_if_controller_not_found(
    mock_sub_controller, mocker: MockerFixture
):
    controller = Controller()

    controller.writing = AttrR(
        Bool(), StatusSummaryAttributeIORef(["OD", mock_sub_controller], "writing", any)
    )
    with pytest.raises(ValueError, match=r"Sub controller .* not found"):
        initialise_summary_attributes(controller)


@pytest.mark.asyncio
async def test_config_fan_sender(mocker: MockerFixture):
    attr1 = mocker.MagicMock()
    attr1.put = (put1_mock := mocker.AsyncMock())
    attr2 = mocker.MagicMock()
    attr2.put = (put2_mock := mocker.AsyncMock())

    attr = AttrRW(Int(), ConfigFanAttributeIORef([attr1, attr2]))
    io = ConfigFanAttributeIO()

    await io.send(attr, 10)
    put1_mock.assert_called_once_with(10, sync_setpoint=True)
    put2_mock.assert_called_once_with(10, sync_setpoint=True)

    attr1.get.return_value = 10
    attr2.get.return_value = 5

    await io.update(attr)
    assert attr.get() == 0  # attributes don't match -> default value

    attr2.get.return_value = 10

    await io.update(attr)
    assert attr.get() == 10  # attributes match -> set value


@pytest.mark.asyncio
async def test_frame_processor_start_and_stop_writing(mocker: MockerFixture):
    fpac = FrameProcessorAdapterController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    fpc = FrameProcessorController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    await fpc._create_plugin_sub_controllers(["hdf"])

    # Mock the commands to check calls
    hdf = fpc.sub_controllers["HDF"]
    hdf.start_writing = mocker.AsyncMock()  # type: ignore
    hdf.stop_writing = mocker.AsyncMock()  # type: ignore

    fpac.file_path = AttrRW(String())
    fpac.file_prefix = AttrRW(String())

    fpac[0] = fpc

    # Top level FP commands should collect and call lower level commands
    await fpac.start_writing()
    await fpac.stop_writing()
    assert len(hdf.start_writing.mock_calls) == 1  # type: ignore
    assert len(hdf.stop_writing.mock_calls) == 1  # type: ignore


@pytest.mark.asyncio
async def test_vds_generator_created_on_start_writing(mocker: MockerFixture):
    fpac = FrameProcessorAdapterController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    fpc = FrameProcessorController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    await fpc._create_plugin_sub_controllers(["hdf"])

    hdf = fpc.sub_controllers["HDF"]
    hdf.start_writing = mocker.AsyncMock()
    hdf.stop_writing = mocker.AsyncMock()

    fpac.file_path = AttrRW(String(), initial_value="test_path")
    fpac.file_prefix = AttrRW(String(), initial_value="test_prefix")

    fpac[0] = fpc

    await fpac.start_writing()
    assert fpac.vds.path == Path("test_path")
    assert fpac.vds.prefix == "test_prefix"


@pytest.mark.asyncio
async def test_vds_created_on_stop_writing_if_vds_enabled(mocker: MockerFixture):
    fpac = FrameProcessorAdapterController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    fpc = FrameProcessorController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    await fpc._create_plugin_sub_controllers(["hdf"])

    hdf = fpc.sub_controllers["HDF"]
    hdf.start_writing = mocker.AsyncMock()
    hdf.stop_writing = mocker.AsyncMock()

    await fpac.enable_vds_creation.put(True)
    fpac.file_path = AttrRW(String(), initial_value="test_path")
    fpac.file_prefix = AttrRW(String(), initial_value="test_prefix")
    fpac.process_frames_per_block = AttrRW(Int(), initial_value=1)
    fpac.process_blocks_per_file = AttrRW(Int(), initial_value=0)
    fpac.data_dims_0 = AttrRW(Int(), initial_value=10)
    fpac.data_dims_1 = AttrRW(Int(), initial_value=20)
    fpac.data_datatype = AttrRW(String(), initial_value="uint32")
    fpac.frames_written.get = MagicMock(return_value=100)

    fpac[0] = fpc

    await fpac.start_writing()
    fpac.vds.create_interleave_vds = MagicMock()
    await fpac.stop_writing()
    fpac.vds.create_interleave_vds.assert_called_once_with(
        datasets=["data", "data2", "data3"],
        frame_count=100,
        frames_per_block=1,
        blocks_per_file=0,
        frame_shape=(10, 20),
        dtype="uint32",
    )


@pytest.mark.asyncio
async def test_top_level_frame_processor_commands_raise_exception(
    mocker: MockerFixture,
):
    fpac = FrameProcessorAdapterController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )

    fpc = FrameProcessorController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    await fpc._create_plugin_sub_controllers(["hdf"])
    fpac[0] = fpc

    fpac.file_path = AttrRW(String(), initial_value="")
    fpac.file_prefix = AttrRW(String(), initial_value="")

    with pytest.raises(AttributeError, match="does not have"):
        await fpac.start_writing()


@pytest.mark.asyncio
async def test_status_summary_updater_raises_exception_if_attribute_not_found():
    controller = Controller()
    sub_controller = Controller()

    controller.add_sub_controller("OD", sub_controller)

    controller.writing = AttrR(
        Bool(), StatusSummaryAttributeIORef(["OD"], "some_attribute", any)
    )
    with pytest.raises(KeyError, match=r"Sub controller .* does not have attribute"):
        initialise_summary_attributes(controller)


@pytest.mark.asyncio
async def test_subcontroller_vs_adapter_controller_initialise(mocker: MockerFixture):
    sub_controller = OdinSubController(mocker.Mock(), [], "api/0.1", [])
    create_attributes_mock = mocker.patch.object(
        sub_controller, "_create_attributes", mocker.AsyncMock()
    )
    create_commands_mock = mocker.patch.object(
        sub_controller, "_create_commands", mocker.AsyncMock()
    )

    await sub_controller.initialise()

    create_attributes_mock.assert_called_once()
    create_commands_mock.assert_not_called()

    adapter_controller = OdinAdapterController(mocker.Mock(), [], "api/0.1", [])
    create_attributes_mock = mocker.patch.object(
        adapter_controller, "_create_attributes", mocker.AsyncMock()
    )
    create_commands_mock = mocker.patch.object(
        adapter_controller, "_create_commands", mocker.AsyncMock()
    )

    await adapter_controller.initialise()

    create_attributes_mock.assert_called_once()
    create_commands_mock.assert_called_once()
