"""Confirm the GPU actually executes kernels. Fails loudly, exits nonzero."""
import sys

import torch

print("torch          ", torch.__version__)
print("cuda runtime   ", torch.version.cuda)
print("is_available   ", torch.cuda.is_available())
print("arch_list      ", torch.cuda.get_arch_list())

if not torch.cuda.is_available():
    print("FAIL: no CUDA device visible")
    sys.exit(1)

name = torch.cuda.get_device_name(0)
cc = torch.cuda.get_device_capability(0)
sm = "sm_%d%d" % cc
total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
print("device         ", name)
print("capability     ", sm)
print("total memory   %.1f GiB" % total)
print("device count   ", torch.cuda.device_count())

if sm not in torch.cuda.get_arch_list():
    print("WARNING: %s is not in the compiled arch list, kernels may fail" % sm)

# torch.cuda.is_available() returns True even when no kernel image exists for the
# device, which is the exact trap that makes a Pascal card look usable. Only an
# actual kernel launch settles it.
try:
    x = torch.randn(4096, 4096, device="cuda", dtype=torch.float32)
    y = (x @ x).sum().item()
    torch.cuda.synchronize()
    print("fp32 matmul     OK, finite:", y == y)
    h = torch.randn(2048, 2048, device="cuda", dtype=torch.float16)
    torch.cuda.synchronize()
    print("fp16 matmul     OK, finite:", (h @ h).sum().item() == (h @ h).sum().item())
    try:
        b = torch.randn(512, 512, device="cuda", dtype=torch.bfloat16)
        (b @ b).sum().item()
        torch.cuda.synchronize()
        print("bf16 matmul     OK")
    except Exception as e:
        print("bf16 matmul     unsupported:", type(e).__name__)
    conv = torch.nn.Conv3d(1, 8, 3, padding=1).cuda()
    v = torch.randn(1, 1, 48, 48, 48, device="cuda")
    conv(v)
    torch.cuda.synchronize()
    print("conv3d          OK")
except Exception as e:
    print("FAIL: kernel launch failed: %s: %s" % (type(e).__name__, e))
    sys.exit(2)

print("GPU GATE PASSED")
