"""uvraster.py — the two nvdiffrast calls TRELLIS.2's GLB export makes, in plain PyTorch (kit-owned code).

TRELLIS.2 (MIT) bakes its textures by rasterizing the new mesh in UV space: which triangle covers each texel, and
where (barycentrics), so the texel's 3D position can sample the generated voxel attributes. It does that with
nvdiffrast, whose NVIDIA Source Code License (1-Way Commercial) allows non-commercial use only (s.3.3) — a game
asset is commercial use. This module implements exactly the subset that export uses, with nvdiffrast's conventions:

    ctx = RasterizeCudaContext()
    rast, _ = rasterize(ctx, pos, tri, resolution=[H, W])   # pos (1, V, 4) clip space, tri (F, 3)
    out, _ = interpolate(attr, rast, tri)                    # attr (1, V, C) -> (1, H, W, C)

rast[..., 0:2] are the barycentrics (u, v) of the triangle's first two corners (the third weighs 1 - u - v),
rast[..., 2] is z/w and rast[..., 3] the triangle's index + 1 (0 = empty). Pixel (row r, column c) samples clip
(2(c + 0.5)/W - 1, 2(r + 0.5)/H - 1): row 0 is clip y = -1, the OpenGL bottom, as in nvdiffrast. No depth test (a
UV layout does not overlap); where triangles share a texel the later one wins. The runner installs this module as
`nvdiffrast.torch` (kit/gen/trellis2_run.py), so nvdiffrast is never installed.
"""

import torch


class RasterizeCudaContext:
    """nvdiffrast's context object: this rasterizer keeps no state."""

    def __init__(self, *args, **kwargs):
        pass


class RasterizeGLContext(RasterizeCudaContext):
    pass


def rasterize(ctx, pos, tri, resolution, ranges=None, grad_db=True, chunk=2_000_000):
    """the orthographic coverage of `tri` -> (rast (1, H, W, 4) float32, None). `chunk` caps the candidate texels
    examined at once (a triangle's bounding box is scanned, then each texel is tested)."""
    if ranges is not None:
        raise NotImplementedError("uvraster: range mode is not used by the TRELLIS.2 export")
    H, W = int(resolution[0]), int(resolution[1])
    p = pos[0] if pos.dim() == 3 else pos
    xyzw = p.float()
    w = xyzw[:, 3:4]
    ndc = xyzw[:, :3] / torch.where(w.abs() > 1e-12, w, torch.ones_like(w))
    # texel space: pixel centres sit on integers
    vx = (ndc[:, 0] + 1.0) * 0.5 * W - 0.5
    vy = (ndc[:, 1] + 1.0) * 0.5 * H - 0.5
    vz = ndc[:, 2]
    t = tri.long()
    out = torch.zeros((1, H, W, 4), device=p.device, dtype=torch.float32)
    if t.numel() == 0:
        return out, None
    x0, x1, x2 = vx[t[:, 0]], vx[t[:, 1]], vx[t[:, 2]]
    y0, y1, y2 = vy[t[:, 0]], vy[t[:, 1]], vy[t[:, 2]]
    lo_x = torch.clamp(torch.ceil(torch.minimum(torch.minimum(x0, x1), x2)), 0, W - 1).long()
    hi_x = torch.clamp(torch.floor(torch.maximum(torch.maximum(x0, x1), x2)), 0, W - 1).long()
    lo_y = torch.clamp(torch.ceil(torch.minimum(torch.minimum(y0, y1), y2)), 0, H - 1).long()
    hi_y = torch.clamp(torch.floor(torch.maximum(torch.maximum(y0, y1), y2)), 0, H - 1).long()
    bw = (hi_x - lo_x + 1).clamp(min=0)
    bh = (hi_y - lo_y + 1).clamp(min=0)
    count = bw * bh
    # a triangle with no texel centre inside its box covers nothing (its box test fails above: hi < lo)
    count = torch.where((hi_x >= lo_x) & (hi_y >= lo_y), count, torch.zeros_like(count))
    # signed doubled area: degenerate triangles cover nothing
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    count = torch.where(area.abs() > 1e-12, count, torch.zeros_like(count))
    ends = torch.cumsum(count, 0)
    starts = ends - count
    total = int(ends[-1].item()) if ends.numel() else 0
    flat = out.view(H * W, 4)
    done = 0
    while done < total:
        n = min(chunk, total - done)
        idx = torch.arange(done, done + n, device=p.device)
        f = torch.searchsorted(ends, idx, right=True)  # the triangle each candidate texel belongs to
        local = idx - starts[f]
        px = lo_x[f] + local % bw[f]
        py = lo_y[f] + torch.div(local, bw[f], rounding_mode="floor")
        cx, cy = px.float(), py.float()
        a = area[f]
        # barycentrics by edge functions: the weight of a corner is the area opposite it
        w0 = ((x1[f] - cx) * (y2[f] - cy) - (x2[f] - cx) * (y1[f] - cy)) / a
        w1 = ((x2[f] - cx) * (y0[f] - cy) - (x0[f] - cx) * (y2[f] - cy)) / a
        w2 = 1.0 - w0 - w1
        eps = -1e-6
        inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        if inside.any():
            fi = f[inside]
            z = w0[inside] * vz[t[fi, 0]] + w1[inside] * vz[t[fi, 1]] + w2[inside] * vz[t[fi, 2]]
            vals = torch.stack([w0[inside], w1[inside], z, (fi + 1).float()], dim=-1)
            flat[(py[inside] * W + px[inside])] = vals
        done += n
    return out, None


def interpolate(attr, rast, tri, rast_db=None, diff_attrs=None):
    """vertex attributes at each covered pixel -> (out (1, H, W, C), None); empty pixels stay 0"""
    a = attr[0] if attr.dim() == 3 else attr
    r = rast[0]
    tid = r[..., 3].long() - 1
    mask = tid >= 0
    out = torch.zeros((r.shape[0], r.shape[1], a.shape[-1]), device=a.device, dtype=a.dtype)
    if mask.any():
        corners = tri.long()[tid[mask]]
        u = r[..., 0][mask].unsqueeze(-1).to(a.dtype)
        v = r[..., 1][mask].unsqueeze(-1).to(a.dtype)
        out[mask] = u * a[corners[:, 0]] + v * a[corners[:, 1]] + (1 - u - v) * a[corners[:, 2]]
    return out.unsqueeze(0), None
