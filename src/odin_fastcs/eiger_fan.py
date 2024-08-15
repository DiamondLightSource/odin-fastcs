from fastcs.attributes import AttrRW
from fastcs.datatypes import String

from odin_fastcs.odin_adapter_controller import OdinAdapterController, ParamTreeHandler


class EigerFanAdapterController(OdinAdapterController):
    """SubController for an eigerfan adapter in an odin control server."""

    acquisition_id: AttrRW = AttrRW(
        String(), handler=ParamTreeHandler("api/0.1/ef/0/config/acqid")
    )
