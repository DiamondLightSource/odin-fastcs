import asyncio
import re
from collections.abc import Sequence
from functools import cached_property, partial
from pathlib import Path

from fastcs.attributes import AttrR, AttrRW
from fastcs.datatypes import Bool, Int
from fastcs.methods import command

from fastcs_odin.controllers.odin_data._generate_vds import VDSGenerator
from fastcs_odin.controllers.odin_data.odin_data_adapter import (
    OdinDataAdapterController,
)
from fastcs_odin.controllers.odin_subcontroller import OdinSubController
from fastcs_odin.io.status_summary_attribute_io import (
    StatusSummaryAttributeIORef,
    _filter_sub_controllers,
)
from fastcs_odin.util import OdinParameter, create_attribute, partition


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
    """Controller for a frame processor adapter"""

    file_path: AttrRW[str]
    file_prefix: AttrRW[str]
    acquisition_id: AttrRW[str]
    process_frames_per_block: AttrRW[int]
    process_blocks_per_file: AttrRW[int]
    frames: AttrR[int]
    data_datatype: AttrRW[str]
    data_dims_0: AttrR[int]  # y
    data_dims_1: AttrR[int]  # x
    enable_vds_creation = AttrRW(Bool())

    frames_written = AttrR(
        Int(),
        io_ref=StatusSummaryAttributeIORef(
            [re.compile(r"[0-9]+"), "hdf"], "frames_written", partial(sum, start=0)
        ),
    )
    writing = AttrR(
        Bool(),
        io_ref=StatusSummaryAttributeIORef(
            [re.compile(r"[0-9]+"), "hdf"], "writing", any
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
        return self._collect_commands((re.compile(r"[0-9]+"), "hdf"), "start_writing")

    @cached_property
    def _stop_writing_commands(self):
        return self._collect_commands((re.compile(r"[0-9]+"), "hdf"), "stop_writing")

    def _create_vds(self):
        if self.enable_vds_creation.get():
            self.vds.create_interleave_vds(
                datasets=["data", "data2", "data3"],
                frame_count=self.frames_written.get(),
                frames_per_block=self.process_frames_per_block.get(),
                blocks_per_file=self.process_blocks_per_file.get(),
                frame_shape=(
                    self.data_dims_0.get(),
                    self.data_dims_1.get(),
                ),
                dtype=self.data_datatype.get(),
            )

    def _instantiate_vds_generator(self):
        self.vds = VDSGenerator(
            path=Path(self.file_path.get()), prefix=self.file_prefix.get()
        )

    @command()
    async def start_writing(self) -> None:
        self._instantiate_vds_generator()
        await asyncio.gather(
            *(start_writing() for start_writing in self._start_writing_commands)
        )

    @command()
    async def stop_writing(self) -> None:
        self._create_vds()
        await asyncio.gather(
            *(stop_writing() for stop_writing in self._stop_writing_commands)
        )


class FrameProcessorPluginController(OdinSubController):
    """Controller for a plugin in a frameProcessor application."""

    async def initialise(self):
        for parameter in self.parameters:
            # Remove plugin name included in controller base path
            parameter.set_path(parameter.path[1:])

            # Handle clash between status and config in FileWriterPlugin
            # TODO: https://github.com/odin-detector/odin-data/issues/426
            if parameter.uri == ["status", "hdf", "file_path"]:
                parameter.set_path(["current_file_path"])
            elif parameter.uri == ["status", "hdf", "acquisition_id"]:
                parameter.set_path(["current_acquisition_id"])
            elif parameter.uri[:2] == ["status", "blosc"]:
                # TODO: https://github.com/odin-detector/odin-data/issues/426
                continue

            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )

        plugin_name = self.path[-1].lower()
        await self._create_commands([plugin_name])

        await self._create_dataset_controllers()

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
                self.add_sub_controller("DS", dataset_controller)
                await dataset_controller.initialise()


class FrameProcessorDatasetController(OdinSubController):
    """Controller for datasets in the HDF plugin of a frameProcessor application"""

    async def initialise(self):
        for parameter in self.parameters:
            parameter.set_path(parameter.uri[3:])
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )
