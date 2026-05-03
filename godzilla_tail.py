"""
GODZILLA CITY DESTRUCTION — with NATURAL procedural tail

CONTROLS:
  WASD / Arrows : Move
  SHIFT         : Run
  SPACE         : Jump
  LEFT CLICK / F: Smash attack
  R             : Reset city
  RMB drag      : Orbit camera
  T             : Toggle tail wag on/off (for testing)
  B             : Print bone list to console (helper for finding tail)

ANIMATION TESTING:
  1, 2, 3, 4, 5 : Force-play animation #1..5
  0             : Resume automatic animation switching

==============================================================
TAIL PHYSICS — what's going on
==============================================================
The tail uses three combined equations + two clamps:

  1) Damped harmonic oscillator per bone (Hooke's law + damping):
        a = k*(target - angle) - c*velocity
        velocity += a*dt
        angle    += velocity*dt
     This makes the tail feel HEAVY — it overshoots and settles.

  2) Inertia coupling (Newton's 1st law) — body accel drives target:
        target_pitch <- -body_vertical_accel * gain  (jump=down, fall=up)
        target_yaw   <- -body_angular_vel    * gain  (turn left=trail right)

  3) Phase-delayed travelling sine wave for the rhythmic wag.

  4) Sideways-swing UP-bias:
        swing_lift = |heading_angle| * SWING_LIFT_GAIN * inertia_factor
     When the tail swings hard sideways during turns, the geometric
     chaining of yaw across many bones tends to drag the tip downward.
     This counter-bias lifts the tail up in proportion to how far it's
     currently swung — same trick real animals use for balance.

  5) Soft floor clamp on pitch — guarantees no bone can ever pitch
     past MAX_DOWN in the down direction, even on heavy landings.

PITCH CONVENTION:
  PITCH_UP_SIGN is auto-derived from the sign of REST_LIFT.
  If REST_LIFT > 0 → positive pitch goes UP on your model.
  If REST_LIFT < 0 → positive pitch goes DOWN on your model.
  All other pitch terms (jump reaction, swing comp, floor clamp)
  follow that convention automatically.

Tuning knobs:
  TAIL_STIFFNESS     k    -- higher = snappier tail
  TAIL_DAMPING       c    -- critical damping at c ≈ 2*sqrt(k)
  REST_LIFT               -- rest pose: tail held UP by this many degrees
                             at the tip (sign defines model convention).
  SWING_LIFT_GAIN         -- how much the tail lifts up when swung sideways.
                             Increase if tail still dips below floor on turns.
  MAX_DOWN                -- soft floor: max degrees any bone may pitch DOWN.
==============================================================
"""

from ursina import *
from direct.actor.Actor import Actor
import random
import math

app = Ursina()
window.title = 'Godzilla City Destruction'
window.color = color.rgb(20, 20, 35)

CITY_SIZE = 500
GODZILLA_SCALE = 2.2

# === ANIMATION MAPPING ===
ANIM_MAP = {
    'idle':   'Armature|ArmatureAction',
    'walk':   'Armature|ArmatureAction.001',
    'run':    'Armature|ArmatureAction.001',
    'jump':   'Armature|ArmatureAction.002',
    'attack': 'Armature|ArmatureAction.003',
}
ANIM_PLAY_RATES = {
    'idle': 0.6, 'walk': 1.0, 'run': 1.6, 'jump': 1.0, 'attack': 1.4,
}

# ============== TAIL CONFIG ==============
TAIL_BONES = [f'Bone.{i:03d}' for i in range(12, 35)]   # Bone.012 .. Bone.034

# Wag waveform parameters
TAIL_AMPLITUDE   = 25     # base wag amplitude in degrees per bone
TAIL_FREQUENCY   = 0.8    # base wag cycles per second
TAIL_PHASE_DELAY = 0.28   # phase lag between consecutive bones (radians)

# Spring physics parameters
TAIL_STIFFNESS = 280.0    # spring constant k (180-350 = heavy Godzilla tail)
TAIL_DAMPING   = 18.0     # damping coefficient c (under-damped = lively wobble)

# Rest pose, swing compensation, clamp
REST_LIFT       = 5.0     # rest pose tilt; sign sets pitch convention.
                          # POSITIVE = your model's pitch-up direction.
SWING_LIFT_GAIN = 0.3    # how much UP-bias to add per degree of sideways swing
                          # (raise this if tail still dips below floor on turns)
