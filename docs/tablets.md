# Tablets

Every TAB-1 tablet shows one TAB-1 dashboard. This page explains how to
turn on a new tablet, how to choose its dashboard, how to switch it from an
automation, what the tablet's taps may do, and what the status words mean.

A tablet can show a dashboard only when its software has the dashboard
engine. Until then your choice is saved and sent as soon as it has.

## Adding a tablet

A tablet shows up in the panel once it is in Home Assistant. For a tablet
that has the dashboard software on it, the tablet's screen says each next
step under a large headline:

1. Power the tablet on.
2. If its screen says "Set up Wi-Fi", join the open Wi-Fi "Apollo TAB1
   Hotspot" from a phone within 15 minutes, and pick your home's Wi-Fi on
   the page that opens.
3. Its screen then says "Add this tablet in Home Assistant" and "It shows
   up by itself in Settings > Devices & services". Add it there.
4. Its screen then says "Ready to turn on". Turn it on in the panel, as
   below.

The 15 minutes start each time the tablet is powered on. If they run out
first, the tablet says "Setup not finished" and "Restart the tablet to
finish setup": turn it off and on, and start again at step 2 or 3. While
no tablet is in Home Assistant the panel says "No TAB-1 tablet found in
Home Assistant yet" and repeats these steps; you can build dashboards all
the same. Once there is a tablet, a short line under the tablets says the
same for the next one:
"To add another tablet, power it on. If it asks for Wi-Fi, join "Apollo TAB1 Hotspot" from a phone and pick your Wi-Fi. Then add it in Settings > Devices & services, where it shows up by itself, and turn it on here."

## A new tablet

Any ESPHome device can say it is a TAB-1: the name comes from the device's
own software. So Home Assistant does not trust a tablet it sees for the
first time. Until an admin turns it on, Home Assistant sends it nothing, it
is not set up for taps, and anything it sends is ignored.

The panel lists a new tablet first in the "Tablets" box, marked "New", with
"New tablet. Pick a dashboard, then press "Turn on with this dashboard"."
(or "New tablet. Make a dashboard, then pick it and press "Turn on with
this dashboard"." while there is no dashboard to pick). Any
device can call itself "Porch tablet", so under its name the row says what
to check first, for example "Before you turn it on, check that the name on
the tablet's screen ends in 12ee0e." The six characters are the end of the
tablet's MAC address, and its waiting screen shows its name with them, for
example "Apollo TAB-1 12ee0e". Check them on the tablet in front of you.
"Open device page" opens the device in Home Assistant. Home Assistant also
lists the tablet under Settings > System > Repairs as "New TAB-1 tablet
found", with its name. A tablet whose device you disabled in Home Assistant
is not listed there.

A tablet that was added to ESPHome again still shows its old dashboard, not
its waiting screen, so its name is not on its screen. When the panel knows
that dashboard, the row says what to check instead, for example "If it
still shows Home, its old dashboard, its name is not on its screen. Check
that it shows Home and that its values no longer change." That is the
tablet you just added again.

To turn it on in the panel, pick its first dashboard under "Shows", then
press "Turn on with this dashboard". Picking alone changes nothing, also
when you move through the list with the keyboard. Only that button turns a
tablet on. A "Shows" list or the editor's "Show this dashboard" still open
from before the tablet became new is refused, and the tablet stays as it
is. The panel then says that the change could not be saved:
"This tablet is new. Pick a dashboard for it on the Home screen, then press "Turn on with this dashboard"."

An admin can also turn it on with the tablet's "Dashboard" control or with
the "Show dashboard" action. Only turn on tablets you own. If you do not
know the device, remove it from ESPHome instead.

After you press the button, the tablet keeps its place in the list until
you come back to the Home screen, and focus moves to its name. A "Turn on
with this dashboard" button that has just moved, because a row above it
changed, ignores presses for a moment and looks greyed out until then. So
a double click turns on only the tablet you meant. A button that did not
move takes a press at once, whatever else changes on the screen.

