import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from odin_fastcs.frame_processor import FrameProcessorAdapterController
from odin_fastcs.util import create_odin_parameters

HERE = Path(__file__).parent


def test_one_node():
    with (HERE / "input/one_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    parameters = create_odin_parameters(response)
    assert len(parameters) == 97


def test_two_node():
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    parameters = create_odin_parameters(response)
    assert len(parameters) == 190


@pytest.mark.asyncio
async def test_fp_initialise(mocker: MockerFixture):
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    async def get_plugins(idx: int):
        return response[str(idx)]["status"]["plugins"]

    mock_connection = mocker.MagicMock()
    mock_connection.get.side_effect = [get_plugins(0), get_plugins(1)]

    parameters = create_odin_parameters(response)
    controller = FrameProcessorAdapterController(mock_connection, parameters, "prefix")
    await controller.initialise()
    assert all(fpx in controller.get_sub_controllers() for fpx in ("FP0", "FP1"))


def test_node_with_empty_list_is_correctly_counted():
    parameters = create_odin_parameters({"test": []})
    names = [p.name for p in parameters]
    assert "test" in names
    assert len(parameters) == 1


def test_node_that_has_metadata_only_counts_once():
    data = {"count": {"value": 1, "writeable": False, "type": "int"}}
    parameters = create_odin_parameters(data)
    assert len(parameters) == 1


def test_nested_node_gives_correct_name():
    data = {"top": {"nest-1": {"nest-2": 1}}}
    parameters = create_odin_parameters(data)
    assert len(parameters) == 1
    assert parameters[0].name == "top_nest-1_nest-2"


def test_config_node_splits_list_into_mutiples():
    data = {"config": {"param": [1, 2]}}
    parameters = create_odin_parameters(data)
    assert len(parameters) == 2
