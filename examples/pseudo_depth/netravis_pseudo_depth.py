"""Pseudo depth for NetraVis6L_USB cameras — live view (Isaac Sim Script Editor).

Isaac Sim's single-view depth sensor, set up from the template each NetraVis6L_USB carries
(`econ_PseudoDepth_ir`): a generic stereo depth approximation with this camera's geometry,
1 m to 6 m. It is not NetraVis6L_USB's own depth output (see the main README).

Run it in Window -> Script Editor with one or more NetraVis6L_USB cameras in the stage
(Create -> Sensors -> Camera and Depth Sensors -> e-con -> NetraVis6L_USB). It presses Play
and opens a window per camera:

    image   pseudo depth, near = red -> far = blue, black = no depth
    text    share of pixels with depth, nearest distance, distance at the image centre

Turn the IR dot projector on (eye icon on Emitter_Left / Emitter_Right) for texture-poor
scenes: pseudo depth needs texture.

In your own code, after running this file in the same Script Editor tab:

    d = get_depth()               # numpy (720, 1080) float32, metres; 0 = no depth
    d = get_depth("/World/NetraVis6L_USB_01")

Stop with stop().
"""
import asyncio

import carb
import numpy as np
import omni.kit.app
import omni.replicator.core as rep
import omni.timeline
import omni.ui as ui
import omni.usd

MODEL = "NetraVis6L_USB"
TEMPLATE = "econ_PseudoDepth_ir"
CAMERA = "Stereo_Camera/CameraFrame/Pseudo_Depth"
SIZE = (1080, 720)                  # the template's resolution (width, height)
VIEW_SIZE = (540, 360)              # size of the image in the window
RANGE_M = (1.0, 6.0)                # colour scale
UPDATE_EVERY = 10                   # refresh the window every N app updates

_sensors = {}                       # unit path -> {"rp", "annot", "window", "image", "label"}
_sub = None
_tick = 0


def _units(stage):
    """Paths of the NetraVis6L_USB cameras in the stage."""
    return [str(p.GetPath()) for p in stage.Traverse()
            if p.GetAttribute("econ:unit:model").IsValid()
            and p.GetAttribute("econ:unit:model").Get() == MODEL
            and stage.GetPrimAtPath(p.GetPath().AppendChild(TEMPLATE)).IsValid()]


def _create(stage, unit):
    """A render product on the unit's Pseudo_Depth camera with the template's sensor settings."""
    template = stage.GetPrimAtPath(f"{unit}/{TEMPLATE}")
    rp = rep.create.render_product(f"{unit}/{CAMERA}", SIZE)
    rp_prim = stage.GetPrimAtPath(rp.path)
    for k in ("renderSettings", "camera", "renderProduct"):
        carb.settings.get_settings().set(f"/exts/omni.usd.schema.render_settings/rtx/{k}/apiSchemas/autoApply", None)
    rp_prim.ApplyAPI("OmniSensorDepthSensorSingleViewAPI")
    for a in template.GetAttributes():
        if a.GetName().startswith("omni:rtx:post:depthSensor:") and a.HasAuthoredValue():
            rp_prim.GetAttribute(a.GetName()).Set(a.Get())
    rp_prim.GetAttribute("omni:rtx:post:depthSensor:enabled").Set(True)
    annot = rep.AnnotatorRegistry.get_annotator("DepthSensorDistance")
    annot.attach(rp)

    window = ui.Window(f"Pseudo depth - {unit.rsplit('/', 1)[-1]}",
                       width=VIEW_SIZE[0] + 20, height=VIEW_SIZE[1] + 70)
    image = ui.ByteImageProvider()
    with window.frame:
        with ui.VStack(spacing=4):
            ui.ImageWithProvider(image, width=VIEW_SIZE[0], height=VIEW_SIZE[1])
            label = ui.Label("waiting for frames...", height=20)
    return {"rp": rp, "annot": annot, "window": window, "image": image, "label": label}


def get_depth(unit=None):
    """The latest pseudo depth of a unit (default: the first), numpy (720, 1080), metres; 0 = no depth."""
    if not _sensors:
        return None
    s = _sensors[unit] if unit else next(iter(_sensors.values()))
    d = np.asarray(s["annot"].get_data(), dtype=np.float32)
    if d.size != SIZE[0] * SIZE[1]:
        return None
    d = d.reshape(SIZE[1], SIZE[0])
    return np.where(np.isfinite(d) & (d > 0), d, 0.0)


def _colour(d):
    """Depth (m) -> RGBA bytes at VIEW_SIZE: red near, blue far, black where there is no depth."""
    step = SIZE[0] // VIEW_SIZE[0]
    d = d[::step, ::step][:VIEW_SIZE[1], :VIEW_SIZE[0]]
    t = np.clip((d - RANGE_M[0]) / (RANGE_M[1] - RANGE_M[0]), 0.0, 1.0)
    rgba = np.empty((*d.shape, 4), np.uint8)
    rgba[..., 0] = 255 * (1 - t)
    rgba[..., 1] = 255 * (1 - np.abs(2 * t - 1))
    rgba[..., 2] = 255 * t
    rgba[..., 3] = 255
    rgba[d <= 0, :3] = 0
    return rgba


def _update(_):
    global _tick
    _tick += 1
    if _tick % UPDATE_EVERY:
        return
    for unit, s in _sensors.items():
        d = get_depth(unit)
        if d is None:
            continue
        s["image"].set_bytes_data(_colour(d).flatten().tolist(), [VIEW_SIZE[0], VIEW_SIZE[1]])
        valid = d > 0
        centre = d[SIZE[1] // 2, SIZE[0] // 2]
        s["label"].text = (f"depth on {valid.mean() * 100:.0f}% of pixels   "
                           f"nearest {d[valid].min():.2f} m   " if valid.any() else "no depth   ") + \
                          (f"centre {centre:.2f} m" if centre > 0 else "centre: no depth")


def stop():
    """Close the windows and remove the render products."""
    global _sub
    _sub = None
    for s in _sensors.values():
        try:
            s["annot"].detach()
            s["rp"].destroy()
        except Exception:
            pass
        s["window"].visible = False
    _sensors.clear()


async def _start():
    global _sub
    stop()
    stage = omni.usd.get_context().get_stage()
    units = _units(stage)
    if not units:
        print(f"[pseudo depth] no {MODEL} camera in the stage: add one from "
              "Create -> Sensors -> Camera and Depth Sensors -> e-con")
        return
    for unit in units:
        _sensors[unit] = _create(stage, unit)
    if not omni.timeline.get_timeline_interface().is_playing():
        omni.timeline.get_timeline_interface().play()
    _sub = (omni.kit.app.get_app().get_update_event_stream()
            .create_subscription_to_pop(_update, name="netravis pseudo depth"))
    print(f"[pseudo depth] showing {len(units)} camera(s): {', '.join(units)}")
    print("[pseudo depth] get_depth() returns the latest frame; stop() closes the windows")


asyncio.ensure_future(_start())
