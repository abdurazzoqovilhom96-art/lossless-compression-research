#!/bin/bash
# Builds the external baselines inside bdlc-baselines-env:2026-10-29.
#   /src     downloads/baselines (read-only): the source archives
#   /scripts BDLC/docker (read-only): this script and cpso_cli.cpp
#   /out     BDLC/docker/build_out: logs, binary hashes
# Each project is built with its own default flags. The only source change is
# patches/ecc_ub_fixes.patch (see ecc() below).
set -u
W=/opt/baselines
mkdir -p "$W/src" "$W/bin" /out/logs
cd "$W/src" || exit 1
for a in /src/JBIG-KIT/jbigkit-2.1.tar.gz /src/FLIF/FLIF-v0.4.tar.gz \
         /src/ECC/ECC-fe3f2f1.tar.gz /src/Compresso/compresso-b1f7fd6.tar.gz \
         "/src/HM-SCM/HM-16.21+SCM-8.8.tar.gz"; do
    tar -xzf "$a" || { echo "extract failed: $a"; exit 1; }
done

status=0
build() {
    local name=$1; shift
    if "$@" > "/out/logs/$name.log" 2>&1; then
        echo "$name: OK"
    else
        echo "$name: FAILED (logs/$name.log)"; status=1
    fi
}

# HM builds with -Werror; GCC 13 reports a false-positive -Warray-bounds in
# TComLoopFilter.cpp:214, so only that warning is kept non-fatal. Warning
# flags do not change generated code; the HM sources are not modified.
HM_EXTRA_CXXFLAGS="-Wno-error=array-bounds"

# every step is chained with && so that any failure fails the build
jbig()  { cd "$W/src/jbigkit-2.1" && make && make test \
          && cp pbmtools/pbmtojbg pbmtools/jbgtopbm "$W/bin/"; }
flif()  { cd "$W/src/FLIF-0.4/src" && make -j8 flif && cp flif "$W/bin/"; }
# ECC: patches/ecc_ub_fixes.patch adds two missing `return` statements (functions
# whose value is never used; without them GCC 13 -O2 builds crash on every
# non-constant map) and pads the decoder's input buffer with 16 zero bytes (its
# arithmetic decoder reads ahead past the stream end). Nothing else is changed.
ecc()   { cd "$W"/src/LosslessSegmentationMapCompression-* \
          && patch -p1 < /scripts/patches/ecc_ub_fixes.patch && make -j8 \
          && cp encoder "$W/bin/ecc_encoder" && cp decoder "$W/bin/ecc_decoder"; }
hm()    { cd "$W/src/HM-HM-16.21+SCM-8.8" && mkdir -p build && cd build \
          && cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS="$HM_EXTRA_CXXFLAGS" \
          && make -j8 TAppEncoder TAppDecoder \
          && local e d && e=$(find .. -type f -name TAppEncoder -perm -u+x | head -1) \
          && d=$(find .. -type f -name TAppDecoder -perm -u+x | head -1) \
          && [ -n "$e" ] && [ -n "$d" ] && cp "$e" "$d" "$W/bin/" \
          && mkdir -p "$W/bin/hm_cfg" && cp -r ../cfg/. "$W/bin/hm_cfg/"; }
cpso()  { g++ -std=c++11 -O3 -I "$(echo "$W"/src/compresso-*)" /scripts/cpso_cli.cpp -o "$W/bin/cpso_cli"; }

build jbigkit  jbig
build flif     flif
build ecc      ecc
build hm       hm
build compresso cpso

( cd "$W/bin" && find . -maxdepth 1 -type f -exec sha256sum {} + | sort -k2 ) > /out/binaries.sha256
ls -l "$W/bin" > /out/binaries.txt
{ gcc --version | head -1; g++ --version | head -1; cmake --version | head -1; } > /out/toolchain.txt
exit $status
