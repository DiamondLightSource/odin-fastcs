import json
from pathlib import Path

from odin_fastcs.util import create_odin_parameters

HERE = Path(__file__).parent


def test_one_node():
    with (HERE / "input/one_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    parameters = create_odin_parameters(response)
    assert len(parameters) == 96


def test_two_node():
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    parameters = create_odin_parameters(response)
    assert len(parameters) == 188