MAX_DOWN        = 6.0     # soft floor: max degrees any bone may pitch DOWN

# Auto-derived: which sign of pitch is "up" on this model?
PITCH_UP_SIGN = 1 if REST_LIFT >= 0 else -1

# Per-bone spring state (heading=yaw, pitch=up/down)
tail_h_vel = [0.0] * len(TAIL_BONES)   # angular velocity, heading axis
tail_p_vel = [0.0] * len(TAIL_BONES)   # angular velocity, pitch axis
tail_h_ang = [0.0] * len(TAIL_BONES)   # current angular offset from rest, heading
tail_p_ang = [0.0] * len(TAIL_BONES)   # current angular offset from rest, pitch

# Body kinematics tracking (used by the inertia coupling)
prev_velocity_y      = 0.0
prev_body_rotation_y = 0.0
# ==========================================

# ========================= CITY =========================
ground = Entity(model='plane', scale=(CITY_SIZE, 1, CITY_SIZE),
                texture='grass', color=color.gray.tint(-0.7),
                texture_scale=(30, 30), collider='box')


for i in range(-2, 3):
    Entity(model='plane', scale=(CITY_SIZE, 1, 12),
           position=(0, 0.05, i * 80), color=color.dark_gray)
    Entity(model='plane', scale=(12, 1, CITY_SIZE),
           position=(i * 80, 0.05, 0), color=color.dark_gray)

class Building(Entity):
    def __init__(self, position, height):
        style = random.choice(['glass', 'brick', 'concrete'])
        if style == 'glass':
            col = color.rgb(random.randint(80, 140), random.randint(140, 200), random.randint(180, 230))
            tex = 'white_cube'
        elif style == 'brick':
            col = color.rgb(random.randint(140, 200), 80, 60); tex = 'brick'
        else:
            col = color.rgb(random.randint(150, 200), random.randint(150, 200), random.randint(150, 200))
            tex = 'white_cube'
        super().__init__(model='cube',
                         scale=(random.uniform(8, 14), height, random.uniform(8, 14)),
                         position=(position[0], height / 2, position[2]),
                         color=col, texture=tex, collider='box')
        self.full_height = height
        self.destroyed = False
        self.health = max(1, int(height / 12))
        self.shake_offset = 0

    def take_damage(self, amount=1):
        if self.destroyed: return
        self.health -= amount
        self.color = self.color.tint(-0.15)
        self.shake_offset = 0.4
        if self.health <= 0:
            self.collapse()

    def collapse(self):
        self.destroyed = True
        self.collider = None
        for _ in range(6):
            d = Entity(model='cube', color=self.color, scale=random.uniform(1.5, 3),
                       position=self.position + Vec3(random.uniform(-2,2),
                                                     random.uniform(0, self.full_height),
                                                     random.uniform(-2,2)))
            d.velocity = Vec3(random.uniform(-8,8), random.uniform(5,14), random.uniform(-8,8))
            d.angular = Vec3(random.uniform(-300,300), random.uniform(-300,300), random.uniform(-300,300))
            d.lifetime = 4
            debris.append(d)
        self.animate_scale_y(0.5, duration=0.6, curve=curve.out_quad)
        self.animate_y(0.25, duration=0.6, curve=curve.out_quad)
        invoke(setattr, self, 'enabled', False, delay=2.0)

buildings = []
debris = []

def spawn_city():
    global buildings
    for b in buildings: destroy(b)
    buildings = []
    spacing = 22
    for x in range(int(-CITY_SIZE/2)+20, int(CITY_SIZE/2)-20, spacing):
        for z in range(int(-CITY_SIZE/2)+20, int(CITY_SIZE/2)-20, spacing):
            if abs(x) < 8 or abs(z) < 8: continue
            if abs(x % 80) < 8 or abs(z % 80) < 8: continue
            if random.random() < 0.35: continue
            buildings.append(Building((x + random.uniform(-3,3), 0, z + random.uniform(-3,3)),
                                      random.uniform(15, 65)))

spawn_city()

cars = []
for i in range(30):
    c = Entity(model='cube', scale=(4, 2.5, 7),
               position=(random.uniform(-CITY_SIZE/2+20, CITY_SIZE/2-20), 1.25,
                         random.uniform(-CITY_SIZE/2+20, CITY_SIZE/2-20)),
               color=color.rgb(random.randint(80,255), random.randint(80,255), random.randint(80,255)),
               rotation_y=random.choice([0,90,180,270]), collider='box')
    c.destroyed = False
    cars.append(c)