An automation, or a user who is not an admin, cannot turn on a new tablet.
Add-ons such as Node-RED or AppDaemon that call Home Assistant with their
own access (the Supervisor's) count as automations. They are refused with:

> An admin must turn this tablet on first: in the TAB-1 panel, pick a
> dashboard for it, then press "Turn on with this dashboard".

An add-on that you set up with an admin's long-lived access token acts as
that admin: it can turn on a new tablet, just as that admin can with the
"Show dashboard" action. Only the Supervisor's own access counts as an
automation. So give an add-on an admin's token only if you would let it do
what that admin can. Once a tablet is on, automations and add-ons switch it
like any other tablet.

A tablet stays on when Home Assistant restarts, when ESPHome reloads, and
when its device is removed and added again by the same ESPHome entry. A
tablet that is added to ESPHome again (a new entry for the same tablet) is
new again and needs an admin once more. Its "Shows" list marks the dashboard
it showed before, for example "Home (shown before)", until that dashboard
is deleted.

### What a waiting tablet shows

Home Assistant sends nothing to a tablet that is not turned on, so the
tablet keeps the screen it has. The panel says so under the row: "Until you
turn it on, the tablet keeps the screen it has now, and taps on it do
nothing."

- A tablet that was never set up shows its waiting screen: "Ready to turn
  on" and "Open TAB-1 in Home Assistant and turn this tablet on", with its
  name above them.
- A tablet that was added to ESPHome again keeps the last dashboard it had,
  with the values it had then; they no longer change. Taps do nothing: a
  lock may still ask "Unlock Front door?", but nothing happens after the
  yes. Once the tablet has connected again, a tap shows "Home Assistant is
  not connected". That is expected: it waits for an admin, not for a
  connection.

As soon as an admin turns it on, it is set up again and gets its dashboard.

### Taking an approval back

The panel has no button to turn a tablet off again. To take an approval
back, delete the tablet's ESPHome entry (Settings > Devices & services >
ESPHome, then the tablet, then Delete). Home Assistant then talks to it no
more. If it is added to ESPHome again later, it is new again and needs an
admin once more.

## Which dashboard a tablet shows

- A new tablet gets no dashboard until an admin turns it on with its first
  dashboard (see above).
- A tablet that is on but has nothing to show, because its dashboard was
  deleted, gets the first TAB-1 dashboard you make.
- A new tablet that marks a dashboard "(shown before)" loses that mark when
  the dashboard is deleted, also while Home Assistant is off. A dashboard
  made later with the same id is not marked.
- The list is sorted by title, then by the dashboard's id.
- Renaming a dashboard does not move any tablet.
- Deleting a dashboard moves its tablets to the first one left. If none is
  left, they have nothing to show.
- A dashboard that cannot be read for a while (for example a YAML dashboard
  with an error, or whose file is gone) keeps its tablets, and they keep
  their last screen. Until Home Assistant restarts, that screen's values
  stay live and its taps work. After a restart Home Assistant has nothing
  to take them from: the screen stays, but its values stop changing and
  taps do nothing until the dashboard can be read again.
  Meanwhile the tablet's row says "This dashboard cannot be read" and its
  "Shows" list names the dashboard with "(cannot be read right now)".
  Deleting such a dashboard moves its tablets on like any other.
- The choice is kept for each tablet, also when you remove the tablet from
  Home Assistant and its ESPHome entry adds it again.

## Choosing a dashboard

In the TAB-1 panel: open the Home screen and, in the "Tablets" box, pick a
dashboard under "Shows" next to the tablet. It is saved and sent at once.
A new tablet is turned on with "Turn on with this dashboard" after the pick
(see above).
The editor's settings for a dashboard, under "This dashboard", list the
tablets that show it, with a "Show this dashboard" button for the others.
New tablets are not listed there: turn them on from the Home screen first.

On the tablet's device page: the "Dashboard" control under Configuration has
the same choice. Two dashboards with the same title are told apart by their
id, for example "Home (tab-home)".

Only admins and automations can switch a tablet's dashboard. A user who is
not an admin is refused. Only an admin can turn on a new tablet.

## Switching from an automation

There are two ways.

**By title**, with the tablet's "Dashboard" control:

```yaml
action: select.select_option
target:
  entity_id: select.kitchen_tablet_dashboard
data:
  option: Night
```

This stops working when the dashboard is renamed, because "Night" is then
no longer one of the choices.

**By id**, with the "Show dashboard" action. This keeps working after a
rename:

```yaml
action: apollo_tab.show_dashboard
data:
  device_id: 0123456789abcdef0123456789abcdef
  dashboard: tab-night
```

- `device_id` is the tablet's device. In the automation editor, pick the
  tablet from the list and the id is filled in.
- `dashboard` is the dashboard's id. The editor shows it under "This
  dashboard", as "Name for automations". It is also the last part of the
  dashboard's address, and the `dashboard_id` attribute of the tablet's
  "Dashboard" control.

If something is wrong the action says so plainly: "This tablet is not known"
or "This dashboard does not exist".

### A "Night" button for the family

A script runs as the person who started it. So a button on a family
dashboard that runs a script is refused for a user who is not an admin.
Let the button start an automation instead:

1. Make a button helper, for example `input_button.night`.
2. Put the button on the family's dashboard.
3. Make an automation that switches the tablet when the button is pressed:

```yaml
triggers:
  - trigger: state
    entity_id: input_button.night
actions:
  - action: apollo_tab.show_dashboard
    data:
      device_id: 0123456789abcdef0123456789abcdef
      dashboard: tab-night
```

