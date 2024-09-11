import re
from pathlib import Path

import pytest
from fastcs.attributes import AttrR, AttrRW
from fastcs.datatypes import Bool, Float, Int
from pytest_mock import MockerFixture

from odin_fastcs.http_connection import HTTPConnection
from odin_fastcs.odin_adapter_controller import (
    ConfigFanSender,
    ParamTreeHandler,
    StatusSummaryUpdater,
)
from odin_fastcs.odin_controller import OdinAdapterController
from odin_fastcs.odin_data import (
    FrameProcessorController,
    FrameProcessorPluginController,
    FrameReceiverController,
    FrameReceiverDecoderController,
)
from odin_fastcs.util import OdinParameter

HERE = Path(__file__).parent


def test_create_attributes():
    parameters = [
        OdinParameter(uri=["read_int"], metadata={"type": "int"}),
        OdinParameter(uri=["write_bool"], metadata={"type": "bool", "writeable": True}),
        OdinParameter(uri=["group", "float"], metadata={"type": "float"}),
    ]
    controller = OdinAdapterController(HTTPConnection("", 0), parameters, "api/0.1")

    controller._create_attributes()

    match controller:
        case OdinAdapterController(
            read_int=AttrR(datatype=Int()),
            write_bool=AttrRW(datatype=Bool()),
            group_float=AttrR(datatype=Float(), group="Group"),
        ):
            pass
        case _:
            pytest.fail("Controller Attributes not as expected")


def test_fp_process_parameters():
    parameters = [
        OdinParameter(["0", "status", "hdf", "frames_written"], metadata={}),
        OdinParameter(["0", "config", "hdf", "frames"], metadata={}),
    ]

    fpc = FrameProcessorController(HTTPConnection("", 0), parameters, "api/0.1")

    fpc._process_parameters()
    assert fpc._parameters == [
        OdinParameter(
            uri=["status", "hdf", "frames_written"],
            _path=["hdf", "frames_written"],
            metadata={},
        ),
        OdinParameter(
            uri=["config", "hdf", "frames"], _path=["hdf", "frames"], metadata={}
        ),
    ]


@pytest.mark.asyncio
async def test_fp_create_plugin_sub_controllers():
    parameters = [
        OdinParameter(
            uri=["config", "ctrl_endpoint"],
            _path=["ctrl_endpoint"],
            metadata={"type": "str"},
        ),
        OdinParameter(
            uri=["status", "hdf", "frames_written"],
            _path=["hdf", "frames_written"],
            metadata={"type": "int"},
        ),
        OdinParameter(
            uri=["status", "hdf", "dataset", "compressed_size", "compression"],
            _path=["hdf", "dataset", "compressed_size", "compression"],
            metadata={"type": "str"},
        ),
    ]

    fpc = FrameProcessorController(HTTPConnection("", 0), parameters, "api/0.1")

    await fpc._create_plugin_sub_controllers(["hdf"])

    # Check that hdf parameter has been split into a sub controller
    assert fpc._parameters == [
        OdinParameter(
            uri=["config", "ctrl_endpoint"],
            _path=["ctrl_endpoint"],
            metadata={"type": "str"},
        )
    ]
    controllers = fpc.get_sub_controllers()
    match controllers:
        case {
            "HDF": FrameProcessorPluginController(
                _parameters=[
                    OdinParameter(
                        uri=["status", "hdf", "frames_written"],
                        _path=["frames_written"],
                    )
                ]
            )
        }:
            sub_controllers = controllers["HDF"].get_sub_controllers()
            assert "DS" in sub_controllers
            assert sub_controllers["DS"]._parameters == [
                OdinParameter(
                    uri=["status", "hdf", "dataset", "compressed_size", "compression"],
                    _path=["compressed_size", "compression"],
                    metadata={"type": "str"},
                )
            ]
        case _:
            pytest.fail("Sub controllers not as expected")


@pytest.mark.asyncio
async def test_param_tree_handler_update(mocker: MockerFixture):
    controller = mocker.AsyncMock()
    attr = mocker.MagicMock()

    handler = ParamTreeHandler("hdf/frames_written")

    controller._connection.get.return_value = {"frames_written": 20}
    await handler.update(controller, attr)
    attr.set.assert_called_once_with(20)


@pytest.mark.asyncio
async def test_param_tree_handler_update_exception(mocker: MockerFixture):
    controller = mocker.AsyncMock()
    attr = mocker.MagicMock()

    handler = ParamTreeHandler("hdf/frames_written")

    controller._connection.get.return_value = {"frames_wroted": 20}
    error_mock = mocker.patch("odin_fastcs.odin_adapter_controller.logging.error")
    await handler.update(controller, attr)
    error_mock.assert_called_once_with(
        "Update loop failed for %s:\n%s", "hdf/frames_written", mocker.ANY
    )


