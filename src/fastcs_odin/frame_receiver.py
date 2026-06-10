from fastcs_odin.odin_data import OdinDataAdapterController
from fastcs_odin.odin_subcontroller import OdinSubController
from fastcs_odin.util import (
    OdinParameter,
    create_attribute,
    partition,
    remove_metadata_fields_paths,
)


class FrameReceiverController(OdinSubController):
    async def initialise(self):
        def __decoder_parameter(parameter: OdinParameter):
            return "decoder" in parameter.path[:-1]

        self.parameters = remove_metadata_fields_paths(self.parameters)

        decoder_parameters, self.parameters = partition(
            self.parameters, __decoder_parameter
        )
        decoder_controller = FrameReceiverDecoderController(
            self.connection, decoder_parameters, f"{self._api_prefix}", self._ios
        )
        self.add_sub_controller("decoder", decoder_controller)
        await decoder_controller.initialise()

        for parameter in self.parameters:
            # Remove duplicate index from uri
            parameter.uri = parameter.uri[1:]
            # Remove redundant status/config from parameter path
            parameter.set_path(parameter.uri[1:])
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )


class FrameReceiverAdapterController(OdinDataAdapterController):
    _subcontroller_label = "fr"
    _subcontroller_cls = FrameReceiverController
    _unique_config = [
        "rank",
        "number",
        "ctrl_endpoint",
        "fr_ready_cnxn",
        "fr_release_cnxn",
        "frame_ready_endpoint",
        "frame_release_endpoint",
        "shared_buffer_name",
        "rx_address",
        "rx_ports",
    ]


class FrameReceiverDecoderController(OdinSubController):
    async def initialise(self):
        for parameter in self.parameters:
            # remove redundant status/decoder part from path
            parameter.set_path(parameter.uri[3:])
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )
