"""footage_landmarks.py — the extraction half of `kit anim dossier measure` from video (mission 04-anim 7): MediaPipe's
Pose Landmarker (VETLOG 2026-10-16, mediapipe 1.0.1 + pose_landmarker_full.task, Apache-2.0) reads a clip and writes
its 33 WORLD landmarks per frame (metres, origin = the hip centre, y flipped to UP so footage_measure reads it
directly). Frames where no body was found are null. Numbers only - the clip and the landmarks stay in the git-ignored
_artifacts/footage/ (measure-only, private; the owner: "find a video yourself").
    python kit/anim/footage_landmarks.py <clip.mp4> <out.landmarks.json> [--start S] [--end S] [--poses 2]
  --poses 2: every body, kept on TRACKS (a fight: the measure finds who got hit) -> {"tracks": [{"start", "frames"}]}"""
import json
import os
import sys

MODEL = os.path.join(os.path.dirname(__file__), "..", "..", "_artifacts", "models", "mediapipe", "pose_landmarker_full.task")


def track(dets, max_jump=0.15):
    """per-frame detections [(img_xy, world, vis)] -> stable TRACKS: each detection joins the track whose last image
    position (the hip centre, normalised 0..1) is nearest within `max_jump`, else it starts a new one; a camera cut
    starts new tracks (a jump), so a track never spans two shots. -> [{"start": frame, "frames": [world|None ...]}]"""
    tracks, live = [], []
    for f, ds in enumerate(dets):
        used = set()
        for det in sorted(ds, key=lambda d: d[0][0]):
            xy, w, v = det[:3]
            im = det[3] if len(det) > 3 else None                   # the image landmarks (older callers: none)
            best, bd = None, max_jump
            for ti in live:
                if ti in used:
                    continue
                last = tracks[ti]["last"]
                dd = ((xy[0] - last[0]) ** 2 + (xy[1] - last[1]) ** 2) ** 0.5
                if dd < bd:
                    best, bd = ti, dd
            if best is None:
                tracks.append({"start": f, "frames": [], "vis": [], "img": [], "last": xy})
                best = len(tracks) - 1
                live.append(best)
            tr = tracks[best]
            while tr["start"] + len(tr["frames"]) < f:                 # a short miss inside the track: a gap
                tr["frames"].append(None)
                tr["vis"].append(None)
                tr["img"].append(None)
            tr["frames"].append(w)
            tr["vis"].append(v)
            tr["img"].append(im)
            tr["last"] = xy
            used.add(best)
        live = [ti for ti in live if tracks[ti]["start"] + len(tracks[ti]["frames"]) >= f - 2]
    for tr in tracks:
        tr.pop("last")
    return [tr for tr in tracks if sum(1 for x in tr["frames"] if x) >= 10]


def extract(path, start=0.0, end=None, model=MODEL, poses=1):
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    if not os.path.isfile(model):
        raise SystemExit(f"no pose model at {model} - see VETLOG (MediaPipe 2026-10-16) for the pinned download")
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    opts = vision.PoseLandmarkerOptions(base_options=BaseOptions(model_asset_path=model),
                                        running_mode=vision.RunningMode.VIDEO, num_poses=poses,
                                        min_pose_detection_confidence=0.5, min_tracking_confidence=0.5)
    frames, vis, dets, i = [], [], [], 0
    with vision.PoseLandmarker.create_from_options(opts) as det:
        while True:
            ok, img = cap.read()
            if not ok:
                break
            t = i / fps
            i += 1
            if t < start:
                continue
            if end is not None and t > end:
                break
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            res = det.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(t * 1000))
            if poses > 1:                                  # every body in the frame (a fight: who got hit?)
                fr = []
                for w, im in zip(res.pose_world_landmarks or [], res.pose_landmarks or []):
                    xy = (round(0.5 * (im[23].x + im[24].x), 4), round(0.5 * (im[23].y + im[24].y), 4))
                    # + the IMAGE landmarks (0..1, y down): world landmarks are hip-centred, so a STEP that carries the
                    # body over the ground only shows on the image (the owner's "geniune foot work", 2026-10-18)
                    fr.append((xy, [[round(p.x, 4), round(-p.y, 4), round(p.z, 4)] for p in w],
                               [round(p.visibility or 0.0, 2) for p in im], [[round(p.x, 4), round(p.y, 4)] for p in im]))
                dets.append(fr)
                continue
            if res.pose_world_landmarks:
                w = res.pose_world_landmarks[0]
                frames.append([[round(p.x, 4), round(-p.y, 4), round(p.z, 4)] for p in w])
                vis.append([round(p.visibility or 0.0, 2) for p in res.pose_landmarks[0]])
            else:
                frames.append(None)
                vis.append(None)
    cap.release()
    if poses > 1:
        return {"fps": fps, "source": os.path.basename(path), "start_s": start, "n_frames": len(dets), "tracks": track(dets)}
    return {"fps": fps, "source": os.path.basename(path), "start_s": start, "frames": frames, "vis": vis}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    opt = {k: float(a[a.index(k) + 1]) for k in ("--start", "--end", "--poses") if k in a}
    d = extract(a[0], opt.get("--start", 0.0), opt.get("--end"), poses=int(opt.get("--poses", 1)))
    with open(a[1], "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, separators=(",", ":"))
    if "tracks" in d:
        print(json.dumps({"schema": 1, "status": "pass" if d["tracks"] else "fail",
                          "summary": f"{d['source']}: {len(d['tracks'])} body track(s) over {d['n_frames']} frames at {d['fps']:.2f} fps",
                          "next_action": f"python kit/anim/footage_measure.py {a[1]} --reaction"}))
        sys.exit(0)
    found = sum(1 for x in d["frames"] if x)
    print(json.dumps({"schema": 1, "status": "pass" if found else "fail",
                      "summary": f"{d['source']}: {found}/{len(d['frames'])} frames with a body at {d['fps']:.2f} fps",
                      "next_action": f"python kit/anim/footage_measure.py {a[1]}"}))
