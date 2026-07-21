# Digest-pin the base image when publishing a production audit image.  The
# unpinned tag keeps this recipe locally buildable; the resulting image digest
# is what every audit command must record and consume.
FROM python:3.10-slim

RUN python -m pip install --no-cache-dir \
    "numpy==1.24.4" \
    "pandas==1.5.3" \
    "scipy==1.10.1" \
    "scikit-learn==1.2.2"

RUN useradd --create-home --uid 10001 audit
USER audit
WORKDIR /workspace
