"""probe_mitsuba.py — does Mitsuba 3 work on THIS GPU, forward AND backward? (run in the mitsuba env)

    <env>/python kit/tools/probe_mitsuba.py [--variant cuda_ad_rgb] [--size 64] [--spp 16]

A textured square in front of the camera, lit evenly. Forward: render it. Backward: render it again with a darker
texture and ask for the gradient of the image difference (mean squared) with respect to every texel. The gradient
must be finite, not zero, and say "brighter" (negative): the darker texture made the picture too dark.
Prints a line per phase as it goes (a caller with a timeout sees where it stopped), then one JSON verdict line.
Nothing is written to disk (Dr.Jit keeps its own kernel cache in ~/.drjit).
"""

import json
import math
import sys
import time


def _opt(argv, flag, default):
    return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}),
          flush=True)
    return 0 if status == "pass" else 1


def scene_dict(mi, size, texels, value):
    tex = mi.TensorXf([value] * (texels * texels * 3), shape=(texels, texels, 3))
    return {
        "type": "scene",
        "integrator": {"type": "prb", "max_depth": 2},
        "sensor": {
            "type": "perspective", "fov": 40,
            "to_world": mi.ScalarTransform4f().look_at(origin=[0, 0, 4], target=[0, 0, 0], up=[0, 1, 0]),
            "film": {"type": "hdrfilm", "width": size, "height": size, "rfilter": {"type": "box"},
                     "pixel_format": "rgb"},
        },
        "light": {"type": "constant", "radiance": {"type": "rgb", "value": 1.0}},
        "square": {"type": "rectangle",
                   "bsdf": {"type": "diffuse", "reflectance": {"type": "bitmap", "data": tex, "raw": True}}},
    }


def total(dr, x):
    """a tensor or array summed to one python float (reading it back runs the kernels)"""
    arr = x.array if hasattr(x, "array") else x
    s = dr.sum(arr, axis=None)
    return float(s[0]) if hasattr(s, "__getitem__") and not isinstance(s, float) else float(s)


def main(argv):
    variant, size, spp = _opt(argv, "--variant", "cuda_ad_rgb"), _opt(argv, "--size", 64), _opt(argv, "--spp", 16)
    import drjit as dr  # noqa: PLC0415
    import mitsuba as mi  # noqa: PLC0415

    versions = {"mitsuba": mi.__version__, "drjit": dr.__version__}
    if variant not in mi.variants():
        return emit("fail", f"mitsuba: variant {variant} is not in this build ({', '.join(mi.variants())})",
                    "use one of the listed variants: --variant <name>", versions=versions)
    t0 = time.time()
    mi.set_variant(variant)
    print(f"variant {variant} set ({time.time() - t0:.1f} s)", flush=True)

    texels = 8
    t0 = time.time()
    scene = mi.load_dict(scene_dict(mi, size, texels, 0.5))
    ref = mi.render(scene, spp=spp, seed=0)
    fwd_mean = total(dr, ref) / (size * size * 3)
    fwd_s = time.time() - t0
    print(f"forward ok: {size} x {size} px, {spp} spp, mean {fwd_mean:.4f} ({fwd_s:.1f} s)", flush=True)
    if not math.isfinite(fwd_mean) or fwd_mean <= 0:
        return emit("fail", f"mitsuba {variant}: the forward render is black or not finite (mean {fwd_mean})",
                    "update the NVIDIA driver; try --variant scalar_rgb to split GPU from install problems",
                    versions=versions, forward_mean=fwd_mean)

    t0 = time.time()
    params = mi.traverse(scene)
    key = next(k for k in params.keys() if k.endswith("reflectance.data"))
    params[key] = mi.TensorXf([0.3] * (texels * texels * 3), shape=(texels, texels, 3))
    dr.enable_grad(params[key])
    params.update()
    img = mi.render(scene, params, spp=spp, seed=1)
    loss = dr.mean(dr.square(img - ref), axis=None)
    dr.backward(loss)
    grad = dr.grad(params[key])
    g_sum = total(dr, grad)
    g_abs = total(dr, dr.abs(grad))
    bwd_s = time.time() - t0
    print(f"backward ok: d(loss)/d(texture) summed {g_sum:.3e}, |sum| {g_abs:.3e} ({bwd_s:.1f} s)", flush=True)
    good = math.isfinite(g_sum) and g_abs > 0 and g_sum < 0
    return emit(
        "pass" if good else "fail",
        f"mitsuba {versions['mitsuba']} / drjit {versions['drjit']} on {variant}: forward {fwd_s:.1f} s (mean "
        f"{fwd_mean:.3f}), backward {bwd_s:.1f} s (texture gradient {g_sum:.2e}"
        + (", says brighter: right)" if good else ", WRONG: must be finite, non-zero and negative)"),
        "none — proceed" if good else "the gradient is wrong: report it with the versions above",
        versions=versions, variant=variant, forward_s=round(fwd_s, 2), backward_s=round(bwd_s, 2),
        forward_mean=round(fwd_mean, 5), grad_sum=g_sum, grad_abs=g_abs)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
