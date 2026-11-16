# bdh-app-feedback

Black Diamond Hub app: the inbox for messages sent from the hub's top-bar
feedback pill. Installed into the hub through the `blackdiamondhub.plugins`
entry point (see [bdh-sdk](https://github.com/blackdiamondlodge/bdh-sdk)).

The app has no tile, and visitors never open it directly:

- **Sending**: the pill and its modal belong to the hub. The hub posts each
  message to the app's `submit/` URL, adding the page it was sent from (title
  and tile icon) and the stay in progress, and flags the request in the
  identity it signs. Messages that don't come from the hub's submit endpoint
  are refused.
- **Inbox**: admins open it from the owner menu (**Feedback inbox**). It lists
  every message with its page and stay; messages can be marked read or unread
  and deleted, one at a time or in bulk. Anyone else gets a 404.
- **Unread badge**: the app keeps the unread count in its app state
  (`unread_count`) and updates it on every change. The hub reads it from there
  for the badge, so the app doesn't need to be running for the count to show.

The manifest asks for no permissions and no network access.

## Moving a site from the built-in feedback app

Hubs used to ship feedback as a built-in Django app. The model here has the
same fields (plus the page's title and icon), so its rows import as they are:

1. On the hub (with its usual `DJANGO_SETTINGS_MODULE`), export the built-in
   rows: `python -m bdh_sdk.appdata export feedback -o feedback.json`.
2. Install this app on the site (`sites/<site>/apps.txt`) and turn the
   built-in one off (`feedback = false` under `[features]` in `site.toml`).
3. Copy `feedback.json` into the app's data volume and load it:
   `python -m bdh_sdk.runtime.manage import_app_data /data/feedback.json`.
   The import updates the unread badge.

Imported rows have no page title or icon; the inbox shows "Home" or the page's
path instead.

## Development

CI (`.github/workflows/ci.yml`) uses the reusable `app-ci.yml` from
bdh-sdk. It builds the wheel, installs it next to the hub, then runs
`hub_smoke` and the app tests.

To release, bump `version` in `pyproject.toml`. When that lands on
`main`, `release.yml` tags it and publishes the wheel, and the release
notes include the hashed line for the hub's `sites/<site>/apps.txt`.
