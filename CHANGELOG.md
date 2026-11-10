# Changelog

## 1.3.4

- Remove the Call button and phone-handler integration. Supplier phone numbers remain visible and included in Copy.

## 1.3.3

- Handle Call without opening a browser when no dedicated phone app is configured: copy the number and show an explanation.
- Add the public repository installation URL, clearer dependency and removal documentation, and publishing checks.
- Use synthetic contact details throughout the tests.
- Harden release packaging against symlinked files and unsafe versions.
- Add CI tests on Python 3.9 and 3.13 and a local secret scan with online verification disabled.

## 1.3.2

- Rename the initial edit action to Save changes.

## 1.3.1

- Show proposed edit changes and require typing exactly yes before saving.
- Clear edit confirmation when details change, the panel closes, or a save fails.

## 1.3.0

- Add editing of existing ServiceM8 suppliers, preserving unchanged fields and checking for conflicting remote edits.
- Make the ServiceM8 Suppliers add-on prerequisite prominent.

## 1.2.0

- Add supplier deletion with typed yes confirmation. ServiceM8 archives deleted suppliers.

## 1.1.0

- Add supplier creation, duplicate checks and recovery of uncertain saves.

## 1.0.1

- Share the saved API key with My Jobs Today, show connection status, and support multiline map addresses.

## 1.0.0

- Initial searchable supplier directory with contact and copy actions.