trees = []
for i in range(50):
    x = random.uniform(-CITY_SIZE/2+10, CITY_SIZE/2-10)
    z = random.uniform(-CITY_SIZE/2+10, CITY_SIZE/2-10)
    trunk = Entity(model='cube', scale=(1.8, 7, 1.8),
                   position=(x, 3.5, z), color=color.brown, collider='box')
    leaves = Entity(model='sphere', scale=6, position=(x, 10, z),
                    color=color.green.tint(random.uniform(-0.3, 0.1)))
    trunk.leaves = leaves
    trunk.destroyed = False
    trees.append(trunk)

# ========================= GODZILLA =========================
body = Entity(position=(0, 0, 0))

godzilla_actor = Actor('godzilla.glb')
godzilla_actor.reparentTo(body)
godzilla_actor.setScale(GODZILLA_SCALE)
godzilla_actor.setH(180)

ANIM_NAMES = list(godzilla_actor.getAnimNames())
print(f"\nLoaded {len(ANIM_NAMES)} animations: {ANIM_NAMES}")

# ====== PRINT ALL BONES — find your tail in this list ======
def print_bone_list():
    """Prints every joint with its parent so you can identify the tail chain."""
    joints = godzilla_actor.getJoints()
    print(f"\n=== {len(joints)} BONES IN SKELETON ===")
    print("Format: BONE_NAME  <-  parent_name")
    print("Look for a chain where each bone's parent is the previous bone.")
    print("That chain attached behind the spine is your tail.\n")
    for j in joints:
        try:
            p = j.getParent()
            pname = p.getName() if p else 'ROOT'
        except Exception:
            pname = '?'
        print(f"  {j.getName():25s}  <-  {pname}")
    print("=== END OF BONES ===\n")

print_bone_list()
# ============================================================

# Set up control over tail bones (disconnects them from animation)
tail_joints = []
tail_rest_hpr = []
for name in TAIL_BONES:
    j = godzilla_actor.controlJoint(None, 'modelRoot', name)
    if j is None or j.isEmpty():
        print(f"WARNING: tail bone '{name}' not found in skeleton")
        continue
    tail_joints.append(j)
    tail_rest_hpr.append(j.getHpr())

# Trim per-bone state arrays in case some tail bones weren't found
_n_actual = len(tail_joints)
tail_h_vel = tail_h_vel[:_n_actual]
tail_p_vel = tail_p_vel[:_n_actual]
tail_h_ang = tail_h_ang[:_n_actual]
tail_p_ang = tail_p_ang[:_n_actual]

if tail_joints:
    print(f"Tail control: {len(tail_joints)} bones connected, wagging enabled")
else:
    print("Tail control: no bones configured. Edit TAIL_BONES in the script.")

current_anim = None
manual_anim_override = None

def play_anim(name, rate=1.0):
    global current_anim
    if name is None or name not in ANIM_NAMES: return
    if current_anim == name: return
    godzilla_actor.stop()
    godzilla_actor.setPlayRate(rate, name)
    godzilla_actor.loop(name)
    current_anim = name

play_anim(ANIM_MAP.get('idle'), ANIM_PLAY_RATES['idle'])

# ========================= STATE =========================
move_speed = 0.9
run_multiplier = 1.9
velocity_y = 0
gravity = -0.42
jump_power = 11
ground_y = 0
walk_phase = 0
score = 0
shake_amount = 0
camera_yaw = 0
camera_pitch = 20
camera_dist = 95
attack_timer = 0
tail_wag_enabled = True

mouse.locked = False
mouse.visible = True

# ========================= INPUT =========================
def input(key):
    global score, manual_anim_override, attack_timer, tail_wag_enabled
    if key == 'r':
        spawn_city(); score = 0
    elif key == 'left mouse down' or key == 'f':
        smash_attack(); attack_timer = 0.6
    elif key == 'escape':
        application.quit()
    elif key == 't':
        tail_wag_enabled = not tail_wag_enabled
        print(f"Tail wag: {'ON' if tail_wag_enabled else 'OFF'}")
    elif key == 'b':
        print_bone_list()
    elif key in '12345':
        idx = int(key) - 1
        if idx < len(ANIM_NAMES):
            manual_anim_override = ANIM_NAMES[idx]
            play_anim(manual_anim_override, 1.0)
            anim_text.text = f'MANUAL: {manual_anim_override} ({godzilla_actor.getNumFrames(manual_anim_override)} frames)'
    elif key == '0':
        manual_anim_override = None
        anim_text.text = 'AUTO'

