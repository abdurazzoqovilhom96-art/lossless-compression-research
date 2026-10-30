// Command-line wrapper around compresso.hpp (seung-lab/compresso, commit b1f7fd6).
//
// It reproduces the defaults of the Python package's compresso.compress():
// the 2D array (H, W) is passed in Fortran order with sx = H, sy = W, sz = 1;
// steps 4x4x1, connectivity 4, random_access_z_index = true; if encoding fails
// with "Unable to RLE encode", it retries with steps 8x8x1.
//
// Raw files are little-endian uint16 in C (row-major) order, H*W*2 bytes.
//
//   cpso_cli c IN.u16 H W OUT.cpso
//   cpso_cli d IN.cpso OUT.u16
#include "compresso.hpp"

#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

static std::vector<unsigned char> slurp(const char *path) {
    FILE *f = std::fopen(path, "rb");
    if (!f) throw std::runtime_error(std::string("cannot open ") + path);
    std::vector<unsigned char> buf;
    unsigned char tmp[1 << 16];
    size_t n;
    while ((n = std::fread(tmp, 1, sizeof(tmp), f)) > 0) buf.insert(buf.end(), tmp, tmp + n);
    std::fclose(f);
    return buf;
}

static void spit(const char *path, const void *data, size_t n) {
    FILE *f = std::fopen(path, "wb");
    if (!f) throw std::runtime_error(std::string("cannot create ") + path);
    if (n && std::fwrite(data, 1, n, f) != n) throw std::runtime_error("short write");
    if (std::fclose(f)) throw std::runtime_error("close failed");
}

int main(int argc, char **argv) {
    try {
        if (argc == 6 && std::strcmp(argv[1], "c") == 0) {
            const size_t H = std::stoull(argv[3]), W = std::stoull(argv[4]);
            std::vector<unsigned char> raw = slurp(argv[2]);
            if (raw.size() != H * W * 2) throw std::runtime_error("input size != H*W*2");
            std::vector<uint16_t> a(H * W), f(H * W);
            std::memcpy(a.data(), raw.data(), raw.size());  // x86: little-endian host
            for (size_t r = 0; r < H; r++)
                for (size_t c = 0; c < W; c++) f[r + H * c] = a[r * W + c];
            std::vector<unsigned char> out;
            try {
                out = compresso::compress<uint16_t>(f.data(), H, W, 1, 4, 4, 1, 4, true);
            } catch (const std::runtime_error &e) {
                if (std::string(e.what()).find("Unable to RLE encode") == std::string::npos) throw;
                out = compresso::compress<uint16_t>(f.data(), H, W, 1, 8, 8, 1, 4, true);
            }
            spit(argv[5], out.data(), out.size());
            return 0;
        }
        if (argc == 4 && std::strcmp(argv[1], "d") == 0) {
            std::vector<unsigned char> buf = slurp(argv[2]);
            if (buf.size() < compresso::CompressoHeader::header_size) throw std::runtime_error("stream too small");
            const compresso::CompressoHeader h(buf.data());
            if (h.data_width != 2 || h.sz != 1) throw std::runtime_error("expected a 2D uint16 stream");
            const size_t H = h.sx, W = h.sy;
            uint16_t *f = static_cast<uint16_t *>(
                compresso::decompress<void, void>(buf.data(), buf.size(), NULL, 0, -1));
            std::vector<uint16_t> a(H * W);
            for (size_t r = 0; r < H; r++)
                for (size_t c = 0; c < W; c++) a[r * W + c] = f[r + H * c];
            delete[] f;
            spit(argv[3], a.data(), a.size() * 2);
            return 0;
        }
        std::fprintf(stderr, "usage: cpso_cli c IN.u16 H W OUT.cpso | cpso_cli d IN.cpso OUT.u16\n");
        return 2;
    } catch (const std::exception &e) {
        std::fprintf(stderr, "cpso_cli: %s\n", e.what());
        return 1;
    }
}
