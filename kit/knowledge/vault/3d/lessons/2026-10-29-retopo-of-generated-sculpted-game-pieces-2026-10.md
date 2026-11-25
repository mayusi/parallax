---
kind: lesson
area: 3d
date: 2026-10-29
by: mayusi
source: "kit/lessons/3d.md"
links: ["[[3d/index]]"]
project: Parallax
---

Retopo of generated / sculpted game pieces (2026-10-30, Sample Game R30): QuadriFlow refuses them in background Blender 5.2 even when manifold; a coarse VOXEL remesh sized from the target count (corrected once from the count it gave) + relax + shrinkwrap gives clean all-quad watertight limbs - but merge the R6 block into a garment TUBE first (trousers, sleeves) or the voxels keep the hollow and the low shows its inside, and wrap with OUTSIDE_SURFACE. Voxels cannot hold thin things: a coat sheet -> rebuild its own quad grid from the build's parametric profile + solidify; a crisp sole -> MODEL it (rings measured on the high by inward rays, smoothed round the loop, lofted). Bake traps: Image.save() of a generated image needs save(filepath=abs); a 2-pass bake into one image needs render.bake.use_clear=False on pass 2; joining meshes remaps material indices (give every mesh the same slots BEFORE the join; clearing slots resets indices).
