# Procedural Tail Animation with Spring Physics

A real-time tail simulation that brings a static Godzilla model to life using
spring physics, inertia coupling, and a phase-delayed travelling sine wave.

The Godzilla model used in this project ships with walking, arm, and leg
animations baked in, but the tail has **no keyframes** and stays completely
still. This project drives the tail bones procedurally at runtime so the tail
swings, lags behind turns, dips on jumps, and snaps up on heavy landings.

> **Topic:** Procedural tail animation with spring physics
> **Goal:**  Simulate the motion of a tail (or whip) made of many connected
> bones, swinging according to physical laws.

---

## Preview Image

<img width="734" height="420" alt="Screenshot 2026-05-03 212710" src="https://github.com/user-attachments/assets/e6de301c-1d56-420a-854f-b37869c9d499" />

---

## Features

- **Damped harmonic oscillator** per bone : heavy, springy feel
- **Inertia coupling** to body acceleration : jump dips, landing snaps, turn lag
- **Phase-delayed travelling sine wave** : wave visibly runs from base to tip
- **Sideways-swing up-bias** : prevents floor-clipping during sharp turns
- **Soft floor clamp** : guaranteed no ground penetration
- **Runtime toggle** : turn the simulation on/off live for A/B comparison

---

## Project Structure

```
.
├── godzilla_tail.py   # Main program (tail physics + city destruction demo)
├── godzilla.glb       # Godzilla model with renamed tail bones
└── README.md          # This file
```

---

## Requirements

- Python 3.8+
- [Ursina engine](https://www.ursinaengine.org/) (Panda3D is installed as a
  dependency; we use `direct.actor.Actor` to access individual bones)

---

## Installation

```bash
pip install ursina
```

Place `godzilla.glb` in the same folder as `godzilla_tail.py`.

---

## Usage

```bash
python godzilla_tail.py
```

On startup the program prints the skeleton's full bone list to the console so
you can verify the names of the tail bones.

### Controls

| Key                | Action                                   |
| ------------------ | ---------------------------------------- |
| `WASD` / Arrows    | Move                                     |
| `SHIFT`            | Run                                      |
| `SPACE`            | Jump                                     |
| `Left Click` / `F` | Smash attack (destroy buildings)         |
| `R`                | Reset the city                           |
| `RMB` (hold)       | Orbit camera                             |
| `T`                | Toggle tail physics ON / OFF             |
| `B`                | Print bone list to console               |
| `1` – `5`          | Force-play animation #1 .. #5            |
| `0`                | Resume automatic animation switching     |
| `ESC`              | Quit                                     |

> Tip: press `T` while walking, running, jumping, or turning to see exactly
> what each part of the simulation contributes.

---

## How It Works

The tail is driven by **three physics equations** combined with **two safety
mechanisms**, for five stages total.

### 1. Damped Harmonic Oscillator (per bone)

Hooke's law plus a damping term, applied independently on the heading and
pitch axes of every tail bone:

```
a         = k * (target - angle) - c * velocity
velocity += a * dt
angle    += velocity * dt
```

This is what makes the tail feel **heavy** — it overshoots its target and
gradually settles, like real flesh and bone.

### 2. Inertia Coupling (Newton's 1st Law)

The body's acceleration drives each bone's target angle:

- `target_pitch  ←  -body_vertical_accel  * gain`
  → jump up, tail dips down; land hard, tail snaps up
- `target_yaw    ←  -body_angular_vel     * gain`
  → turn left, tail trails to the right

### 3. Phase-Delayed Travelling Sine Wave

Each bone's wag is delayed by a small phase relative to the previous bone,
producing a wave that visibly **travels** from the base of the tail out to the
tip — the way a real animal's tail flicks.

### 4. Sideways-Swing UP-Bias

```
swing_lift = |heading_angle| * SWING_LIFT_GAIN * inertia_factor
```

When the tail swings hard sideways, chained yaw rotations across many bones
tend to drag the tip downward through the floor. This term lifts the tail
upward proportionally to how far it's currently swung, the same balance
trick real animals use.

### 5. Soft Floor Clamp

Caps how far any bone may pitch downward to `MAX_DOWN` degrees, guaranteeing
the tail never clips through the ground even on heavy landings.

---

## Configuration

All tuning lives in the **TAIL CONFIG** section at the top of
`godzilla_tail.py`:

| Parameter         | Description                                                                 |
| ----------------- | --------------------------------------------------------------------------- |
| `TAIL_BONES`      | Names of tail bones to control (currently `Bone.012`..`Bone.034`, 23 bones) |
| `TAIL_AMPLITUDE`  | Base wag amplitude per bone (degrees)                                       |
| `TAIL_FREQUENCY`  | Base wag frequency (cycles per second)                                      |
| `TAIL_PHASE_DELAY`| Phase lag between consecutive bones (radians)                               |
| `TAIL_STIFFNESS`  | Spring constant *k*. Higher = snappier tail                                 |
| `TAIL_DAMPING`    | Damping coefficient *c*. Critical damping at *c ≈ 2√k*                      |
| `REST_LIFT`       | Resting tilt (degrees); sign sets the model's pitch-up convention           |
| `SWING_LIFT_GAIN` | Up-bias added per degree of sideways swing                                  |
| `MAX_DOWN`        | Soft-floor ceiling: max downward pitch in degrees                           |

---

## Project Workflow

1. Download a Godzilla `.glb` model that has walking / limb animations but a
   static tail.
2. Open it in Blender and rename the tail bones to a consistent set of names
   so the program can identify them.
3. Export back to `godzilla.glb`.
4. Run `godzilla_tail.py`. The program:
   - Loads the model with panda3d's `Actor`.
   - Calls `controlJoint()` on each tail bone, **detaching** it from the
     baked animation so our code has full control of it.
   - Every frame, `update_tail()` evaluates *spring + inertia + sine wave +
     clamp* as described above.
   - Writes the resulting angles back into each bone with `joint.setHpr(...)`.

---

## Credits

### Godzilla model

> **"Godzilla First Walk Animation (scrunchy32205 alt)"**
> by **[carladoll996](https://sketchfab.com/carladoll996)**
> — [Sketchfab page](https://sketchfab.com/3d-models/godzilla-first-walk-animationscrunchy32205-alt-e46c2cc5b698471588afd0ff9875d519)
> Licensed under [Creative Commons Attribution 4.0 (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

### Tools & libraries

- [Ursina engine](https://www.ursinaengine.org/) : game framework
- [Blender](https://www.blender.org/) : bone renaming and re-export
