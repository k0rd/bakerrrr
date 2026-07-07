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
- `E` inspects items in inventory-style panels.

## Drones

Drone parts are ordinary items until you stow them. Pick up or buy loose chassis, power cores, and modules into your backpack, then select the part in inventory and press `U` to move it into the drone workshop.

- `U` on a `packed drone` deploys it nearby when there is room.
- `,` picks a deployed drone back up when there is no ground item taking pickup priority.
- `g` opens remote command for a deployed drone with a remote receiver.
- `G` opens the drone sheet/workshop in local view.
- In the drone sheet, the Parts tab can move workshop parts back to your backpack or drop them on your tile.
- Batteries and packed drones stay in your backpack. Shops and street contacts only trade what is in your backpack, so move a part out of the workshop before selling it.

Drone features depend on installed modules. Cameras enable linked looking, cargo modules enable cargo transfer, procedure modules enable autonomy, and weapon modules need their matching ammo or fuel support.

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
