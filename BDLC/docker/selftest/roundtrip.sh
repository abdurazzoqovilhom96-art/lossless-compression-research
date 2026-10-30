#!/bin/bash
# Encodes and decodes every synthetic map with every baseline (inside
# bdlc-baselines:2026-10-29, WORK mounted at /work). Writes /work/roundtrip.csv.
set -u
B=/opt/baselines/bin
cd /work || exit 1
mkdir -p enc dec logs
echo "tool,variant,name,kind,exit,bytes,decoded" > roundtrip.csv

run() {  # tool variant name kind encoded decoded -- commands (encode ; decode)
    local tool=$1 variant=$2 name=$3 kind=$4 enc=$5 dec=$6; shift 6
    local log="logs/${tool}_${variant}_${name}.log"
    if bash -c "$*" > "$log" 2>&1; then
        echo "$tool,$variant,$name,$kind,0,$(stat -c %s "$enc"),$dec" >> roundtrip.csv
    else
        echo "$tool,$variant,$name,$kind,$?,,"  >> roundtrip.csv
    fi
}

tail -n +2 index.csv | tr -d '\r' | while IFS=, read -r name H W K rank8; do
    i=in/$name
    # Compresso: uint16 directly
    run cpso default "$name" u16raw "enc/$name.cpso" "dec/$name.cpso.u16" \
        "$B/cpso_cli c $i.u16 $H $W enc/$name.cpso && $B/cpso_cli d enc/$name.cpso dec/$name.cpso.u16"
    # FLIF: uint16 PGM, default effort and -E100
    for e in 60 100; do
        run flif "u16_E$e" "$name" u16pnm "enc/$name.u16.E$e.flif" "dec/$name.u16.E$e.pgm" \
            "$B/flif -e -E$e $i.u16.pgm enc/$name.u16.E$e.flif && $B/flif -d enc/$name.u16.E$e.flif dec/$name.u16.E$e.pgm"
    done
    [ "$rank8" = 1 ] || continue
    for e in 60 100; do
        run flif "r8_E$e" "$name" r8pnm "enc/$name.r8.E$e.flif" "dec/$name.r8.E$e.pgm" \
            "$B/flif -e -E$e $i.r8.pgm enc/$name.r8.E$e.flif && $B/flif -d enc/$name.r8.E$e.flif dec/$name.r8.E$e.pgm"
    done
    # JBIG1: bit planes of the rank map, Gray code (default) and plain binary (-b), sequential (-q)
    run jbig gray "$name" jbigpnm "enc/$name.gray.jbg" "dec/$name.gray.pgm" \
        "$B/pbmtojbg -q $i.jbig.pgm enc/$name.gray.jbg && $B/jbgtopbm enc/$name.gray.jbg dec/$name.gray.pgm"
    run jbig binary "$name" jbigpnm "enc/$name.bin.jbg" "dec/$name.bin.pgm" \
        "$B/pbmtojbg -q -b $i.jbig.pgm enc/$name.bin.jbg && $B/jbgtopbm -b enc/$name.bin.jbg dec/$name.bin.pgm"
    # (the plane code is not stored in the BIE, so the decoder needs -b as well)
    # ECC-2026: 8-bit YUV 4:0:0 rank map, one frame
    run ecc default "$name" r8yuv "enc/$name.ecc.bin" "dec/$name.ecc.yuv" \
        "$B/ecc_encoder -i $i.r8.yuv -o enc/$name.ecc.bin -r $H -c $W -f 1 -s 0 -t 400 && $B/ecc_decoder -i enc/$name.ecc.bin -o dec/$name.ecc.yuv"
    # HEVC SCC (HM-16.21+SCM-8.8): lossless intra, palette on, 4:0:0, padded by the conformance window
    run hm scc_lossless "$name" r8yuv "enc/$name.hevc" "dec/$name.hevc.yuv" \
        "$B/TAppEncoder -c $B/hm_cfg/encoder_intra_main_scc.cfg -i $i.r8.yuv -b enc/$name.hevc -o /dev/null \
           -wdt $W -hgt $H -fr 1 -f 1 --InputBitDepth=8 --InternalBitDepth=8 \
           --InputChromaFormat=400 --ChromaFormatIDC=400 --ConformanceWindowMode=1 \
           --TransquantBypassEnable=1 --CUTransquantBypassFlagForce=1 --CostMode=lossless \
         && $B/TAppDecoder -b enc/$name.hevc -o dec/$name.hevc.yuv -d 8"
done
echo done
