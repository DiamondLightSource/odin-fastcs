import re
from collections.abc import Iterable, Sequence

from fastcs.attributes import AttrR, AttrW
from fastcs.controller import BaseController, SubController
from fastcs.datatypes import Bool, Int

from odin_fastcs.odin_adapter_controller import (
    ConfigFanSender,
    OdinAdapterController,
    StatusSummaryUpdater,
)
from odin_fastcs.util import OdinParameter, partition

UNIQUE_FP_CONFIG = [
    "rank",
    "number",
    "ctrl_endpoint",
    "meta_endpoint",
    "fr_ready_cnxn",
    "fr_release_cnxn",
]


class FrameProcessorAdapterController(OdinAdapterController):
    """Sub controller for the frame processor adapter in an odin control server."""

    frames_written: AttrR = AttrR(
        Int(),
        handler=StatusSummaryUpdater([re.compile("FP*"), "HDF"], "frames_written", sum),
    )
    writing: AttrR = AttrR(
        Bool(),
        handler=StatusSummaryUpdater([re.compile("FP*"), "HDF"], "writing", any),
    )

    async def initialise(self):
        idx_parameters, self._parameters = partition(
            self._parameters, lambda p: p.uri[0].isdigit()
        )

        while idx_parameters:
            idx = idx_parameters[0].uri[0]
            fp_parameters, idx_parameters = partition(
                idx_parameters, lambda p, idx=idx: p.uri[0] == idx
            )

            adapter_controller = FrameProcessorController(
                self._connection,
                fp_parameters,
                f"{self._api_prefix}/{idx}",
            )
            self.register_sub_controller(f"FP{idx}", adapter_controller)
            await adapter_controller.initialise()

        self._create_attributes()
        self._create_config_fan_attributes()

    def _create_config_fan_attributes(self):
        """Search for config attributes in sub controllers to create fan out PVs."""
        parameter_attribute_map: dict[str, tuple[OdinParameter, list[AttrW]]] = {}
        for sub_controller in get_all_sub_controllers(self):
            for parameter in sub_controller._parameters:
                mode, key = parameter.uri[0], parameter.uri[-1]
                if mode == "config" and key not in UNIQUE_FP_CONFIG:
                    try:
                        attr = getattr(sub_controller, parameter.name)
                    except AttributeError:
                        print(
                            f"Controller has parameter {parameter}, "
                            f"but no corresponding attribute {parameter.name}"
                        )

                    if parameter.name not in parameter_attribute_map:
                        parameter_attribute_map[parameter.name] = (parameter, [attr])
                    else:
                        parameter_attribute_map[parameter.name][1].append(attr)

        for parameter, sub_attributes in parameter_attribute_map.values():
            setattr(
                self,
                parameter.name,
                sub_attributes[0].__class__(
                    sub_attributes[0]._datatype,
                    group=sub_attributes[0].group,
                    handler=ConfigFanSender(sub_attributes),
                ),
            )


class FrameProcessorController(OdinAdapterController):
    """Sub controller for a frame processor application."""

    async def initialise(self):
        plugins_response = await self._connection.get(
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

        self._process_parameters()
        await self._create_plugin_sub_controllers(plugins)
        self._create_attributes()

    def _process_parameters(self):
        for parameter in self._parameters:
            # Remove duplicate index from uri
            parameter.uri = parameter.uri[1:]
            # Remove redundant status/config from parameter path
            parameter.set_path(parameter.uri[1:])

    async def _create_plugin_sub_controllers(self, plugins: Sequence[str]):
        for plugin in plugins:

            def __parameter_in_plugin(
                parameter: OdinParameter, plugin: str = plugin
            ) -> bool:
                return parameter.path[0] == plugin

            plugin_parameters, self._parameters = partition(
                self._parameters, __parameter_in_plugin
            )
            plugin_controller = FrameProcessorPluginController(
                self._connection,
                plugin_parameters,
                f"{self._api_prefix}",
            )
            self.register_sub_controller(plugin.upper(), plugin_controller)
            await plugin_controller.initialise()


class FrameProcessorPluginController(OdinAdapterController):
    """SubController for a plugin in a frameProcessor application."""

    def _process_parameters(self):
        for parameter in self._parameters:
            # Remove plugin name included in controller base path
            parameter.set_path(parameter.path[1:])


def get_all_sub_controllers(
    controller: "OdinAdapterController",
) -> list["OdinAdapterController"]:
    return list(_walk_sub_controllers(controller))


def _walk_sub_controllers(controller: BaseController) -> Iterable[SubController]:
    for sub_controller in controller.get_sub_controllers().values():
        yield sub_controller
        yield from _walk_sub_controllers(sub_controller)
