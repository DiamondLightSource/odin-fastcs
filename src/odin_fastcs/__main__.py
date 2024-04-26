from typing import Optional

import typer
from fastcs.backends.asyncio_backend import AsyncioBackend
from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.mapping import Mapping

from odin_fastcs.odin_controller import (
    FPOdinController,
    OdinTopController,
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


@app.command()
def ioc(pv_prefix: str = typer.Argument()):
    from fastcs.backends.epics.backend import EpicsBackend

    mapping = get_controller_mapping()

    backend = EpicsBackend(mapping, pv_prefix)
    backend.create_gui()
    backend.get_ioc().run()


@app.command()
def asyncio():
    mapping = get_controller_mapping()

    backend = AsyncioBackend(mapping)
    backend.run_interactive_session()


def get_controller_mapping() -> Mapping:
    controller = OdinTopController()
    # fr_controller = FROdinController(IPConnectionSettings("127.0.0.1", 8888))
    # controller.register_sub_controller(fr_controller)
    fp_controller = FPOdinController(IPConnectionSettings("127.0.0.1", 8888))
    controller.register_sub_controller(fp_controller)
    # ml_controller = MLOdinController(IPConnectionSettings("127.0.0.1", 8888))
    # controller.register_sub_controller(ml_controller)

    return Mapping(controller)


# test with: python -m odin_fastcs
if __name__ == "__main__":
    app()
