# Build the local inference environment.
#
# We do NOT run the container. We reproduce its stack natively, because
# torch 2.8.0+cu128 ships sm_120 kernels and this machine's RTX 5090 Laptop GPU
# is sm_120. Python is pinned to 3.10 to match the container and to keep
# nnunetv2 2.4.2 available as a fallback if the checkpoints will not load.
#
# Idempotent. Every step checks its exit code, because a previous version of
# this script exited 0 while installing nothing.

$CONDA = "C:\Users\dekay\miniconda3\Scripts\conda.exe"
$ENVNAME = "spinelab"
$PY = "C:\Users\dekay\miniconda3\envs\$ENVNAME\python.exe"
$HERE = $PSScriptRoot

function Step($label) { Write-Output ""; Write-Output ("=" * 70); Write-Output $label; Write-Output ("=" * 70) }
function Must($what) {
    if ($LASTEXITCODE -ne 0) { Write-Output "ABORT: $what failed with exit code $LASTEXITCODE"; exit 1 }
}

Step "1. python 3.10 environment"
if (-not (Test-Path -LiteralPath $PY)) {
    & $CONDA create -n $ENVNAME python=3.10 -y
    Must "conda create"
} else {
    Write-Output "already exists, reusing"
}
if (-not (Test-Path -LiteralPath $PY)) { Write-Output "ABORT: interpreter not at $PY"; exit 1 }
& $PY -c "import sys; print('interpreter', sys.executable); print('version', sys.version.split()[0])"
Must "interpreter probe"

Step "2. torch 2.8.0 from the cu128 index"
& $PY -m pip install --quiet --upgrade pip
& $PY -m pip install torch==2.8.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
Must "torch install"

Step "3. GPU gate: does this card actually execute kernels"
& $PY (Join-Path $HERE "probe_gpu.py")
Must "GPU probe"

Step "4. pipeline dependencies"
& $PY -m pip install --quiet numpy nibabel pydicom psutil scipy tqdm torchio PyYAML Pillow gunicorn flask batchgenerators acvl-utils dynamic-network-architectures opencv-python pylibjpeg pylibjpeg-libjpeg matplotlib seaborn pandas SimpleITK
Must "dependency install"

Step "5. totalspineseg and its nnunetv2 pin"
& $PY -m pip install --quiet totalspineseg
Must "totalspineseg install"
& $PY -m pip show nnunetv2 totalspineseg | Select-String -Pattern '^(Name|Version):'

Step "6. checkpoint gate: trainer resolution and real deserialisation"
& $PY (Join-Path $HERE "probe_checkpoints.py")
$ckptCode = $LASTEXITCODE
if ($ckptCode -ne 0) {
    Write-Output ""
    Write-Output "Checkpoint gate FAILED (exit $ckptCode). Retrying with nnunetv2 pinned to 2.4.2,"
    Write-Output "which is the version the notes tie to nnUNetTrainer_DASegOrd0_NoMirroring."
    & $PY -m pip install --quiet "nnunetv2==2.4.2"
    if ($LASTEXITCODE -eq 0) {
        & $PY (Join-Path $HERE "probe_checkpoints.py")
        $ckptCode = $LASTEXITCODE
    } else {
        Write-Output "nnunetv2==2.4.2 install itself failed on python 3.10"
    }
}

Step "7. freeze"
& $PY -m pip freeze | Out-File -LiteralPath (Join-Path $HERE "requirements.lock") -Encoding utf8
Write-Output "wrote requirements.lock ($((Get-Content -LiteralPath (Join-Path $HERE 'requirements.lock')).Count) lines)"

Step "SUMMARY"
Write-Output "interpreter    : $PY"
Write-Output "checkpoint gate: $(if ($ckptCode -eq 0) { 'PASSED' } else { "FAILED (exit $ckptCode)" })"
exit $ckptCode
