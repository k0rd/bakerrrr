# Controls And Help

Press `?` in game for the full help panel. Press `Esc` or `?` again to close it.

The HUD footer is your quick reference. It changes when you are looking, talking, shopping, driving, reading the log, or using inventory.

## Action Palette

- `Tab` opens a small action menu near you.
- `Enter` runs the selected action.
- `B` rebinds the selected action to another key.
- `R` resets the selected action to its default.
- `Esc` closes the menu.

Movement, back, help, and the action-menu key itself are protected. The rest is meant to be reshuffled while you play.

In Pygame, a controller can use the same palette. Left stick or d-pad moves, `Left Shoulder/LB/L1` held filters movement to diagonals only, `South/A/Cross` confirms, `East/B/Circle` backs out, `View/Select` opens the action palette, `West/X/Square` binds the selected action, and `North/Y/Triangle` resets it. Ordinary action buttons and triggers can be rebound from the palette; movement, diagonal-filter shoulder, confirm, back, menu, and start/pause-style inputs stay protected.

## Core Movement

- Move with arrows, `WASD`, `HJKL`, `QEZC`, or numpad `1-9`.
- Wait with `Space` or numpad `5`.
- Open the map with `X`.

## Looking, Talking, And Using Things

- `x` opens the look cursor.
- `/` targets someone to talk to.
- `'` targets a nearby thing to physically interact with.
- `.` uses the service on your tile.
- `,` picks up nearby items.
- `;` locks or unlocks a nearby door when you have the right access.

If there is more than one possible target, use the cursor. Guessing is optional. The cursor is there so you do not have to argue with the tile stack.

## Reports, Notes, And Memory

- `O` opens the operations report.
- `Y` opens the Places notebook.
- `Tab` switches between Places and People while the notebook is open.
- `L` opens the event log.
- `+` opens the character sheet.

These are player-facing tools. They are not just flavor; they are how the game reminds you what you have seen, who you have met, and what currently matters.

## Inventory And Gear

- `i` opens inventory.
- `U` uses, equips, or stows the selected item.
- `R` drops the selected item.
- `S` cycles inventory sort order without changing what you carry.
- `E` inspects items in inventory-style panels.

## Drones

Drone parts are ordinary items until you stow them. Pick up or buy loose chassis, power cores, and modules into your backpack, then select the part in inventory and press `U` to move it into the drone workshop.

- Electronics, comms, and drone shops are the cleanest legal sources for drone parts. Surplus, backroom, street, salvage, and field sources can still carry rougher or restricted gear.
- `U` on a `packed drone` deploys it nearby when there is room.
- `,` picks a deployed drone back up when there is no ground item taking pickup priority.
- `g` opens remote command for a deployed drone with a remote receiver.
- `G` opens the drone workshop in local view.
- In the drone workshop, the Parts tab can move workshop parts back to your backpack or drop them on your tile.
- To edit a packed drone instead of deploying it, open `G`, use the Parts tab, and press `Enter` on the backpack packed-drone row. The drone unpacks into workshop parts and its battery returns to your backpack.
- Batteries and packed drones stay in your backpack. Shops and street contacts only trade what is in your backpack, so move a part out of the workshop before selling it.

Drone features depend on installed modules. Cameras enable linked looking, cargo modules enable cargo transfer, procedure modules enable autonomy, and weapon modules need their matching ammo or fuel support.

## Tinkering And Field Devices

Mechanical plans are real inventory items. Inspect a plan with `E` to see its
parts and output. With the plan, its components, and a usable pocket multitool
in your inventory, press `U` on the plan to begin construction. Time passes in
the living world while you work; interruption leaves parts that were not yet
consumed in your inventory.

The first field-device family contains four different tools:

- tripline alarms make noise and can survive enough use to be reset or
  recovered;
- restraint snares interrupt movement and are spent when they catch something;
- remote release rigs place a receiver loaded with a carried smoke, aerosol,
  or fire payload while leaving the linked controller in your inventory;
- decoy beacons make a short, bounded series of noises.

Select a completed device and press `U` to place or operate it. A remote release
controller uses `U` again to fire its linked receiver while it remains in range.
Physically interact with your own deployed device to recover it when its design
and condition allow. Other people can notice placement, remember or discover a
device, avoid it, disarm it, report it, or use devices for their own purposes.

## Map And Vehicle Basics

- On foot, `X` opens the map for browsing.
- On the map, movement browses or travels depending on whether you are in a vehicle.
- `t` returns from the map to the street or exits the vehicle.
- `M` adds a marker, `l` lists markers, and `N` jumps to the nearest marker.
- In a vehicle, `G` can drive toward the last marker.

## Combat And Caution

- `F` cycles target lock or opens melee aim.
- Free aim is available from the `Tab` action palette and can be rebound.
- `C` uses cover.
- `v` hops cover.
- `Shift+S` toggles sneak.
- `V` cycles weapons.

You do not need to memorize every key before playing. Start with movement, `x`, `/`, `.`, `i`, `O`, `Y`, `L`, and `?`. The rest can arrive when the street asks for it.