## Taps on the tablet

The tablet controls devices only when its ESPHome connection is encrypted.
Without encryption it shows the dashboard but cannot control anything: the
panel says "Turn on encryption for it in ESPHome", and a tap on the tablet
shows "Touch is off: this tablet is not protected". The dashboard version
of the tablet software turns encryption on by itself: Home Assistant gives
the tablet its key the first time they connect. If you build the tablet
software yourself, keep `encryption:` under `api:`. If you also set a `key:`
there, keep it in your `secrets.yaml`, never in a file you share.

With encryption on, Home Assistant and the tablet set themselves up once an
admin has turned the tablet on. The panel says "It is still being set up"
until that has worked, and a tap on the tablet shows "Not paired with Home
Assistant". Home Assistant tries again by itself once a minute. If the
tablet is still not set up after a minute and a half, the panel shows a
"Set up again" button under that line: press it to start the set-up again
at once. If that does not help, check that the tablet runs the dashboard
version of the tablet software and that its ESPHome device in Home
Assistant is working.

A tablet that was set up before and then erased comes back without its
key. Home Assistant then lists it under Settings > System > Repairs as
"Authentication expired for" and the tablet's name there, for example
"Authentication expired for Apollo TAB-1 ddee01". Opening it says that the
device "disabled transport encryption" and asks you to confirm that you
want to "remove the encryption key and allow unencrypted connections".
Home Assistant does not try again by itself, so until an admin answers, the
panel says "Waiting for you in Repairs" for the tablet, on an amber band,
and under it when to confirm, the name to look for in Repairs and an "Open
Repairs" link:

> Only if you erased this tablet and its screen says "Confirm this tablet
> in Home Assistant" ("Add this tablet in Home Assistant" after a USB
> erase): confirm "Authentication expired for Apollo TAB-1 ddee01"; it gets
> its old key back. "Setup not finished": restart it first. Otherwise do
> not confirm: check the tablet.

The tablet's own screen is the check. Confirm that question only if you
erased this tablet yourself and its screen now says "Confirm this tablet in
Home Assistant" under its name. A tablet erased by holding a finger on its
screen right after power-on shows that until it has its key again, with
"In Settings > System > Repairs, confirm only “Authentication expired for
Apollo TAB-1 ddee01”" under it. A tablet erased over USB says "Add this
tablet in Home Assistant" instead, which counts the same. Only a tablet
without its key shows either, and another device on your network cannot
make a tablet that still has its key show them. At most it can make the
screen show something else for a while, and then you do not confirm. A
restart alone, for example after a power cut, is never a reason to
confirm. If its screen says "Setup not finished" and "Restart the tablet
to finish setup", its 15 minutes ran out: restart it, and confirm once it
shows one of those two screens again.

