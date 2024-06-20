from pathlib import Path
from typing import Optional

import typer
from fastcs.backends.asyncio_backend import AsyncioBackend
from fastcs.backends.epics.gui import EpicsGUIOptions
from fastcs.connections.ip_connection import IPConnectionSettings

from odin_fastcs.odin_controller import (
    OdinController,
)

from . import __version__

__all__ = ["main"]


app = typer.Typer()


def version_callback(value: bool):
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    # TODO: typer does not support `bool | None` yet
    # https://github.com/tiangolo/typer/issues/533
    version: Optional[bool] = typer.Option(  # noqa
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Print the version and exit",
    ),
):
    pass


OdinIp = typer.Option("127.0.0.1", help="IP address of odin server")
OdinPort = typer.Option(8888, help="Port of odin server")


@app.command()
def ioc(pv_prefix: str = typer.Argument(), ip: str = OdinIp, port: int = OdinPort):
    from fastcs.backends.epics.backend import EpicsBackend

    controller = OdinController(IPConnectionSettings(ip, port))

    backend = EpicsBackend(controller, pv_prefix)
    backend.create_gui(
        options=EpicsGUIOptions(
            output_path=Path.cwd() / "odin.bob", title=f"Odin - {pv_prefix}"
        )
    )
    backend.run()


@app.command()
def asyncio(ip: str = OdinIp, port: int = OdinPort):
    controller = OdinController(IPConnectionSettings(ip, port))

    backend = AsyncioBackend(controller)
    backend.run()


# test with: python -m odin_fastcs
if __name__ == "__main__":
    app()