def smash_attack():
    global shake_amount, score
    shake_amount = 1.2
    attack_pos = body.position + Vec3(
        math.sin(math.radians(body.rotation_y)) * 10, 2,
        math.cos(math.radians(body.rotation_y)) * 10)
    radius = 16
    for b in buildings:
        if b.destroyed or not b.enabled: continue
        d = (b.position - attack_pos); d.y = 0
        if d.length() < radius:
            b.take_damage(2)
            if b.destroyed: score += int(b.full_height)
    for c in cars:
        if c.destroyed: continue
        if (c.position - attack_pos).length() < radius:
            c.destroyed = True; c.collider = None
            c.animate_scale_y(0.3, duration=0.4); c.animate_y(0.5, duration=0.4)
            score += 10
    for t in trees:
        if t.destroyed: continue
        if (t.position - attack_pos).length() < radius:
            t.destroyed = True; t.collider = None
            t.animate_rotation((random.uniform(70,110), 0, random.uniform(-30,30)), duration=0.6)
            t.leaves.animate_position(t.leaves.position + Vec3(0,-3,0), duration=0.6)
            score += 5

def crush_under_feet():
    global score
    pos = body.position
    for b in buildings:
        if b.destroyed or not b.enabled: continue
        d = (b.position - pos); d.y = 0
        if d.length() < 7 and b.full_height < body.y + 5:
            b.take_damage(1)
            if b.destroyed: score += int(b.full_height)
        elif d.length() < 6:
            b.take_damage(1)
            if b.destroyed: score += int(b.full_height)
    for c in cars:
        if c.destroyed: continue
        if (c.position - pos).length() < 6:
            c.destroyed = True; c.collider = None
            c.animate_scale_y(0.2, duration=0.3); c.animate_y(0.3, duration=0.3)
            score += 10

