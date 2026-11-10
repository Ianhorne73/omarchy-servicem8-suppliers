# Supplier Quick Access for Omarchy

**Required: the ServiceM8 Suppliers add-on must be installed and enabled in your ServiceM8 account.** Activate it in **Account → Features & Integrations → Suppliers** before using this plugin.

A searchable ServiceM8 supplier directory in your Omarchy bar. Open the parcel icon to find a supplier by name, email, phone, address, account or business number.

- Email opens a draft in your default mail app.
- Right-click Email to copy the address. Copy copies the whole card, including the phone number.
- Map opens the stored address in Google Maps, including addresses saved across multiple lines.
- Website opens a stored website when available. Search web searches Google using the supplier name and address; results are not verified supplier websites.
- Displays available account numbers, business numbers, addresses and notes.
- Matches the My Jobs Today plugin’s font, buttons and cards, with Omarchy theme colors, panel motion and language handling. English catalog included; missing translations fall back to English.

This is an independent integration, not an official ServiceM8 product. No ServiceM8 logos or third-party artwork are bundled.

## Requirements

Current Omarchy with Quickshell `qs.Ui.KeyboardPanel` and `qs.Commons.Translations`; Python 3.9+; xdg-utils (`xdg-open`). Install wl-clipboard for copy actions. Email requires a configured `mailto:` handler. The Suppliers add-on must be enabled in ServiceM8 and your API key must allow supplier read access. Creating, editing or deleting suppliers additionally requires supplier write access (`manage_suppliers`). The plugin sends a POST only when you press Save to ServiceM8, Save confirmed changes or Retry save, and a DELETE only after you type exactly `yes` and click Delete from ServiceM8; it never sends emails or SMS.

## Install

```sh
omarchy plugin add https://github.com/Ianhorne73/omarchy-servicem8-suppliers.git --enable
```

For a local checkout, copy the runtime files (manifest.json, BarWidget.qml, suppliers.py and i18n/) to `~/.config/omarchy/plugins/servicem8.suppliers/`, then run:

```sh
omarchy-shell shell rescanPlugins
omarchy plugin enable servicem8.suppliers --section right
```

Open the parcel icon and choose Connection. Enter your own ServiceM8 API key; it is saved only after a successful supplier fetch. If you already use My Jobs Today, its saved connection at `~/.config/omarchy/servicem8/credentials.json` is reused without copying the key. Both plugins use the same saved connection. A green dot and “Connected to ServiceM8” confirm successful access; failed refreshes show “Connection needs attention”. Older supplier-only credentials are reused when no shared key exists and migrated after successful validation. A rejected replacement leaves the previous saved key intact.

No credentials, staff names, supplier records or private account data are included in this repository or its release archive. Test contacts and keys are synthetic.

## Create a supplier

Click **New supplier**. Enter the supplier name (required), email, phone, address, account number, and ABN/business number. These map to ServiceM8’s native supplier fields. Click **Save to ServiceM8** to create the record in your connected account.

After ServiceM8 confirms creation, the plugin refreshes the directory and filters to the saved supplier. If creation succeeds but the list refresh fails, it still confirms the save and shows the new supplier, with a refresh warning. The form retains entered details on failure and offers Retry save. Closing the panel or choosing Back to suppliers keeps the form in memory; restarting the shell clears unsaved form fields.

Matching names or emails trigger a duplicate warning. Creating another requires the explicit “I have checked” checkbox. The backend also checks the current directory immediately before creating. Repeated attempts for the same fields use a stable record UUID, recorded privately in the cache. If a request times out, Retry first checks that UUID in ServiceM8 before attempting another POST. This also recovers a previous attempt after a shell restart when the same details are re-entered. There is no automatic retry or offline queue.

Website and notes are not included in the creation form because they are not documented supplier-write fields. Saving an API key does not create a supplier. No test or example suppliers are created during installation.

## Edit a supplier

Click **Edit** on a supplier card. The form is prefilled with name, email, phone, address, account number and ABN/business number. Change the details and click **Save changes**. Check the supplier name and the before/after field summary, type exactly **yes** (lowercase, without spaces), then click **Save confirmed changes**. No update is sent before this confirmation. The existing supplier is updated directly in SM8, then the plugin refreshes and displays the updated card. **Cancel edits** discards the draft and returns to the list. Changing any field, closing the panel or receiving a failed-save response clears the confirmation; saving again requires a fresh review and typed `yes`. The backend enforces the exact confirmation too.

Only changed fields are sent; clearing an optional field sends an empty value. Before saving, the plugin checks the current ServiceM8 record. If a field you changed has also changed remotely, saving stops with a conflict message and keeps your draft. Unrelated remote changes are preserved. Duplicate checks exclude the supplier being edited. Retrying a lost response recognizes already-applied changes. Permission or network failures keep your edits available for Retry save. Editing requires the same `manage_suppliers` access as creation and deletion.

## Delete a supplier

Click **Delete** on the supplier’s card. A confirmation screen shows its name, email and address. Type exactly **yes** (lowercase, without spaces), then click **Delete from ServiceM8**. The button remains disabled for any other text, and the helper independently rejects deletion without the exact confirmation. Cancel or Escape dismisses the screen; closing it, changing suppliers or retrying after an error requires fresh confirmation.

