"""The apollo_tab websocket commands."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import probatio
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .live import CallError, CardSubscription, async_call_output, json_safe
from .tablets import async_get_tablets

if TYPE_CHECKING:
    from . import ApolloTabData

# Card subscriptions per websocket connection.
MAX_CARD_SUBSCRIPTIONS = 100


def _loaded_data(
    hass: HomeAssistant, connection: ActiveConnection, msg_id: int
) -> ApolloTabData | None:
    """Return the loaded entry's data, or send the not_loaded error."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_error(msg_id, "not_loaded", "The integration is not loaded")
        return None
    return entries[0].runtime_data


class _ListenerSubscription:
    """Hold one library or layout listener until unsubscribe or unload."""

    def __init__(
        self,
        data: ApolloTabData,
        connection: ActiveConnection,
        msg_id: int,
        remover: Callable[[], None],
    ) -> None:
        """Store the remover and register with the entry's subscriptions."""
        self._data = data
        self._connection = connection
        self._msg_id = msg_id
        self._remover: Callable[[], None] | None = remover
        data.subscriptions.add(self)

    @callback
    def async_stop(self) -> None:
        """Remove the listener, at most once."""
        if self._remover is None:
            return
        remover = self._remover
        self._remover = None
        remover()
        self._data.subscriptions.discard(self)

    @callback
    def async_unload(self) -> None:
        """Stop and tell the subscriber, which has to subscribe again."""
        if self._remover is None:
            return
        self.async_stop()
        # After a reload the library and the manager are new objects, so
        # this subscription can never report another change.
        self._connection.send_message(
            websocket_api.event_message(self._msg_id, {"type": "not_loaded"})
        )


