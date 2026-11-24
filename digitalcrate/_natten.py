"""Neighborhood attention in plain PyTorch: the four NATTEN 0.17 functions All-In-One's model calls, so it runs
without compiling NATTEN (which has no macOS build) and on Apple's GPU.

Semantics as NATTEN: with dilation d, positions split into d interleaved groups; within a group each query attends to
the kernel_size nearest positions, the window shifted inward at the edges; rpb is indexed by relative position.
Checked against NATTEN 0.17.1 on random inputs (tests/test_units.py keeps the edge cases honest).
"""
import sys
import types

import torch


def _idx(n, k, d, device):
    """(n, k) absolute neighbour positions and (n, k) relative positions (+ k - 1, an rpb index)."""
    i = torch.arange(n, device=device)
    g, ig = i % d, i // d
    glen = (n - g + d - 1) // d  # length of each position's group
    start = (ig - k // 2).clamp(min=0)
    start = torch.minimum(start, glen - k)
    j = start[:, None] + torch.arange(k, device=device)[None, :]  # index within the group
    return g[:, None] + j * d, j - ig[:, None] + k - 1


def natten1dqkrpb(q, k, rpb, kernel_size, dilation):
    n = q.shape[2]
    nb, rel = _idx(n, kernel_size, dilation, q.device)
    kk = k[:, :, nb]  # B h n K D
    a = (q.unsqueeze(3) * kk).sum(-1)
    return a + rpb[:, rel].unsqueeze(0) if rpb is not None else a


def natten1dav(attn, v, kernel_size, dilation):
    n = v.shape[2]
    nb, _ = _idx(n, kernel_size, dilation, v.device)
    return (attn.unsqueeze(-1) * v[:, :, nb]).sum(3)


def natten2dqkrpb(q, k, rpb, kernel_size, dilation):
    B, h, H, W, D = q.shape
    K = kernel_size
    nh, rh = _idx(H, K, dilation, q.device)
    nw, rw = _idx(W, K, dilation, q.device)
    kk = k[:, :, nh][:, :, :, :, nw]  # B h H Kh W Kw D
    kk = kk.permute(0, 1, 2, 4, 3, 5, 6)  # B h H W Kh Kw D
    a = (q[:, :, :, :, None, None, :] * kk).sum(-1)  # B h H W Kh Kw
    if rpb is not None:
        bias = rpb[:, rh[:, None, :, None], rw[None, :, None, :]]  # h H W Kh Kw
        a = a + bias.unsqueeze(0)
    return a.reshape(B, h, H, W, K * K)


def natten2dav(attn, v, kernel_size, dilation):
    B, h, H, W, D = v.shape
    K = kernel_size
    nh, _ = _idx(H, K, dilation, v.device)
    nw, _ = _idx(W, K, dilation, v.device)
    vv = v[:, :, nh][:, :, :, :, nw].permute(0, 1, 2, 4, 3, 5, 6)  # B h H W Kh Kw D
    a = attn.reshape(B, h, H, W, K, K, 1)
    return (a * vv).sum((4, 5))


def install():
    """Make `import natten` / `from natten.functional import …` resolve to this (only if NATTEN isn't installed)."""
    if "natten" in sys.modules:
        return
    try:
        import natten  # noqa: F401  (a real install wins)
        return
    except Exception:
        pass
    m = types.ModuleType("natten")
    f = types.ModuleType("natten.functional")
    for name in ("natten1dqkrpb", "natten1dav", "natten2dqkrpb", "natten2dav"):
        setattr(f, name, globals()[name])
    m.functional = f
    m.__version__ = "0.17.1-torch"
    sys.modules["natten"] = m
    sys.modules["natten.functional"] = f
