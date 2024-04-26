import json
from pathlib import Path

from odin_fastcs.util import create_odin_parameters

HERE = Path(__file__).parent


def test_create_odin_parameters():
    with (HERE / "response.json").open() as f:
        response = json.loads(f.read())

    create_odin_parameters(response)
