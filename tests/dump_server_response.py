import json
from pathlib import Path
from typing import Annotated

import requests
import typer

from fastcs_odin.odin_controller import REQUEST_METADATA_HEADER

HERE = Path(__file__).parent


def main(
    url: Annotated[
        str, typer.Argument(help="Root URL of Odin server")
    ] = "127.0.0.1:8888",
    output: Annotated[Path, typer.Option(help="Output directory")] = HERE / "input",
    prefix: Annotated[str, typer.Option(help="Prefix for files")] = "",
    adapter: Annotated[str, typer.Option(help="Only dump this adapter")] = "",
):
    """Dump Odin server adapter parameter trees to file."""
    if not url.startswith("http://"):
        url = f"http://{url}"

    if adapter:
        adapters = [adapter]
    else:
        adapters = requests.get(f"{url}/api/0.1/adapters").json()["adapters"]

    for adapter in adapters:
        try:
            adapter_tree = requests.get(
                f"{url}/api/0.1/{adapter}", headers=REQUEST_METADATA_HEADER
            ).json()
        except Exception as e:
            print(f"Failed to get paramter tree for {adapter}: {e.__class__.__name__}")
            continue

        with (output / f"{prefix}{adapter}_response.json").open(mode="w") as f:
            f.write(json.dumps(adapter_tree, indent=4))


if __name__ == "__main__":
    typer.run(main)