# ========================= TAIL UPDATE =========================
def update_tail():
    """
    Procedural tail combining:
      1. Damped harmonic oscillator per bone  -> heavy, springy feel
      2. Inertia coupling to body acceleration -> jump=down, fall=up,
                                                   turn left=trail right
      3. Phase-delayed travelling sine wave    -> rhythmic wag
      4. Sideways-swing UP-bias                -> no floor-clipping in turns
      5. Soft floor on pitch                   -> hard guarantee against clipping
    """
    global prev_velocity_y, prev_body_rotation_y

    if not tail_joints or not tail_wag_enabled:
        # Still keep prev_* up-to-date so we don't get a huge jolt when re-enabled
        prev_velocity_y      = velocity_y
        prev_body_rotation_y = body.rotation_y
        return

    dt = max(time.dt, 1e-4)        # guard against dt=0 on the first frame
    n = len(tail_joints)
    is_running = held_keys['shift']
    moving = any(held_keys[k] for k in
                 ('w', 'a', 's', 'd',
                  'up arrow', 'down arrow', 'left arrow', 'right arrow'))

    # ---------- Body kinematics (the source of all inertia coupling) ----------
    # Vertical ACCELERATION (not velocity!). Positive = body accelerating upward.
    accel_y = (velocity_y - prev_velocity_y) / dt
    prev_velocity_y = velocity_y

    # Angular velocity around Y, deg/sec. Positive = body turning right (CW from above).
    rot_diff = (body.rotation_y - prev_body_rotation_y + 540) % 360 - 180
    angular_vel_y = rot_diff / dt
    prev_body_rotation_y = body.rotation_y

    # ---------- Wag amplitude/frequency scales with locomotion ----------
    if is_running:
        amp_mul, freq_mul = 1.6, 1.6
    elif moving:
        amp_mul, freq_mul = 1.0, 1.0
    else:
        amp_mul, freq_mul = 0.35, 0.6

    t = time.time()

    for i, joint in enumerate(tail_joints):
        # Bones farther from the root have more inertia (longer lever arm)
        inertia_factor = (i + 1) / n

        # ============================================================
        # TARGET HEADING (left/right yaw)
        # ============================================================
        # 1) Travelling sine wave — each bone delayed by TAIL_PHASE_DELAY radians.
        phase = t * TAIL_FREQUENCY * 2 * math.pi * freq_mul - i * TAIL_PHASE_DELAY
        wave = math.sin(phase) + 0.3 * math.sin(phase * 1.7)
        tip_weight = 0.4 + 0.6 * inertia_factor
        wag = wave * TAIL_AMPLITUDE * amp_mul * tip_weight

        # 2) Turn lag — Newton's 1st law: tail trails opposite to body rotation.
        #    If the lag goes the wrong way, flip the sign of -0.18.
        turn_lag = -angular_vel_y * 0.12 * inertia_factor

        target_h = wag + turn_lag

        # ============================================================
        # HEADING SPRING — solve heading first; we'll use the result
        # for the swing-up compensation below.
        # ============================================================
        k = TAIL_STIFFNESS * (1.2 - 0.4 * inertia_factor)
        c = TAIL_DAMPING

        accel_h = k * (target_h - tail_h_ang[i]) - c * tail_h_vel[i]
        tail_h_vel[i] += accel_h * dt
        tail_h_ang[i] += tail_h_vel[i] * dt

        # ============================================================
        # TARGET PITCH (up/down) — sign-aware for your model's convention
        # ============================================================
        # Inertia: body accel UP -> tail target pitches DOWN.
        # Multiply by -PITCH_UP_SIGN so this is correct on either model convention.
        jump_pitch = -PITCH_UP_SIGN * accel_y * 0.18 * inertia_factor

        # Rest lift (REST_LIFT already carries the right sign for this model)
        rest_lift = REST_LIFT * inertia_factor

        # ----- Sideways-swing UP-bias -----
        # When the tail is swung sideways, chained yaw rotations drag the tip
        # down through the floor. Counter that by adding pitch in the UP
        # direction proportional to how far this bone is swung.
        # PITCH_UP_SIGN ensures we always lift UP regardless of model convention.
        swing_lift = abs(tail_h_ang[i]) * SWING_LIFT_GAIN * inertia_factor * PITCH_UP_SIGN

        target_p = jump_pitch + rest_lift + swing_lift

        # ============================================================
        # PITCH SPRING
        # ============================================================
        accel_p = k * (target_p - tail_p_ang[i]) - c * tail_p_vel[i]
        tail_p_vel[i] += accel_p * dt
        tail_p_ang[i] += tail_p_vel[i] * dt

        # ----- Soft floor: don't let any bone pitch DOWN beyond MAX_DOWN -----
        # "Down" is the direction OPPOSITE to PITCH_UP_SIGN.
        down_amount = -PITCH_UP_SIGN * tail_p_ang[i]
        if down_amount > MAX_DOWN:
            tail_p_ang[i] = -PITCH_UP_SIGN * MAX_DOWN
            # Kill any further-down velocity
            if -PITCH_UP_SIGN * tail_p_vel[i] > 0:
                tail_p_vel[i] = 0

        # ============================================================
        # Apply both axes around the bone's rest pose
        # ============================================================
        rest = tail_rest_hpr[i]
        joint.setHpr(rest.x + tail_h_ang[i],
                     rest.y + tail_p_ang[i],
                     rest.z)

