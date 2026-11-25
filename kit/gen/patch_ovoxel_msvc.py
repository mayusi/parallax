"""patch_ovoxel_msvc.py — make TRELLIS.2's o-voxel extension compile with MSVC + nvcc on Windows (idempotent).

o-voxel is written for GCC; three things stop MSVC (measured on VS 2022 14.44 + CUDA 13.1, 2026-10-06):
- its setup.py passes GCC flags only; CuMesh and FlexGEMM (same author) add MSVC conformance flags "required for
  MSVC + nvcc + torch headers" — without /permissive- nvcc's front end finds `std` ambiguous in torch's
  compiled_autograd.h (C2872). The same Windows flags are added here.
- brace lists of size_t into torch's int64_t sizes are narrowing conversions: an error in MSVC (C2398) — cast.
- `1e-6d` / `0.0d` use GCC's `d` literal suffix (C3688) — plain double literals mean the same.
None of this changes what the code computes.

    python kit/gen/patch_ovoxel_msvc.py <TRELLIS.2 checkout>/o-voxel
"""

import os
import re
import sys

WIN_FLAGS = '''if os.name == "nt":  # (kit: MSVC + nvcc, as CuMesh / FlexGEMM build on Windows)
    CXX_FLAGS = ["/O2", "/std:c++17", "/EHsc", "/permissive-", "/Zc:__cplusplus"]
    NVCC_FLAGS = ["-O3", "-std=c++17", "--expt-relaxed-constexpr", "--extended-lambda", "-Xcompiler=/std:c++17",
                  "-Xcompiler=/EHsc", "-Xcompiler=/permissive-", "-Xcompiler=/Zc:__cplusplus",
                  "-allow-unsupported-compiler"] + cc_flag
else:
    CXX_FLAGS = ["-O3", "-std=c++17"]
    NVCC_FLAGS = ["-O3", "-std=c++17"] + cc_flag

setup('''

CASTS = {
    "src/io/svo.cpp": [("{svo.size()}", "{(int64_t)svo.size()}"), ("{codes.size()}", "{(int64_t)codes.size()}")],
    "src/io/filter_parent.cpp": [("torch::zeros({N_leaf, C}", "torch::zeros({(int64_t)N_leaf, (int64_t)C}")],
    "src/io/filter_neighbor.cpp": [("torch::zeros({N, C}", "torch::zeros({(int64_t)N, (int64_t)C}")],
}


def patch(root):
    changed = []
    setup_py = os.path.join(root, "setup.py")
    s = open(setup_py, encoding="utf-8").read()
    if "CXX_FLAGS" not in s:
        s = s.replace("\nsetup(", "\n" + WIN_FLAGS, 1)
        s = s.replace('"cxx": ["-O3", "-std=c++17"],', '"cxx": CXX_FLAGS,')
        s = s.replace('"nvcc": ["-O3","-std=c++17"] + cc_flag,', '"nvcc": NVCC_FLAGS,')
        if '"cxx": CXX_FLAGS' not in s or '"nvcc": NVCC_FLAGS' not in s:
            raise RuntimeError("o-voxel setup.py changed upstream: patch its compile flags by hand")
        open(setup_py, "w", encoding="utf-8", newline="\n").write(s)
        changed.append("setup.py")
    for rel, pairs in CASTS.items():
        p = os.path.join(root, rel)
        s = open(p, encoding="utf-8").read()
        t = s
        for a, b in pairs:
            t = t.replace(a, b)
        if t != s:
            open(p, "w", encoding="utf-8", newline="\n").write(t)
            changed.append(rel)
    p = os.path.join(root, "src", "convert", "flexible_dual_grid.cpp")
    s = open(p, encoding="utf-8").read()
    t = re.sub(r"(?<![\w.])(\d+\.\d*|\d*\.\d+|\d+)(e[+-]?\d+)?d\b", r"\1\2", s)
    if t != s:
        open(p, "w", encoding="utf-8", newline="\n").write(t)
        changed.append("src/convert/flexible_dual_grid.cpp")
    return changed


if __name__ == "__main__":
    print("patched:", ", ".join(patch(sys.argv[1])) or "nothing (already patched)")
