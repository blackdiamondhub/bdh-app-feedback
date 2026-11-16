from bdh_sdk import PluginSpec
from bdh_sdk.plugins import LIFECYCLE_ON_DEMAND, NETWORK_NONE

# No tile: visitors write from the hub's top-bar pill (the hub posts the message
# here), and admins open the inbox from the owner menu.
spec = PluginSpec(
    id="feedback",
    app="feedback",
    urls="feedback.urls",
    api_version=2,
    # Only keeps its own app state (the unread count the hub shows on its badge).
    permissions=(),
    network=NETWORK_NONE,
    # The hub caches the unread count, so the app only needs to run while used.
    lifecycle=LIFECYCLE_ON_DEMAND,
    memory_mb=96,
)
