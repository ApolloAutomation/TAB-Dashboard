"""The apollo_tab websocket commands."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import probatio
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant, callback

from .assignments import (
    APPROVAL_NEEDED,
    ApprovalNeeded,
    async_show_dashboard,
    dashboard_order,
)
from .const import DOMAIN
from .live import CallError, CardSubscription, async_call_output, json_safe

if TYPE_CHECKING:
    from . import ApolloTabData

_LOGGER = logging.getLogger(__name__)

# Card subscriptions per websocket connection.
MAX_CARD_SUBSCRIPTIONS = 100

# The answer to a change of a tablet that waits for an admin, other than the
# panel's "Turn on with this dashboard", and to pairing such a tablet. It
# quotes the button and ends in a full stop, as the panel's own texts do.
NOT_APPROVED = (
    "This tablet is new. Pick a dashboard for it on the Home screen, "
    'then press "Turn on with this dashboard".'
)


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
    """List the TAB-1 dashboards in the one order, with the tablets on each."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    sender = data.sender
    dashboards = []
    for item in dashboard_order(data.manager):
        url_path = item["url_path"]
        stored = data.manager.layouts[url_path]
        dashboards.append(
            {
                "url_path": url_path,
                "title": stored["title"],
                "mode": stored["mode"],
                "theme": stored["theme"],
                "pages": len(stored["layout"]["pages"]),
                "warnings": len(stored["warnings"]),
                "hash": stored["layout"]["hash"],
                "shown_on": [
                    mac
                    for mac in data.assignments.shown_on(url_path)
                    if mac in sender.sessions and sender.sessions[mac].approved
                ],
            }
        )
    connection.send_result(
        msg["id"],
        {
            "dashboards": dashboards,
            # Dashboards that tablets show but that cannot be read right
            # now, with the last title Home Assistant has for each.
            "unreadable": data.assignments.unreadable_dashboards(),
            # Tablets that wait for an admin show nothing and are not counted.
            "tablets": sum(1 for s in sender.sessions.values() if s.approved),
            "sent_to_tablets": sender.any_on_tablet(),
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command({probatio.Required("type"): "apollo_tab/tablets"})
@websocket_api.async_response
async def websocket_tablets(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the tablets with what each one shows and its status."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    connection.send_result(msg["id"], {"tablets": data.sender.tablets_json()})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {probatio.Required("type"): "apollo_tab/tablets/subscribe"}
)
@websocket_api.async_response
async def websocket_tablets_subscribe(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the tablet list at once and again after every change.

    A last not_loaded event follows when the integration is unloaded.
    """
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return

    @callback
    def forward() -> None:
        """Send the whole tablet list as an event."""
        connection.send_message(
            websocket_api.event_message(
                msg["id"], {"type": "tablets", "tablets": data.sender.tablets_json()}
            )
        )

    subscription = _ListenerSubscription(
        data, connection, msg["id"], data.sender.async_listen(forward)
    )
    connection.subscriptions[msg["id"]] = subscription.async_stop
    connection.send_result(msg["id"])
    forward()


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apollo_tab/tablet/assign",
        probatio.Required("mac"): str,
        probatio.Required("url_path"): str,
        # Sent only by the panel's "Turn on with this dashboard".
        probatio.Optional("approve", default=False): bool,
    }
)
@websocket_api.async_response
async def websocket_tablet_assign(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Choose the dashboard a tablet shows; sending starts at once.

    For a new tablet, with approve true, this is the admin's approval: from
    now on Home Assistant trusts it, pairs it and sends it its dashboard.
    Without approve a new tablet is refused, so a screen that still shows
    it as turned on (the editor's "Show this dashboard", a turned-on row's
    list) never turns it on without the button and the check of its name.
    """
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    session = data.sender.session_for(msg["mac"])
    if session is None:
        connection.send_error(msg["id"], "not_found", "This tablet is not known")
        return
    if not session.approved and not msg["approve"]:
        connection.send_error(msg["id"], "not_approved", NOT_APPROVED)
        return
    if msg["url_path"] not in data.manager.layouts:
        connection.send_error(
            msg["id"], "unknown_dashboard", "This dashboard does not exist"
        )
        return
    try:
        await async_show_dashboard(
            hass,
            data.assignments,
            session.mac,
            msg["url_path"],
            session.entry_id,
            connection.context(msg),
        )
    except ApprovalNeeded:
        # An admin who is no person (the Supervisor's user, which add-ons
        # use) asked to turn a new tablet on.
        connection.send_error(msg["id"], "approval_needed", APPROVAL_NEEDED)
        return
    connection.send_result(msg["id"], {"tablet": data.sender.tablet_json(session)})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        probatio.Required("type"): "apollo_tab/tablet/pair",
        probatio.Required("mac"): str,
    }
)
@websocket_api.async_response
async def websocket_tablet_pair(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Give a tablet a new secret, now or within a minute."""
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    session = data.sender.session_for(msg["mac"])
    if session is None:
        connection.send_error(msg["id"], "not_found", "This tablet is not known")
        return
    if not session.approved:
        # A tablet no admin approved is never paired.
        connection.send_error(msg["id"], "not_approved", NOT_APPROVED)
        return
    session.request_pair()
    connection.send_result(msg["id"], {"tablet": data.sender.tablet_json(session)})


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
    {
        probatio.Required("type"): "apollo_tab/layout/preview",
        probatio.Required("config"): dict,
    }
)
@websocket_api.async_response
async def websocket_layout_preview(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Convert an unsaved dashboard config and return what a tablet would show.

    Nothing is stored, so the editor can preview a draft before it is saved.
    """
    if (data := _loaded_data(hass, connection, msg["id"])) is None:
        return
    try:
        preview = await data.manager.async_preview(msg["config"])
    except Exception:
        _LOGGER.exception("Preview conversion failed")
        connection.send_error(
            msg["id"], "conversion_failed", "The dashboard could not be converted"
        )
        return
    connection.send_result(
        msg["id"],
        {
            "layout": json_safe(preview["layout"]),
            "warnings": json_safe(preview["warnings"]),
            "values": json_safe(preview["values"]),
            "sources": json_safe(preview["sources"]),
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
    """Send converted, removed and renamed events for the dashboards.

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
        elif kind in ("removed", "renamed"):
            payload = {"type": kind, "url_path": url_path}
        else:
            return
        connection.send_message(websocket_api.event_message(msg["id"], payload))

    subscription = _ListenerSubscription(
        data, connection, msg["id"], data.manager.async_listen(forward)
    )
    connection.subscriptions[msg["id"]] = subscription.async_stop
    connection.send_result(msg["id"])


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the fifteen commands of the websocket API."""
    websocket_api.async_register_command(hass, websocket_strings)
    websocket_api.async_register_command(hass, websocket_library)
    websocket_api.async_register_command(hass, websocket_library_subscribe)
    websocket_api.async_register_command(hass, websocket_library_reload)
    websocket_api.async_register_command(hass, websocket_library_approve)
    websocket_api.async_register_command(hass, websocket_card_subscribe)
    websocket_api.async_register_command(hass, websocket_card_call)
    websocket_api.async_register_command(hass, websocket_dashboards)
    websocket_api.async_register_command(hass, websocket_layout_get)
    websocket_api.async_register_command(hass, websocket_layout_preview)
    websocket_api.async_register_command(hass, websocket_layout_subscribe)
    websocket_api.async_register_command(hass, websocket_tablets)
    websocket_api.async_register_command(hass, websocket_tablets_subscribe)
    websocket_api.async_register_command(hass, websocket_tablet_assign)
    websocket_api.async_register_command(hass, websocket_tablet_pair)
