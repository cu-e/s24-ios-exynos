/* NAT-077: SHA-256 (FIPS 180-4), written for this project from the standard; no third-party code.
 *
 * Freestanding on purpose: no libc, no memcpy/memset (a compiler-generated call to either would be an undefined symbol and the link
 * fails, which build.py treats as an error), no global writable data. The same file is compiled into the PID 1 probe for arm64
 * (clang -target arm64-apple-ios16.0) and into the host test programs (cc), so the host tests exercise the same source text.
 */
#ifndef NAT077_SHA256_H
#define NAT077_SHA256_H

typedef unsigned char sha_u8;
typedef unsigned int sha_u32;
typedef unsigned long long sha_u64;

struct sha256 {
	sha_u32 h[8];
	sha_u64 total;		/* bytes absorbed so far */
	sha_u8 buf[64];
	sha_u32 fill;		/* bytes in buf, always < 64 between calls */
};

static const sha_u32 sha256_k[64] = {
	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
	0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
	0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
	0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
	0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

static inline sha_u32 sha256_rotr(sha_u32 x, unsigned n)
{
	return (x >> n) | (x << (32 - n));
}

static void sha256_init(struct sha256 *s)
{
	s->h[0] = 0x6a09e667; s->h[1] = 0xbb67ae85; s->h[2] = 0x3c6ef372; s->h[3] = 0xa54ff53a;
	s->h[4] = 0x510e527f; s->h[5] = 0x9b05688c; s->h[6] = 0x1f83d9ab; s->h[7] = 0x5be0cd19;
	s->total = 0;
	s->fill = 0;
}

static void sha256_block(struct sha256 *s, const sha_u8 *p)
{
	sha_u32 w[64], a, b, c, d, e, f, g, h, t1, t2;
	unsigned i;

	for (i = 0; i < 16; i++)
		w[i] = ((sha_u32)p[4 * i] << 24) | ((sha_u32)p[4 * i + 1] << 16) | ((sha_u32)p[4 * i + 2] << 8) | p[4 * i + 3];
	for (i = 16; i < 64; i++) {
		sha_u32 s0 = sha256_rotr(w[i - 15], 7) ^ sha256_rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
		sha_u32 s1 = sha256_rotr(w[i - 2], 17) ^ sha256_rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);

		w[i] = w[i - 16] + s0 + w[i - 7] + s1;
	}
	a = s->h[0]; b = s->h[1]; c = s->h[2]; d = s->h[3];
	e = s->h[4]; f = s->h[5]; g = s->h[6]; h = s->h[7];
	for (i = 0; i < 64; i++) {
		t1 = h + (sha256_rotr(e, 6) ^ sha256_rotr(e, 11) ^ sha256_rotr(e, 25)) + ((e & f) ^ (~e & g)) + sha256_k[i] + w[i];
		t2 = (sha256_rotr(a, 2) ^ sha256_rotr(a, 13) ^ sha256_rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
		h = g; g = f; f = e; e = d + t1;
		d = c; c = b; b = a; a = t1 + t2;
	}
	s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d;
	s->h[4] += e; s->h[5] += f; s->h[6] += g; s->h[7] += h;
}

static void sha256_update(struct sha256 *s, const sha_u8 *p, sha_u64 n)
{
	s->total += n;
	if (s->fill) {
		while (n && s->fill < 64) {
			s->buf[s->fill++] = *p++;
			n--;
		}
		if (s->fill < 64)
			return;
		sha256_block(s, s->buf);
		s->fill = 0;
	}
	while (n >= 64) {
		sha256_block(s, p);
		p += 64;
		n -= 64;
	}
	while (n) {
		s->buf[s->fill++] = *p++;
		n--;
	}
}

/* pads, absorbs the length and writes the 32-byte digest */
static void sha256_final(struct sha256 *s, sha_u8 out[32])
{
	sha_u64 bits = s->total * 8;
	unsigned i;

	s->buf[s->fill++] = 0x80;
	if (s->fill > 56) {
		while (s->fill < 64)
			s->buf[s->fill++] = 0;
		sha256_block(s, s->buf);
		s->fill = 0;
	}
	while (s->fill < 56)
		s->buf[s->fill++] = 0;
	for (i = 0; i < 8; i++)
		s->buf[56 + i] = (sha_u8)(bits >> (56 - 8 * i));
	sha256_block(s, s->buf);
	for (i = 0; i < 8; i++) {
		out[4 * i] = (sha_u8)(s->h[i] >> 24);
		out[4 * i + 1] = (sha_u8)(s->h[i] >> 16);
		out[4 * i + 2] = (sha_u8)(s->h[i] >> 8);
		out[4 * i + 3] = (sha_u8)s->h[i];
	}
}

#endif