# ========================= UPDATE =========================
def update():
    global velocity_y, walk_phase, shake_amount, camera_yaw, camera_pitch
    global score, attack_timer

    is_running = held_keys['shift']
    speed = move_speed * (run_multiplier if is_running else 1.0)
    moving = False
    move_dir = Vec3(0, 0, 0)
    if held_keys['w'] or held_keys['up arrow']:    move_dir.z += 1; moving = True
    if held_keys['s'] or held_keys['down arrow']:  move_dir.z -= 1; moving = True
    if held_keys['a'] or held_keys['left arrow']:  move_dir.x -= 1; moving = True
    if held_keys['d'] or held_keys['right arrow']: move_dir.x += 1; moving = True

    if moving:
        move_dir = move_dir.normalized()
        body.x += move_dir.x * speed
        body.z += move_dir.z * speed
        target_rot = math.degrees(math.atan2(move_dir.x, move_dir.z))
        cur = body.rotation_y % 360
        diff = (target_rot - cur + 540) % 360 - 180
        body.rotation_y = cur + diff * 0.18
        walk_phase += time.dt * (10 if is_running else 6)

    body.x = clamp(body.x, -CITY_SIZE/2 + 5, CITY_SIZE/2 - 5)
    body.z = clamp(body.z, -CITY_SIZE/2 + 5, CITY_SIZE/2 - 5)

    on_ground = body.y <= ground_y + 0.05
    if held_keys['space'] and on_ground:
        velocity_y = jump_power
    body.y += velocity_y * time.dt * 60
    velocity_y += gravity * time.dt * 60
    if body.y < ground_y:
        if velocity_y < -3:
            shake_amount = max(shake_amount, abs(velocity_y) * 0.08)
            crush_under_feet()
        body.y = ground_y; velocity_y = 0

    if moving and on_ground and int(walk_phase * 2) != getattr(update, '_last_step', -1):
        update._last_step = int(walk_phase * 2)
        crush_under_feet()

    # Animation state machine
    if attack_timer > 0:
        attack_timer -= time.dt
    if manual_anim_override is None:
        if attack_timer > 0 and ANIM_MAP.get('attack') in ANIM_NAMES:
            play_anim(ANIM_MAP['attack'], ANIM_PLAY_RATES['attack'])
        elif not on_ground and ANIM_MAP.get('jump') in ANIM_NAMES:
            play_anim(ANIM_MAP['jump'], ANIM_PLAY_RATES['jump'])
        elif moving:
            if is_running and ANIM_MAP.get('run') in ANIM_NAMES:
                play_anim(ANIM_MAP['run'], ANIM_PLAY_RATES['run'])
            elif ANIM_MAP.get('walk') in ANIM_NAMES:
                play_anim(ANIM_MAP['walk'], ANIM_PLAY_RATES['walk'])
        else:
            if ANIM_MAP.get('idle') in ANIM_NAMES:
                play_anim(ANIM_MAP['idle'], ANIM_PLAY_RATES['idle'])

    # ====== Procedural tail (single call) ======
    update_tail()

    # Debris
    for d in debris[:]:
        d.lifetime -= time.dt
        if d.lifetime <= 0:
            destroy(d); debris.remove(d); continue
        d.velocity += Vec3(0, -30 * time.dt, 0)
        d.position += d.velocity * time.dt
        d.rotation += d.angular * time.dt
        if d.y < 0.5:
            d.y = 0.5
            d.velocity.y *= -0.3; d.velocity.x *= 0.7; d.velocity.z *= 0.7

    for b in buildings:
        if b.shake_offset > 0:
            b.shake_offset *= 0.85
            b.x += random.uniform(-b.shake_offset, b.shake_offset)
            b.z += random.uniform(-b.shake_offset, b.shake_offset)

    # Camera
    if held_keys['right mouse']:
        camera_yaw += mouse.velocity[0] * 100
        camera_pitch -= mouse.velocity[1] * 100
        camera_pitch = clamp(camera_pitch, 5, 60)
    rad_yaw = math.radians(camera_yaw)
    rad_pitch = math.radians(camera_pitch)
    cam_offset = Vec3(
        -math.sin(rad_yaw) * camera_dist * math.cos(rad_pitch),
        math.sin(rad_pitch) * camera_dist + 25,
        -math.cos(rad_yaw) * camera_dist * math.cos(rad_pitch)
    )
    shake = Vec3(random.uniform(-1,1)*shake_amount,
                 random.uniform(-1,1)*shake_amount,
                 random.uniform(-1,1)*shake_amount)
    shake_amount *= 0.88
    camera.position = lerp(camera.position, body.position + cam_offset + shake, 0.12)
    camera.look_at(body.position + Vec3(0, 15, 0))

    score_text.text = f'DESTRUCTION: {score}'

# ========================= UI =========================
Text("GODZILLA : CITY DESTRUCTION", y=0.46, origin=(0,0), scale=1.8, color=color.red, background=True)
Text("WASD/Run | SPACE | LMB/F=Smash | R=Reset | T=Tail | B=Bones | RMB=Camera",
     y=-0.42, origin=(0,0), scale=1.0, color=color.yellow, background=True)
Text("1-5 test anim | 0 auto",
     y=-0.46, origin=(0,0), scale=1.0, color=color.cyan, background=True)
score_text = Text('DESTRUCTION: 0', position=window.top_left + Vec2(0.02, -0.04),
                  scale=2, color=color.orange, background=True)
anim_text = Text('AUTO', position=window.top_left + Vec2(0.02, -0.10),
                 scale=1.4, color=color.azure, background=True)

Sky()
DirectionalLight(y=90, rotation=(50, -40, 30), shadows=True)
AmbientLight(color=color.rgba(120, 120, 140, 100))

app.run()