from collections.abc import Mapping

from aiohttp import ClientResponse, ClientSession

ValueType = bool | int | float | str
JsonElementary = str | int | float | bool | None
JsonType = JsonElementary | list[JsonElementary] | Mapping[str, JsonElementary]


class HTTPConnection:
    def __init__(self, ip: str, port: int):
        self._session: ClientSession | None = None
        self._ip = ip
        self._port = port

    def full_url(self, uri: str) -> str:
        """Expand IP address, port and URI into full URL.

        Args:
            uri: Identifier for a resource for the current connection

        """
        return f"http://{self._ip}:{self._port}/{uri}"

    def open(self):
        """Create the underlying aiohttp ClienSession.

        When called the session will be created in the context of the current running
        asyncio loop.

        """
        self._session = ClientSession()

    def get_session(self) -> ClientSession:
        """Get session or raise exception if session is not open.

        Returns: Current aiohttp session if connection is open

        Raises: ConnectionRefusedError if the connection is not open

        """
        if self._session is not None:
            return self._session

        raise ConnectionRefusedError("Session is not open")

    async def get(self, uri: str, headers: dict | None = None) -> JsonType:
        """Perform HTTP GET request and return response content as JSON.

        Args:
            uri: Identifier for resource

        Returns: Response payload as JSON

        """
        session = self.get_session()
        async with session.get(self.full_url(uri), headers=headers) as response:
            return await response.json()

    async def get_bytes(self, uri: str) -> tuple[ClientResponse, bytes]:
        """Perform HTTP GET request and return response content as bytes.

        Args:
            uri: Identifier for resource

        Returns: ClientResponse header and response payload as bytes

        """
        session = self.get_session()
        async with session.get(self.full_url(uri)) as response:
            return response, await response.read()

    async def put(self, uri: str, value: ValueType) -> JsonType:
        """Perform HTTP PUT request and return response content as json.

        If successful, the response is a list of parameters whose values may have
        changed as a result of the change.

        Args:
            uri: Identifier for resource

        Returns: ClientResponse header and response payload as bytes

        """
        session = self.get_session()
        async with session.put(
            self.full_url(uri),
            json=value,
            headers={"Content-Type": "application/json"},
        ) as response:
            return await response.json()

    async def close(self):
        """Close the underlying aiohttp ClientSession."""
        session = self.get_session()
        await session.close()
        self._session = None
