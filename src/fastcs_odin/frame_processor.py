import asyncio
import re
from collections.abc import Sequence
from functools import cached_property, partial

from fastcs.attributes import AttrR
from fastcs.datatypes import Bool, Int
from fastcs.logging import bind_logger
from fastcs.methods import Command, command
from pydantic import ValidationError

from fastcs_odin.io.status_summary_attribute_io import (
    StatusSummaryAttributeIORef,
    _filter_sub_controllers,
)
from fastcs_odin.odin_data import OdinDataAdapterController
from fastcs_odin.odin_subcontroller import OdinSubController
from fastcs_odin.util import (
    AllowedCommandsResponse,
    OdinParameter,
    create_attribute,
    partition,
    remove_metadata_fields_paths,
)

logger = bind_logger(logger_name=__name__)


class FrameProcessorController(OdinSubController):
    """Sub controller for a frame processor application."""

    async def initialise(self):
        plugins_response = await self.connection.get(
            f"{self._api_prefix}/status/plugins/names"
        )
        match plugins_response:
            case {"names": [*plugin_list]}:
                plugins = tuple(a for a in plugin_list if isinstance(a, str))
                if len(plugins) != len(plugin_list):
                    raise ValueError(f"Received invalid plugins list:\n{plugin_list}")
            case _:
                raise ValueError(
                    f"Did not find valid plugins in response:\n{plugins_response}"
                )

        self.parameters = remove_metadata_fields_paths(self.parameters)
        for parameter in self.parameters:
            # Remove duplicate index from uri
            parameter.uri = parameter.uri[1:]
            # Remove redundant status/config from parameter path
            parameter.set_path(parameter.uri[1:])

        await self._create_plugin_sub_controllers(plugins)

        for parameter in self.parameters:
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )

    async def _create_plugin_sub_controllers(self, plugins: Sequence[str]):
        for plugin in plugins:

            def __parameter_in_plugin(
                parameter: OdinParameter, plugin: str = plugin
            ) -> bool:
                return parameter.path[0] == plugin

            plugin_parameters, self.parameters = partition(
                self.parameters, __parameter_in_plugin
            )
            plugin_controller = FrameProcessorPluginController(
                self.connection,
                plugin_parameters,
                f"{self._api_prefix}",
                self._ios,
            )
            self.add_sub_controller(plugin, plugin_controller)
            await plugin_controller.initialise()


class FrameProcessorAdapterController(OdinDataAdapterController):
    frames_written: AttrR = AttrR(
        Int(),
        io_ref=StatusSummaryAttributeIORef(
            [re.compile(r"[0-9]+"), "HDF"], "frames_written", partial(sum, start=0)
        ),
    )
    writing: AttrR = AttrR(
        Bool(),
        io_ref=StatusSummaryAttributeIORef(
            [re.compile(r"[0-9]+"), "HDF"], "writing", any
        ),
    )
    _unique_config = [
        "rank",
        "number",
        "ctrl_endpoint",
        "meta_endpoint",
        "fr_ready_cnxn",
        "fr_release_cnxn",
    ]
    _subcontroller_label = "fp"
    _subcontroller_cls = FrameProcessorController

    def _collect_commands(
        self,
        path_filter: Sequence[str | tuple[str, ...] | re.Pattern],
        command_name: str,
    ):
        commands = []

        controllers = list(_filter_sub_controllers(self, path_filter))

        for controller in controllers:
            try:
                cmd = getattr(controller, command_name)
                commands.append(cmd)
            except AttributeError as err:
                raise AttributeError(
                    f"Sub controller {controller} does not have command "
                    f"'{command_name}' required by {self} command fan out {path_filter}"
                ) from err
        return commands

    @cached_property
    def _start_writing_commands(self):
        return self._collect_commands((re.compile(r"[0-9]+"), "HDF"), "start_writing")

    @cached_property
    def _stop_writing_commands(self):
        return self._collect_commands((re.compile(r"[0-9]+"), "HDF"), "stop_writing")

    @command()
    async def start_writing(self) -> None:
        await asyncio.gather(
            *(start_writing() for start_writing in self._start_writing_commands)
        )

    @command()
    async def stop_writing(self) -> None:
        await asyncio.gather(
            *(stop_writing() for stop_writing in self._stop_writing_commands)
        )


class FrameProcessorPluginController(OdinSubController):
    """SubController for a plugin in a frameProcessor application."""

    async def initialise(self):
        await self._create_commands()
        await self._create_dataset_controllers()
        for parameter in self.parameters:
            # Remove plugin name included in controller base path
            parameter.set_path(parameter.path[1:])

            # Handle clash between status and config in FileWriterPlugin
            # TODO: https://github.com/odin-detector/odin-data/issues/426
            if parameter.uri == ["status", "hdf", "file_path"]:
                parameter.set_path(["current_file_path"])
            elif parameter.uri == ["status", "hdf", "acquisition_id"]:
                parameter.set_path(["current_acquisition_id"])
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )

    async def _create_commands(self):
        plugin_name = self.path[-1].lower()
        command_response = await self.connection.get(
            f"{self._api_prefix}/command/{plugin_name}/allowed"
        )

        try:
            commands = AllowedCommandsResponse.model_validate(command_response)
            for command in commands.allowed:
                self._construct_command(command, plugin_name)
        except ValidationError:
            pass

    async def _create_dataset_controllers(self):
        if any("dataset" in p.path for p in self.parameters):

            def __dataset_parameter(param: OdinParameter):
                return "dataset" in param.path

            dataset_parameters, self.parameters = partition(
                self.parameters, __dataset_parameter
            )
                if dataset_parameters:
                dataset_controller = FrameProcessorDatasetController(
                    self.connection,
                    dataset_parameters,
                    f"{self._api_prefix}",
                    self._ios,
                )
                self.add_sub_controller("ds", dataset_controller)
                await dataset_controller.initialise()

    def _construct_command(self, command_name, plugin_name):
        async def submit_command() -> None:
            logger.info("Executing command", plugin=plugin_name, command=command_name)
            await self.connection.put(
                f"{self._api_prefix}/command/{plugin_name}/execute", command_name
            )

        setattr(self, command_name, Command(submit_command))


class FrameProcessorDatasetController(OdinSubController):
    async def initialise(self):
        for parameter in self.parameters:
            parameter.set_path(parameter.uri[3:])
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )
