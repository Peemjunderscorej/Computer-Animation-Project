==============================================================================
  PROCEDURAL TAIL ANIMATION WITH SPRING PHYSICS
==============================================================================

Topic       : Procedural tail animation with spring physics
Problem     : Build a system that simulates the motion of a tail or whip made
              of many connected bones, swinging according to physical laws.
Model       : Godzilla (.glb) - already has walking / arm / leg animations,
              but the tail is completely static (no keyframes on tail bones).
What we did : Renamed the tail bones in Blender, re-exported the .glb, and
              wrote a Python program that drives the tail bones at runtime
              using spring physics + inertia coupling + sine-wave wagging.


------------------------------------------------------------------------------
1. FILES IN THIS FOLDER
------------------------------------------------------------------------------
  godzilla_tail.py   -- Main program. Tail physics + city destruction demo.
  godzilla.glb       -- Godzilla model with the tail bones renamed.
  readme.txt         -- This file.


------------------------------------------------------------------------------
2. REQUIREMENTS
------------------------------------------------------------------------------
  - Python 3.8 or newer
  - ursina engine  (this also installs panda3d, which we use through
                    direct.actor.Actor to access and drive individual bones)

  Install command:
      pip install ursina


------------------------------------------------------------------------------
3. HOW TO RUN
------------------------------------------------------------------------------
  Place godzilla.glb in the same folder as godzilla_tail.py and run:

      python godzilla_tail.py

  When the program starts, it prints the full bone list of the skeleton to
  the console so you can verify the names of the tail bones.


------------------------------------------------------------------------------
4. CONTROLS
------------------------------------------------------------------------------
  WASD / Arrows         Move
  SHIFT                 Run
  SPACE                 Jump
  Left Click / F        Smash attack (destroy buildings)
  R                     Reset the city
  RMB (hold)            Orbit camera
  T                     Toggle tail physics ON / OFF
                        (great for A/B comparison: see how the tail looks
                         with the simulation off vs on)
  B                     Print the bone list to the console
  1-5                   Force-play animation #1..#5
  0                     Resume automatic animation switching
  ESC                   Quit


------------------------------------------------------------------------------
5. HOW THE TAIL PHYSICS WORKS
------------------------------------------------------------------------------
The tail is driven by 3 physics equations combined with 2 safety mechanisms,
giving 5 stages in total:

  (1) Damped harmonic oscillator per bone  (Hooke's law + damping)
        a = k * (target - angle) - c * velocity
        velocity += a * dt
        angle    += velocity * dt
      This makes the tail feel HEAVY -- it overshoots its target and
      gradually settles back, like real flesh and bone.

  (2) Inertia coupling  (Newton's 1st law -- body acceleration drives target)
        target_pitch <- -body_vertical_accel * gain
                        (jump up => tail dips down,
                         land hard => tail snaps up)
        target_yaw   <- -body_angular_vel * gain
                        (turn left => tail trails to the right)

  (3) Phase-delayed travelling sine wave
      Each bone's wag has a small phase delay relative to the previous one.
      This produces a wave that visibly travels from the base of the tail
      out to the tip, the way a real animal's tail flicks.

  (4) Sideways-swing UP-bias
        swing_lift = |heading_angle| * SWING_LIFT_GAIN * inertia_factor
      When the tail swings hard sideways, the chained yaw rotations across
      many bones tend to drag the tip downward through the floor. We
      counter this by adding pitch in the UP direction proportional to how
      far the bone is currently swung -- the same balance trick real
      animals use.

  (5) Soft floor clamp on pitch
      Caps how far down any bone can pitch to MAX_DOWN degrees, guaranteeing
      the tail will never clip through the ground even on heavy landings.


------------------------------------------------------------------------------
6. TUNING KNOBS
------------------------------------------------------------------------------
All adjustable in the TAIL CONFIG section at the top of godzilla_tail.py:

  TAIL_BONES         Names of the tail bones to control. The current code
                     uses Bone.012 .. Bone.034 (23 bones total) which are
                     the renamed tail bones from Blender.
  TAIL_AMPLITUDE     Base wag amplitude per bone, in degrees.
  TAIL_FREQUENCY     Base wag frequency, in cycles per second.
  TAIL_PHASE_DELAY   Phase lag between consecutive bones (radians) -- this
                     is what makes the wag look like a travelling wave.
  TAIL_STIFFNESS  k  Spring constant. Higher = snappier tail.
  TAIL_DAMPING    c  Damping coefficient. Critical damping at c ~= 2*sqrt(k);
                     keep it under-damped for a lively wobble.
  REST_LIFT          Resting tilt of the tail in degrees. The SIGN of this
                     value also tells the rest of the system which pitch
                     direction is "up" on this particular model.
  SWING_LIFT_GAIN    How much UP-bias to add per degree of sideways swing.
                     Increase this if the tail still dips below the floor
                     during sharp turns.
  MAX_DOWN           Soft-floor ceiling: max degrees any bone may pitch DOWN.


------------------------------------------------------------------------------
7. PROJECT WORKFLOW
------------------------------------------------------------------------------
  1) Download a Godzilla (.glb) model that has walking / limb animations
     but a static tail.
  2) Open it in Blender and rename the tail bones to a consistent set of
     names so the program can identify them.
  3) Export back to godzilla.glb.
  4) Run godzilla_tail.py. The program:
       - Loads the model with panda3d's Actor.
       - Calls controlJoint() on each tail bone, which DETACHES that bone
         from the baked animation so our code has full control of it.
       - Every frame, update() calls update_tail(), which evaluates
         spring + inertia + sine wave + clamp as described in section 5.
       - Writes the resulting angles back into each bone with
         joint.setHpr(...).


==============================================================================