@pytest.mark.asyncio
async def test_param_tree_handler_put(mocker: MockerFixture):
    controller = mocker.MagicMock()
    attr = mocker.MagicMock()

    handler = ParamTreeHandler("hdf/frames")

    # Test put
    await handler.put(controller, attr, 10)
    controller._connection.put.assert_called_once_with("hdf/frames", 10)


@pytest.mark.asyncio
async def test_param_tree_handler_put_exception(mocker: MockerFixture):
    controller = mocker.AsyncMock()
    attr = mocker.MagicMock()

    handler = ParamTreeHandler("hdf/frames")

    controller._connection.put.return_value = {"error": "No, you can't do that"}
    error_mock = mocker.patch("odin_fastcs.odin_adapter_controller.logging.error")
    await handler.put(controller, attr, -1)
    error_mock.assert_called_once_with(
        "Put %s = %s failed:\n%s", "hdf/frames", -1, mocker.ANY
    )


@pytest.mark.asyncio
async def test_status_summary_updater(mocker: MockerFixture):
    controller = mocker.MagicMock()
    od_controller = mocker.MagicMock()
    fp_controller = mocker.MagicMock()
    fpx_controller = mocker.MagicMock()
    hdf_controller = mocker.MagicMock()
    attr = mocker.AsyncMock()

    controller.get_sub_controllers.return_value = {"OD": od_controller}
    od_controller.get_sub_controllers.return_value = {"FP": fp_controller}
    fp_controller.get_sub_controllers.return_value = {
        "FP0": fpx_controller,
        "FP1": fpx_controller,
    }
    fpx_controller.get_sub_controllers.return_value = {"HDF": hdf_controller}

    hdf_controller.frames_written.get.return_value = 50

    handler = StatusSummaryUpdater(
        ["OD", ("FP",), re.compile("FP*"), "HDF"], "frames_written", sum
    )
    hdf_controller.frames_written.get.return_value = 50
    await handler.update(controller, attr)
    attr.set.assert_called_once_with(100)

    handler = StatusSummaryUpdater(
        ["OD", ("FP",), re.compile("FP*"), "HDF"], "writing", any
    )

    hdf_controller.writing.get.side_effect = [True, False]
    await handler.update(controller, attr)
    attr.set.assert_called_with(True)

    hdf_controller.writing.get.side_effect = [False, False]
    await handler.update(controller, attr)
    attr.set.assert_called_with(False)


@pytest.mark.asyncio
async def test_config_fan_sender(mocker: MockerFixture):
    controller = mocker.MagicMock()
    attr = mocker.MagicMock(AttrRW)
    attr1 = mocker.AsyncMock()
    attr2 = mocker.AsyncMock()

    handler = ConfigFanSender([attr1, attr2])

    await handler.put(controller, attr, 10)
    attr1.process.assert_called_once_with(10)
    attr2.process.assert_called_once_with(10)
    attr.set.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_frame_reciever_controllers():
    valid_non_decoder_parameter = OdinParameter(
        uri=["0", "status", "buffers", "total"],
        metadata={"value": 292, "type": "int", "writeable": False},
    )
    valid_decoder_parameter = OdinParameter(
        uri=["0", "status", "decoder", "packets_dropped"],
        metadata={"value": 0, "type": "int", "writeable": False},
    )

    invalid_decoder_parameter = OdinParameter(
        uri=["0", "status", "decoder", "name"],
        metadata={
            "value": "DummyUDPFrameDecoder",
            "type": "str",
            "writeable": False,
        },
    )
    parameters = [
        valid_non_decoder_parameter,
        valid_decoder_parameter,
        invalid_decoder_parameter,
    ]
    fr_controller = FrameReceiverController(
        HTTPConnection("", 0), parameters, "api/0.1"
    )
    await fr_controller.initialise()
    assert isinstance(fr_controller, FrameReceiverController)
    assert valid_non_decoder_parameter in fr_controller._parameters
    assert len(fr_controller._parameters) == 1
    assert "DECODER" in fr_controller.get_sub_controllers()

    decoder_controller = fr_controller.get_sub_controllers()["DECODER"]
    assert isinstance(decoder_controller, FrameReceiverDecoderController)
    assert valid_decoder_parameter in decoder_controller._parameters
    assert invalid_decoder_parameter not in decoder_controller._parameters
    # index, status, decoder parts removed from path
    assert decoder_controller._parameters[0]._path == ["packets_dropped"]
