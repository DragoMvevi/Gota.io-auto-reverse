**Made by someone**

A lightweight, external auto-reverse tool I built for **Gota.io** (and other Agar-style games). Instead of messing with browser memory, extensions, or WebSocket hooks, it reads screen pixels around your target cell in real time and hits your split/reverse key the instant the enemy cell shrinks or splits.



https://github.com/user-attachments/assets/2753499a-0772-4a33-a564-4fcc318255be


---

## How It Works

When you lock onto a cell, a small black crosshair glides out to the cell's outer edge and follows its movement smoothly.

- If the player is just moving around normally, the crosshair drifts along with the rim.
- The moment they press split (or shrink suddenly), their cell border pulls back across the crosshair and the tool instantly fires your reverse/split key.
- Every trigger is strictly **single-shot**—once it fires, it disarms itself automatically so it won't spam your keys.

---

## Modes

- **Fixed Mode (Toggle — default `X`)**  
  Aim anywhere inside an enemy cell and press your toggle key. The crosshair glides out to the nearest edge, tracks the cell's border in 8 directions, and fires as soon as the dark background hits the crosshair.

- **Smart Mode (Toggle — default `Z` / `M`)**  
  Locks onto the exact RGB color under your cursor and tracks the cell's border. As soon as that color changes past your sensitivity threshold, it fires. Great when playing with custom background colors or themes.

- **Movable Mode (Hold — default `C` / `P`)**  
  Hold the key down to sample directly under your live mouse cursor without locking the crosshair in place.

---

## Main Features

- **8-Directional Edge Tracking**: You don't have to pixel-hunt the very edge of a cell—aim inside the cell and the crosshair automatically glides out to the rim and hugs it.
- **Controlled Glide Speed**: Crosshair movement is tuned so it follows normal drift smoothly without outrunning a cell when it shrinks or splits.
- **Auto-Aim Snap & Cursor Tether**: Can automatically snap your cursor to the target right before firing your split, or tether your mouse directly to the tracking crosshair.
- **Click-Through Black Crosshair**: Clean overlay reticle that stays on top of the game without stealing focus or blocking mouse clicks.

---

## Best In-Game Settings (Gota.io)

For the cleanest tracking in all Modes:
1. Use a **Dark / Black background**.
2. Turn off **Skins** so cells are solid colors.
3. lower animation delay.
4. be smart and play anonymously.

---

## Setup & Running

Make sure you have Python 3.10+ installed along with `customtkinter` and `Pillow`:

```bash
pip install customtkinter pillow
```

Then either double-click **`run.bat`** or run:

```bash
python main.py
```

Set your hotkeys and sensitivity in the menu, click **Apply & Save Settings**, and you're good to go.