ServiceM8’s DELETE endpoint archives the supplier (`active: 0`), hiding it from its UI and the plugin’s active directory. This is not permanent erasure. On confirmation, the plugin refreshes its directory and removes the archived supplier from its private cache. A failed deletion leaves the supplier visible and shows an error. A confirmed deletion remains successful even if the subsequent refresh fails. There are no automatic DELETE retries. If the supplier was renamed since selection, refresh and select it again before deleting.

Deletion tests use mocked API responses and a synthetic desktop helper; no real suppliers are deleted during validation.

## Refresh and privacy

Opening the panel fetches suppliers when the local cache is older than 15 minutes. Refresh or right-clicking the bar icon bypasses the cache. There is no timer or background polling. The complete active supplier directory is paginated, with a safety cap of 10,000 records / 100 pages. Individual HTTPS requests time out after 15–20 seconds and reject redirects and responses larger than 4 MiB. A failed refresh preserves cached details and shows an error. Archived/deleted suppliers are excluded.

ServiceM8's documented supplier schema includes name, email, phone, address, account number and business number, but no website or notes fields. These optional fields are displayed if the API supplies them; the plugin does not invent websites from email addresses. Search web and Map send the chosen name/address to Google only when clicked. Email and website actions are handled by your chosen desktop applications.

The shared API key is plaintext, owner-only (0600), in `~/.config/omarchy/servicem8/credentials.json`. Both plugins read and update this same file. Private cache files are owner-only in `$XDG_CACHE_HOME/omarchy/servicem8-suppliers/` (default `~/.cache/...`); caches are separated by credential fingerprint. Their parent directories are 0700. Keys travel through stdin and an HTTPS header, never process arguments or logs. Network and supplier text are rendered as plain text; actions use argument arrays, never shell interpolation.

## Disable and remove

```sh
omarchy plugin disable servicem8.suppliers
omarchy plugin remove servicem8.suppliers
```

Removal leaves your connection and private cache for reinstallation. To erase them, delete only `~/.config/omarchy/servicem8-suppliers/` and `~/.cache/omarchy/servicem8-suppliers/` (or their XDG equivalents). The shared key in `~/.config/omarchy/servicem8/credentials.json` is left intact because My Jobs Today may still use it. Deleting that file disconnects both plugins.

## Development and validation

```sh
python3 -m unittest discover -v
# Optional desktop integration check (uses a synthetic helper, never the live API):
RUN_QML_INTEGRATION=1 python3 -m unittest test_create_ui test_edit_ui test_delete_ui -v
omarchy plugin validate .
python3 build_release.py
```

In a running desktop, test open, search, scroll, Escape, outside-click dismissal, right-click refresh, email/copy/map actions, offline cached display, no-key setup, a rejected replacement key, disable/re-enable and removal/reinstall. Saved QML normally hot-reloads. If Omarchy retains stale plugin code, rescan plugins and, if needed, run `omarchy restart shell`. Keep private screenshots and API outputs out of the repository. Tests cover pagination, bounded responses, redirect refusal, action URL validation, private caches, failed credentials, markup-shaped display input, native creation fields, duplicate checks, permission failures, recovery of uncertain saves, exact deletion confirmation, changed-name checks and deletion-cache updates. The desktop integration checks verify failed-save form retention, successful-save list updates, editing with prefilled fields, and the typed-confirmation deletion flow using synthetic data.

## Release checks

The public source includes a valid root manifest, MIT license, installation/removal steps, the Suppliers add-on prerequisite, API permissions, private-storage locations and synthetic regression tests. Runtime releases use a fixed six-file allowlist, reject symlinks and unsafe versions, and omit credentials, caches, logs and screenshots.

CI tests Python 3.9 and 3.13, builds the release ZIP and runs detect-secrets 1.5.0 with online verification disabled. Only four literal synthetic test values are excluded from that scan. Desktop QML integration tests require an Omarchy session and are run separately with `RUN_QML_INTEGRATION=1`; they do not create, change or delete real suppliers. These checks do not constitute certification by Omarchy or ServiceM8.

## Marketplace submission

Repository: https://github.com/Ianhorne73/omarchy-servicem8-suppliers

Prepared for the [Omarchy marketplace publishing guide](https://plugins.omarchy.org/publish.html). A public repository and maintainer review are required; local validation does not guarantee acceptance. Submit the repository at the marketplace's linked submission form, with category **Productivity** and tags **Bar** and **Quickshell**. The root manifest uses permanent ID `servicem8.suppliers` and contains no clone metadata or installation hooks. MIT license, no external Python packages, original text/icon-font UI, no bundled brand assets. Add an anonymized preview if desired; never use real supplier data in a public screenshot.

API references: [List suppliers](https://developer.servicem8.com/reference/listsuppliers), [Create supplier](https://developer.servicem8.com/reference/createsuppliers), [Delete supplier](https://developer.servicem8.com/reference/deletesuppliers), [Update supplier](https://developer.servicem8.com/reference/updatesuppliers).

Maintainer notes for submission: Requires Omarchy with Quickshell plugin support, Python 3.9+, xdg-utils and wl-clipboard for copying. Requires the ServiceM8 Suppliers add-on and each user’s own supplier-read API key; creation, editing and deletion also need supplier-write access. Optional My Jobs Today integration shares one locally saved key. No install hooks, no elevated privileges, no background service, and no external Python runtime packages. Network refresh occurs on user interaction; typed yes is required for edits and deletion. The plugin never sends email or SMS itself. MIT source; no bundled ServiceM8 artwork or private preview assets.
