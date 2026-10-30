"""ROS 2 publisher for the four NetraVis6L_USB cameras on Nova Carter (Isaac Sim Script Editor).

Every NetraVis6L_USB unit in the stage that has a ``Depth_GT`` camera is found automatically
(named after its prim suffix: front / back / left / right) and publishes:

    /netravis/<side>/depth          sensor_msgs/Image 32FC1, metres  -- ground-truth depth
    /netravis/<side>/color          sensor_msgs/Image rgb8, ~10 Hz  -- the same view in colour
    /netravis/<side>/camera_info    sensor_msgs/CameraInfo (pinhole 1080x720, fx 559.2), for both
    /tf                             camera frames under base_link (ROS optical convention)
    /clock                          only if the scene does not publish it already

``Depth_GT`` is the camera's rectified depth frame (1080x720, fx 559.2, at the right IR
camera's pose) with a 0.002 m near clip, so the depth is exact at every distance. The
colour image is rendered by the same camera, pixel-aligned with the depth; nvblox uses it only to
colour its mesh. It is a simulation aid: the real camera has no colour image in its depth frame.
The NetraVis6L_USB camera's own ROS variant is not used here and can stay disabled.

A small window shows the four depth images (near = red, far = blue) while publishing.

Usage: open the scene, then run this file in Window -> Script Editor. It presses Play if
needed. Stop with ``teardown()`` (or run the file again to restart).
"""
import asyncio
import os

import numpy as np
import omni.graph.core as og
import omni.kit.app
import omni.timeline
import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom

# ── configuration ─────────────────────────────────────────────────────────────
# The ROS 2 domain is the ROS_DOMAIN_ID that Isaac Sim was started with (as for the robot's
# own publishers); start Nav2 / nvblox with the same value.
ROS2_DOMAIN_ID = int(os.environ.get("ROS_DOMAIN_ID", "0") or 0)
TOPIC_ROOT = "/netravis"
TF_PARENT_LINK = "base_link"
WIDTH, HEIGHT = 1080, 720           # the device's depth resolution
PUBLISH_COLOR = True                # colour image of the depth view, for nvblox's mesh colours
COLOR_FRAME_SKIP = 5                # publish every 6th frame (~10 Hz); nvblox integrates colour at 5 Hz
PREVIEW_WINDOW = True               # show the four depth images in a window
PREVIEW_SIZE = (360, 240)
PREVIEW_MAX_M = 6.0                 # colour scale of the preview

GRAPH_ROOT = "/NetraVisGraphs"
MODEL = "NetraVis6L_USB"
GT_CAMERA = "Stereo_Camera/CameraFrame/Depth_GT"

_preview = None


def _wait(n=1):
    async def _w():
        for _ in range(n):
            await omni.kit.app.get_app().next_update_async()
    return _w()


def _find_units(stage):
    """[(side, unit root, Depth_GT path)] for every NetraVis6L_USB unit with a Depth_GT camera."""
    units = []
    for prim in stage.Traverse():
        a = prim.GetAttribute("econ:unit:model")
        if not (a and a.HasAuthoredValue() and a.Get() == MODEL):
            continue
        gt = prim.GetPath().AppendPath(GT_CAMERA)
        if not stage.GetPrimAtPath(gt).IsValid():
            print(f"  [skip] {prim.GetPath()}: no {GT_CAMERA}")
            continue
        name = prim.GetName()
        side = name[len(MODEL) + 1:] if name.startswith(MODEL + "_") else name
        units.append((side or f"cam{len(units)}", str(prim.GetPath()), str(gt)))
    return units


def _find_base_link(stage, near_path):
    """The base_link prim nearest the cameras (shared path prefix)."""
    cands = [str(p.GetPath()) for p in stage.Traverse() if p.GetName() == TF_PARENT_LINK]
    if not cands:
        return ""
    return max(cands, key=lambda c: len(Sdf.Path(c).GetCommonPrefix(Sdf.Path(near_path)).pathString))


def _optical_frame(stage, cam_path, frame_name):
    """An Xform beside the camera in ROS optical convention (+Z forward, +Y down); a Camera
    prim itself is not a valid TF target. Its TF frame name is frame_name."""
    cam = stage.GetPrimAtPath(cam_path)
    path = f"{cam.GetParent().GetPath()}/{frame_name}"
    local = UsdGeom.Xformable(cam).GetLocalTransformation(Usd.TimeCode.Default())
    flip = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), 180.0))
    x = UsdGeom.Xform.Define(stage, path)
    x.ClearXformOpOrder()
    x.AddTransformOp().Set(flip * local)
    x.GetPrim().CreateAttribute("isaac:nameOverride", Sdf.ValueTypeNames.String).Set(frame_name)
    return path


def _scene_has_clock(stage):
    for p in stage.Traverse():
        t = p.GetAttribute("node:type")
        if t and t.Get() == "isaacsim.ros2.bridge.ROS2PublishClock":
            return True
    return False


