from pathlib import Path

import pytest
from fastcs.attributes import AttrR, AttrRW
from fastcs.datatypes import Bool, Float, Int

from odin_fastcs.frame_processor import (
    FrameProcessorController,
    FrameProcessorPluginController,
)
from odin_fastcs.http_connection import HTTPConnection
from odin_fastcs.odin_controller import OdinAdapterController
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
    match fpc.get_sub_controllers():
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
            pass
        case _:
            pytest.fail("Sub controllers not as expected")
