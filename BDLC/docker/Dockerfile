# Build environment for the external baselines (Q1 step 1).
#
# The image actually used, bdlc-baselines-env:2026-10-29, was created on
# 2026-10-29 with exactly these steps (apt-get update, then install) in a
# container; the full list of installed package versions is in packages.tsv.
# apt indexes came from archive.ubuntu.com / security.ubuntu.com on that day,
# so a later rebuild may pull newer patch versions; compare with packages.tsv.
FROM ubuntu@sha256:78d4744ead1f5b19b04d0df558ab182a5300903900755e515b2ca4d10eb2044d

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential=12.10ubuntu1 \
      cmake=3.28.3-1build7 \
      pkg-config=1.8.1-2build1 \
      libpng-dev=1.6.43-5ubuntu0.7 \
 && dpkg-query -W -f='${Package}\t${Version}\n' > /etc/bdlc-packages.tsv

# Baselines are then built with:
#   docker run -v <BDLC>/downloads/baselines:/src:ro -v <BDLC>/docker:/scripts:ro \
#              -v <BDLC>/docker/build_out:/out bdlc-baselines-env:2026-10-29 \
#              bash /scripts/build_baselines.sh
# and the container is committed as bdlc-baselines:2026-10-29.