If so, confirm it. Home Assistant then gives the tablet back the key it
kept for it: the same key the tablet had before the erase, not a new one.
The line goes away. Until the tablet has its key, Home Assistant sends it
nothing, not its dashboard and not your devices' values, so they never
cross your network unencrypted; the panel says "Sending…" for those few
seconds. The tablet stays turned on: no admin has to approve it again. It
takes the key only in the 15 minutes after it starts, which is why its
screen has to say "Confirm this tablet in Home Assistant" (or "Add this
tablet in Home Assistant" after a USB erase) when you confirm.

If you did not erase the tablet, do not confirm, and check the tablet. A
tablet erased by holding its screen shows its waiting screen with its
name, for example "Apollo TAB-1 ddee01": "Set up Wi-Fi" until it is on
your Wi-Fi, then "Confirm this tablet in Home Assistant". Its last line,
"If this Home Assistant never had this tablet, add it in Settings >
Devices & services", is only for a Home Assistant that never had the
tablet. Yours had it and asks in Repairs, so do not add a device there: one
that shows up by the tablet's name could be another one. A tablet that
shows its dashboard or "Waiting for Home Assistant" still has its key and
was not erased. Another device on your network can pretend to be the
tablet and ask the same question, and confirming would hand it the key
Home Assistant kept for the tablet.

If Home Assistant asks for a key instead (it first met the erased tablet
after its 15 minutes ran out), the row says "Waiting for you in Repairs"
too, and under it "Home Assistant asks for this tablet's key in Repairs",
also with "Open Repairs". Do not enter a key there. If you erased this
tablet yourself and its screen says "Setup not finished":

1. Close that question without entering a key.
2. Restart the tablet.
3. Within 15 minutes, go to Settings > Devices & services > ESPHome, open
   the tablet's menu (three dots) and press Reload.

The reload ends the question for a key, and Home Assistant connects to the
tablet again. It then finds the erased tablet without its key and asks the
question above instead; the row says so. Confirm it as above, once the
tablet's screen says "Confirm this tablet in Home Assistant" (or "Add this
tablet in Home Assistant" after a USB erase). If you did not erase the
tablet, or its screen does not say "Setup not finished", do not do these
steps: check the tablet. A tablet that still has its key never says "Setup
not finished". The panel gives the same steps.

A tap on the tablet follows the same rules as a click in a browser:

- A card controls only the devices it was set up with, and only in the ways
  the card allows.
- Example cards cannot control anything.
- Locks, alarms and garage, gate and door covers ask for confirmation on the
  tablet first, for example "Open Garage?". Home Assistant still checks
  every tap and refuses one without the yes.
- A card from your own folder that controls a lock or an alarm works only
  after an admin has allowed it in the TAB-1 panel.
- A tap that is not allowed shows "Not allowed on this tablet" for a moment.
- While Home Assistant is not connected, the tablet shows its last values,
  and a tap shows "Home Assistant is not connected" and does nothing.

One thing is different from a browser: a tablet has no logged-in user, so
anyone at the tablet can use every card on it. Put a card on a tablet's
dashboard only if everyone who can reach that tablet may use it.

## Text on the tablet

The tablet's font has Latin letters with accents and common punctuation.
Any other character, for example Greek, Cyrillic, Chinese or an emoji,
shows as an empty box. The tablet picture in the TAB-1 panel shows the
same boxes, so you see it before you send. The picture also cuts a long
line with "…" at the same character as the tablet. A thermostat or gauge
value too wide for its dial is drawn a size smaller, as on the tablet,
down to the smallest text size; only there is it cut with "…".

## Status words

The panel shows one of these for each tablet:

| Words | Meaning |
|---|---|
| New tablet. Pick a dashboard, then press "Turn on with this dashboard". | Nobody has turned this tablet on yet. Home Assistant sends it nothing, so it keeps the screen it has, and its taps do nothing. |
| New tablet. Make a dashboard, then pick it and press "Turn on with this dashboard". | The same, and there is no TAB-1 dashboard to pick yet. |
| On the tablet | The tablet says it shows the dashboard. |
| Sending… | The dashboard is on its way, or the tablet is still building it, or an erased tablet is getting its key back. |
| Offline | The tablet is not connected to Home Assistant. The row adds "Check that the tablet has power and Wi-Fi. If your Wi-Fi changed, turn the tablet off and on, then within 15 minutes join "Apollo TAB1 Hotspot" from a phone and pick your Wi-Fi.". A tablet that has a dashboard keeps showing it, with its last values and a small mark at the bottom left that it is not connected. Without Wi-Fi it also shows a note at the bottom, for example "No Wi-Fi. Join the Wi-Fi “Apollo TAB1 Hotspot” from a phone". With Wi-Fi but without Home Assistant it shows only the small mark, so its screen may not say what is wrong. A tablet without a dashboard names what it needs, for example "Set up Wi-Fi", "No Wi-Fi", "Setup not finished" or "Waiting for Home Assistant", each with the next step. |
| Waiting for you in Repairs | Home Assistant does not connect to the tablet until an admin answers its question in Settings > System > Repairs, for example after the tablet was erased. The row says when to confirm and when not to (see "Taps on the tablet"). |
| Waiting for tablet software | The tablet's software cannot show dashboards yet. |
| Needs newer tablet software | Update the software on the tablet. |
| Update Apollo TAB Dashboard in Home Assistant | The tablet is newer than this integration, or Home Assistant changed how it reaches ESPHome devices. |
| Could not send. Trying again. | Sending failed. It is tried again after 5 seconds, then 15 seconds, 1 minute and every 5 minutes. |
| This dashboard is too big for the tablet | Make the dashboard smaller: fewer pages, cards or graphs. |
| This dashboard cannot be read | Its saved settings are broken, for example a YAML file with an error. Fix or delete it; tablets on it keep their last dashboard until then. |
| The tablet cannot show this dashboard | Nothing is tried again until the dashboard or the tablet changes. |
| Nothing to show yet | The tablet has no dashboard: there is no TAB-1 dashboard yet ("Make a dashboard first."), or none is picked for it. The tablet says the same, with "Open TAB-1 in Home Assistant to see what this tablet should show". |

Each tablet's device page also has a "Dashboard engine" sensor under
Diagnostic: "Not installed", "Ready" or "Update needed". Its "Engine
version" attribute is the version of the engine on the tablet.

## Removing the integration

When you delete the integration, every tablet it turned on and can reach is
cleared and goes back to its waiting screen, and the saved choices are
deleted. A tablet
that is offline at that moment keeps its last dashboard until it gets new
software or a new dashboard.

Turning the integration off or restarting Home Assistant does not clear the
tablets.
