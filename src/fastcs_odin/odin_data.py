import logging
from collections.abc import Sequence

from fastcs.attributes import AttributeIO, AttributeIORefT, AttrW
from fastcs.controllers import ControllerVector
from fastcs.datatypes import DType_T

from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.io.config_fan_sender_attribute_io import ConfigFanAttributeIORef
from fastcs_odin.io.status_summary_attribute_io import initialise_summary_attributes
from fastcs_odin.odin_subcontroller import OdinSubController
from fastcs_odin.util import (
    OdinParameter,
    create_attribute,
    get_all_sub_controllers,
    partition,
)


class OdinDataAdapterController(ControllerVector):
    """Sub controller for the frame processor adapter in an odin control server."""

    _unique_config: list[str] = []
    _subcontroller_label: str = "od"
    _subcontroller_cls: type[OdinSubController] = OdinSubController

    def __init__(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        api_prefix: str,
        ios: Sequence[AttributeIO[DType_T, AttributeIORefT]],
    ):
        """
        Args:
            connection: HTTP connection to communicate with odin server
            parameters: The parameters in the adapter
            api_prefix: The base URL of this adapter in the odin server API

        """
        super().__init__(ios=ios, children={})

        self.connection = connection
        self.parameters = parameters
        self._api_prefix = api_prefix
        self._ios = ios

    async def initialise(self):
        idx_parameters, self.parameters = partition(
            self.parameters, lambda p: p.uri[0].isdigit()
        )

        while idx_parameters:
            idx = idx_parameters[0].uri[0]
            fp_parameters, idx_parameters = partition(
                idx_parameters, lambda p, idx=idx: p.uri[0] == idx
            )

            adapter_controller = self._subcontroller_cls(
                self.connection,
                fp_parameters,
                f"{self._api_prefix}/{idx}",
                self._ios,
            )
            self[int(idx)] = adapter_controller
            await adapter_controller.initialise()

        for parameter in self.parameters:
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )
        self._create_config_fan_attributes()
        initialise_summary_attributes(self)

    def _create_config_fan_attributes(self):
        """Search for config attributes in sub controllers to create fan out PVs."""
        parameter_attribute_map: dict[str, tuple[OdinParameter, list[AttrW]]] = {}
        for sub_controller in get_all_sub_controllers(self):
            match sub_controller:
                case OdinSubController():
                    for parameter in sub_controller.parameters:
                        mode, key = parameter.uri[0], parameter.uri[-1]
                        if mode == "config" and key not in self._unique_config:
                            try:
                                attr: AttrW = sub_controller.attributes[parameter.name]  # type: ignore
                                if parameter.name not in parameter_attribute_map:
                                    parameter_attribute_map[parameter.name] = (
                                        parameter,
                                        [attr],
                                    )
                                else:
                                    parameter_attribute_map[parameter.name][1].append(
                                        attr
                                    )
                            except KeyError:
                                logging.warning(
                                    f"Controller has parameter {parameter}, "
                                    f"but no corresponding attribute {parameter.name}"
                                )
                case _:
                    logging.warning(
                        f"Subcontroller {sub_controller} not an OdinAdapterController"
                    )

        for parameter, sub_attributes in parameter_attribute_map.values():
            self.add_attribute(
                parameter.name,
                sub_attributes[0].__class__(
                    sub_attributes[0].datatype,
                    group=sub_attributes[0].group,
                    io_ref=ConfigFanAttributeIORef(sub_attributes),
                ),
            )