@websocket_api.websocket_command({probatio.Required("type"): "apollo_tab/strings"})
@websocket_api.async_response
async def websocket_strings(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the UI strings."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    connection.send_result(msg["id"], {"strings": data.library.strings})


@websocket_api.require_admin
@websocket_api.websocket_command({probatio.Required("type"): "apollo_tab/library"})
@websocket_api.async_response
async def websocket_library(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the component library."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    connection.send_result(msg["id"], json_safe(data.library.as_dict()))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {probatio.Required("type"): "apollo_tab/library/subscribe"}
)
@websocket_api.async_response
async def websocket_library_subscribe(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send a changed event after every library reload or allowance change.

    A last not_loaded event follows when the integration is unloaded.
    """
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return

    @callback
    def forward() -> None:
        """Forward a library change as an event."""
        connection.send_message(
            websocket_api.event_message(msg["id"], {"type": "changed"})
        )

    subscription = _ListenerSubscription(
        data, connection, msg["id"], data.library.async_listen(forward)
    )
    connection.subscriptions[msg["id"]] = subscription.async_stop
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {probatio.Required("type"): "apollo_tab/library/reload"}
)
@websocket_api.async_response
async def websocket_library_reload(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Reload the library and return the component and error counts."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    await data.library.async_load()
    connection.send_result(
        msg["id"],
        {
            "components": len(data.library.components),
            "errors": len(data.library.errors),
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apollo_tab/library/approve",
        probatio.Required("component_id"): str,
        probatio.Required("approved"): bool,
    }
)
@websocket_api.async_response
async def websocket_library_approve(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Approve or reject a component."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    component_id = msg["component_id"]
    try:
        await data.library.async_set_approved(component_id, msg["approved"])
    except KeyError:
        connection.send_error(
            msg["id"], "not_found", f"Unknown component {component_id}"
        )
        return
    connection.send_result(
        msg["id"], {"approved": data.library.is_approved(component_id)}
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apollo_tab/card/subscribe",
        probatio.Required("card"): dict,
        probatio.Optional("dashboard"): probatio.Any(str, None),
    }
)
@websocket_api.async_response
async def websocket_card_subscribe(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Subscribe to a card's compiled form and live values."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    count = sum(
        1
        for subscription in data.subscriptions
        if isinstance(subscription, CardSubscription)
        and subscription.connection is connection
    )
    if count >= MAX_CARD_SUBSCRIPTIONS:
        connection.send_error(
            msg["id"],
            "too_many_subscriptions",
            f"At most {MAX_CARD_SUBSCRIPTIONS} card subscriptions per connection",
        )
        return
    subscription = CardSubscription(hass, data, connection, msg)
    connection.subscriptions[msg["id"]] = subscription.async_stop
    connection.send_result(msg["id"])
    await subscription.async_start()


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apollo_tab/card/call",
        probatio.Required("card"): dict,
        probatio.Required("widget"): int,
        probatio.Required("event"): probatio.In(["tap", "change"]),
        probatio.Optional("value"): probatio.Any(bool, int, float, str),
        probatio.Optional("confirmed", default=False): bool,
    }
)
@websocket_api.async_response
async def websocket_card_call(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Run one of a card's outputs."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    try:
        await async_call_output(hass, data, connection, msg)
    except CallError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.require_admin
@websocket_api.websocket_command({probatio.Required("type"): "apollo_tab/dashboards"})
@websocket_api.async_response
async def websocket_dashboards(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the TAB-1 dashboards and the tablet count."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    dashboards = [
        {
            "url_path": url_path,
            "title": stored["title"],
            "mode": stored["mode"],
            "theme": stored["theme"],
            "pages": len(stored["layout"]["pages"]),
            "warnings": len(stored["warnings"]),
            "hash": stored["layout"]["hash"],
        }
        for url_path, stored in sorted(data.manager.layouts.items())
    ]
    connection.send_result(
        msg["id"],
        {
            "dashboards": dashboards,
            "tablets": len(async_get_tablets(hass)),
            "sent_to_tablets": False,
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apollo_tab/layout/get",
        probatio.Required("url_path"): str,
    }
)
@websocket_api.async_response
async def websocket_layout_get(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return one dashboard's stored layout and current slot values."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    stored = data.manager.layouts.get(msg["url_path"])
    if stored is None:
        connection.send_error(msg["id"], "not_found", "Unknown dashboard")
        return
    values = await data.manager.async_values(msg["url_path"])
    connection.send_result(
        msg["id"],
        {
            "url_path": msg["url_path"],
            "layout": json_safe(stored["layout"]),
            "warnings": json_safe(stored["warnings"]),
            "values": json_safe(values),
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {probatio.Required("type"): "apollo_tab/layout/subscribe"}
)
@websocket_api.async_response
async def websocket_layout_subscribe(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send converted and removed events for the dashboards.

    A last not_loaded event follows when the integration is unloaded.
    """
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return

    @callback
    def forward(kind: str, url_path: str) -> None:
        """Forward a manager event as an event message."""
        if kind == "converted":
            stored = data.manager.layouts.get(url_path)
            payload: dict[str, Any] = {
                "type": "converted",
                "url_path": url_path,
                "hash": stored["layout"]["hash"] if stored else "",
                "warnings": len(stored["warnings"]) if stored else 0,
            }
        else:
            payload = {"type": "removed", "url_path": url_path}
        connection.send_message(websocket_api.event_message(msg["id"], payload))

    subscription = _ListenerSubscription(
        data, connection, msg["id"], data.manager.async_listen(forward)
    )
    connection.subscriptions[msg["id"]] = subscription.async_stop
    connection.send_result(msg["id"])


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the ten commands of the websocket API."""
    websocket_api.async_register_command(hass, websocket_strings)
    websocket_api.async_register_command(hass, websocket_library)
    websocket_api.async_register_command(hass, websocket_library_subscribe)
    websocket_api.async_register_command(hass, websocket_library_reload)
    websocket_api.async_register_command(hass, websocket_library_approve)
    websocket_api.async_register_command(hass, websocket_card_subscribe)
    websocket_api.async_register_command(hass, websocket_card_call)
    websocket_api.async_register_command(hass, websocket_dashboards)
    websocket_api.async_register_command(hass, websocket_layout_get)
    websocket_api.async_register_command(hass, websocket_layout_subscribe)