def _graph(path, spec):
    stage = omni.usd.get_context().get_stage()
    if stage.GetPrimAtPath(path).IsValid():
        stage.RemovePrim(path)
    og.Controller.edit({"graph_path": path, "evaluator_name": "execution"}, spec)


def _tf_graph(frames, parent, with_clock):
    keys = og.Controller.Keys
    nodes = [("OnTick", "omni.graph.action.OnPlaybackTick"),
             ("Ctx", "isaacsim.ros2.bridge.ROS2Context"),
             ("SimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
             ("ComputeTF", "isaacsim.core.nodes.IsaacComputeTransformTree"),
             ("TF", "isaacsim.ros2.bridge.ROS2PublishTransformTree")]
    links = [("OnTick.outputs:tick", "ComputeTF.inputs:execIn"),
             ("ComputeTF.outputs:execOut", "TF.inputs:execIn"),
             ("ComputeTF.outputs:parentFrames", "TF.inputs:parentFrames"),
             ("ComputeTF.outputs:childFrames", "TF.inputs:childFrames"),
             ("ComputeTF.outputs:translations", "TF.inputs:translations"),
             ("ComputeTF.outputs:orientations", "TF.inputs:orientations"),
             ("Ctx.outputs:context", "TF.inputs:context"),
             ("SimTime.outputs:simulationTime", "TF.inputs:timeStamp")]
    values = [("Ctx.inputs:domain_id", ROS2_DOMAIN_ID),
              ("TF.inputs:topicName", "/tf"),
              ("ComputeTF.inputs:targetPrims", frames)]
    if parent:
        values.append(("ComputeTF.inputs:parentPrim", [parent]))
    if with_clock:
        nodes.append(("Clock", "isaacsim.ros2.bridge.ROS2PublishClock"))
        links += [("OnTick.outputs:tick", "Clock.inputs:execIn"),
                  ("SimTime.outputs:simulationTime", "Clock.inputs:timeStamp"),
                  ("Ctx.outputs:context", "Clock.inputs:context")]
        values.append(("Clock.inputs:topicName", "/clock"))
    _graph(f"{GRAPH_ROOT}/TF", {keys.CREATE_NODES: nodes, keys.CONNECT: links,
                                keys.SET_VALUES: values})


def _camera_graph(side, cam_path, frame_id):
    keys = og.Controller.Keys
    ns = f"{TOPIC_ROOT}/{side}"
    spec = {
        keys.CREATE_NODES: [("OnTick", "omni.graph.action.OnPlaybackTick"),
                            ("Ctx", "isaacsim.ros2.bridge.ROS2Context"),
                            ("RenderProduct", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                            ("Depth", "isaacsim.ros2.bridge.ROS2CameraHelper"),
                            ("CameraInfo", "isaacsim.ros2.bridge.ROS2CameraInfoHelper")],
        keys.CONNECT: [("OnTick.outputs:tick", "RenderProduct.inputs:execIn"),
                       ("RenderProduct.outputs:execOut", "Depth.inputs:execIn"),
                       ("RenderProduct.outputs:execOut", "CameraInfo.inputs:execIn"),
                       ("RenderProduct.outputs:renderProductPath", "Depth.inputs:renderProductPath"),
                       ("RenderProduct.outputs:renderProductPath", "CameraInfo.inputs:renderProductPath"),
                       ("Ctx.outputs:context", "Depth.inputs:context"),
                       ("Ctx.outputs:context", "CameraInfo.inputs:context")],
        keys.SET_VALUES: [("Ctx.inputs:domain_id", ROS2_DOMAIN_ID),
                          ("RenderProduct.inputs:cameraPrim", [cam_path]),
                          ("RenderProduct.inputs:width", WIDTH),
                          ("RenderProduct.inputs:height", HEIGHT),
                          ("Depth.inputs:type", "depth"),
                          ("Depth.inputs:topicName", f"{ns}/depth"),
                          ("Depth.inputs:frameId", frame_id),
                          ("CameraInfo.inputs:topicName", f"{ns}/camera_info"),
                          ("CameraInfo.inputs:frameId", frame_id)],
    }
    if PUBLISH_COLOR:   # same render product: colour pixel-aligned with the depth
        spec[keys.CREATE_NODES].append(("Color", "isaacsim.ros2.bridge.ROS2CameraHelper"))
        spec[keys.CONNECT] += [("RenderProduct.outputs:execOut", "Color.inputs:execIn"),
                               ("RenderProduct.outputs:renderProductPath", "Color.inputs:renderProductPath"),
                               ("Ctx.outputs:context", "Color.inputs:context")]
        spec[keys.SET_VALUES] += [("Color.inputs:type", "rgb"),
                                  ("Color.inputs:topicName", f"{ns}/color"),
                                  ("Color.inputs:frameId", frame_id),
                                  ("Color.inputs:frameSkipCount", COLOR_FRAME_SKIP)]
    _graph(f"{GRAPH_ROOT}/Camera_{side}", spec)


# ── depth preview window ──────────────────────────────────────────────────────
class _Preview:
    """The four GT depth images, colour-mapped near = red -> far = blue, ~5 Hz."""

    def __init__(self, units):
        import omni.replicator.core as rep
        import omni.ui as ui
        self._tiles = []
        self.window = ui.Window("NetraVis6L_USB GT depth", width=2 * PREVIEW_SIZE[0] + 40,
                                height=2 * PREVIEW_SIZE[1] + 90)
        with self.window.frame:
            with ui.VGrid(column_width=PREVIEW_SIZE[0] + 10, row_height=PREVIEW_SIZE[1] + 24):
                for side, _root, cam in units:
                    rp = rep.create.render_product(cam, PREVIEW_SIZE)
                    annot = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
                    annot.attach(rp)
                    with ui.VStack():
                        ui.Label(f"{side}", height=18)
                        provider = ui.ByteImageProvider()
                        ui.ImageWithProvider(provider, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1])
                    self._tiles.append((annot, rp, provider))
        self._tick = 0
        self._sub = (omni.kit.app.get_app().get_update_event_stream()
                     .create_subscription_to_pop(self._update, name="netravis gt preview"))

    def _update(self, _):
        self._tick += 1
        if self._tick % 12:
            return
        for annot, _rp, provider in self._tiles:
            d = np.asarray(annot.get_data(), dtype=np.float32)
            if d.size == 0:
                continue
            d = d.reshape(PREVIEW_SIZE[1], PREVIEW_SIZE[0])
            t = np.clip(np.nan_to_num(d, nan=0, posinf=0) / PREVIEW_MAX_M, 0, 1)
            valid = (d > 0) & np.isfinite(d)
            rgba = np.zeros((*d.shape, 4), np.uint8)
            rgba[..., 0] = (255 * (1 - t)).astype(np.uint8)
            rgba[..., 1] = (255 * (1 - np.abs(2 * t - 1))).astype(np.uint8)
            rgba[..., 2] = (255 * t).astype(np.uint8)
            rgba[..., 3] = 255
            rgba[~valid, :3] = 0
            provider.set_bytes_data(rgba.flatten().tolist(), [PREVIEW_SIZE[0], PREVIEW_SIZE[1]])

    def destroy(self):
        self._sub = None
        for annot, rp, _p in self._tiles:
            try:
                annot.detach()
                rp.destroy()
            except Exception:
                pass
        self._tiles = []
        self.window.visible = False


# ── main / teardown ───────────────────────────────────────────────────────────
async def main():
    global _preview
    teardown(stop_timeline=False)
    mgr = omni.kit.app.get_app().get_extension_manager()
    if not mgr.is_extension_enabled("isaacsim.ros2.bridge"):
        print("[netravis] enable the ROS 2 bridge first: Window -> Extensions -> isaacsim.ros2.bridge")
        return
    stage = omni.usd.get_context().get_stage()
    units = _find_units(stage)
    if not units:
        print(f"[netravis] no {MODEL} unit with a Depth_GT camera in the stage -- open the example scene")
        return
    timeline = omni.timeline.get_timeline_interface()
    if not timeline.is_playing():
        timeline.play()
        await _wait(10)

    stage.DefinePrim(GRAPH_ROOT, "Scope")
    frames = []
    for side, _root, cam in units:
        frame = f"netravis_{side}_depth"
        frames.append(_optical_frame(stage, cam, frame))
        _camera_graph(side, cam, frame)
    parent = _find_base_link(stage, units[0][1])
    with_clock = not _scene_has_clock(stage)
    _tf_graph(frames, parent, with_clock)
    await _wait(10)
    if PREVIEW_WINDOW:
        _preview = _Preview(units)

    print(f"\n[netravis] publishing {len(units)} camera(s), domain {ROS2_DOMAIN_ID}, "
          f"TF parent {parent or 'world'}{', + /clock' if with_clock else ''}")
    topics = "depth, color, camera_info" if PUBLISH_COLOR else "depth, camera_info"
    for side, root, _cam in units:
        print(f"    {TOPIC_ROOT}/{side}/{{{topics}}}   frame netravis_{side}_depth   ({root})")
    print("[netravis] stop: teardown()\n")


def teardown(stop_timeline=True):
    """Stop publishing: close the preview, remove the graphs, optionally stop the timeline."""
    global _preview
    if _preview is not None:
        _preview.destroy()
        _preview = None
    stage = omni.usd.get_context().get_stage()
    if stage and stage.GetPrimAtPath(GRAPH_ROOT).IsValid():
        stage.RemovePrim(GRAPH_ROOT)
        print("[netravis] publishers removed")
    if stop_timeline:
        omni.timeline.get_timeline_interface().stop()


async def _run():
    try:
        await main()
    except Exception:
        import traceback
        traceback.print_exc()

asyncio.ensure_future(_run())
