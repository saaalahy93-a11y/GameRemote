// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL

#include <munit.h>
#include <gameremote/ecdh.h>
#include <gameremote/session.h>
#include <string.h>

#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
#include <mbedtls/md.h>
#else
#include <openssl/hmac.h>
#endif

// SEC 2 secp256k1 generator and its double. With d=1 and peer 2G, ECDH is X(2G).
static const uint8_t generator[] = {
	0x04, 0x79, 0xbe, 0x66, 0x7e, 0xf9, 0xdc, 0xbb, 0xac, 0x55, 0xa0, 0x62, 0x95, 0xce, 0x87, 0x0b, 0x07,
	0x02, 0x9b, 0xfc, 0xdb, 0x2d, 0xce, 0x28, 0xd9, 0x59, 0xf2, 0x81, 0x5b, 0x16, 0xf8, 0x17, 0x98,
	0x48, 0x3a, 0xda, 0x77, 0x26, 0xa3, 0xc4, 0x65, 0x5d, 0xa4, 0xfb, 0xfc, 0x0e, 0x11, 0x08, 0xa8,
	0xfd, 0x17, 0xb4, 0x48, 0xa6, 0x85, 0x54, 0x19, 0x9c, 0x47, 0xd0, 0x8f, 0xfb, 0x10, 0xd4, 0xb8
};
static const uint8_t twice_generator[] = {
	0x04, 0xc6, 0x04, 0x7f, 0x94, 0x41, 0xed, 0x7d, 0x6d, 0x30, 0x45, 0x40, 0x6e, 0x95, 0xc0, 0x7c, 0xd8,
	0x5c, 0x77, 0x8e, 0x4b, 0x8c, 0xef, 0x3c, 0xa7, 0xab, 0xac, 0x09, 0xb9, 0x5c, 0x70, 0x9e, 0xe5,
	0x1a, 0xe1, 0x68, 0xfe, 0xa6, 0x3d, 0xc3, 0x39, 0xa3, 0xc5, 0x84, 0x19, 0x46, 0x6c, 0xea, 0xee,
	0xf7, 0xf6, 0x32, 0x65, 0x32, 0x66, 0xd0, 0xe1, 0x23, 0x64, 0x31, 0xa9, 0x50, 0xcf, 0xe5, 0x2a
};
static const uint8_t handshake_key[CHIAKI_HANDSHAKE_KEY_SIZE] = { 1, 2, 3, 4 };

static void assert_filled(const uint8_t *buf, size_t size, uint8_t value)
{
	for(size_t i = 0; i < size; ++i)
		munit_assert_uint8(buf[i], ==, value);
}

static void sign_key(const uint8_t *key, size_t size, uint8_t *sig)
{
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	munit_assert_int(mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), handshake_key,
			sizeof(handshake_key), key, size, sig), ==, 0);
#else
	unsigned int sig_size;
	munit_assert_not_null(HMAC(EVP_sha256(), handshake_key, sizeof(handshake_key), key, size, sig, &sig_size));
	munit_assert_uint(sig_size, ==, CHIAKI_ECDH_SIGNATURE_SIZE);
#endif
}

static void init_key(ChiakiECDH *ecdh, uint8_t scalar, const uint8_t *point)
{
	munit_assert_int(chiaki_ecdh_init(ecdh), ==, CHIAKI_ERR_SUCCESS);
	munit_assert_int(chiaki_ecdh_set_local_key(ecdh, &scalar, 1, point, sizeof(generator)), ==, CHIAKI_ERR_SUCCESS);
}

static void assert_local_key(ChiakiECDH *ecdh, const uint8_t *expected)
{
	uint8_t key[CHIAKI_ECDH_PUBLIC_KEY_SIZE], sig[CHIAKI_ECDH_SIGNATURE_SIZE];
	size_t key_size = sizeof(key), sig_size = SIZE_MAX;
	munit_assert_int(chiaki_ecdh_get_local_pub_key(ecdh, key, &key_size, handshake_key, sig, &sig_size), ==, CHIAKI_ERR_SUCCESS);
	munit_assert_size(key_size, ==, sizeof(key));
	munit_assert_size(sig_size, ==, sizeof(sig));
	munit_assert_memory_equal(sizeof(key), key, expected);
}

static MunitResult test_small_scalar_vector(const MunitParameter params[], void *user)
{
	ChiakiECDH alice, bob;
	init_key(&alice, 1, generator);
	init_key(&bob, 2, twice_generator);
	assert_local_key(&alice, generator);
	assert_local_key(&bob, twice_generator);
	uint8_t sig[CHIAKI_ECDH_SIGNATURE_SIZE], secret[CHIAKI_ECDH_SECRET_SIZE + 1];
	sign_key(twice_generator, sizeof(twice_generator), sig);
	memset(secret, 0xa5, sizeof(secret));
	munit_assert_int(chiaki_ecdh_derive_secret(&alice, secret, twice_generator, sizeof(twice_generator),
			handshake_key, sig, sizeof(sig)), ==, CHIAKI_ERR_SUCCESS);
	munit_assert_memory_equal(CHIAKI_ECDH_SECRET_SIZE, secret, twice_generator + 1);
	munit_assert_uint8(secret[CHIAKI_ECDH_SECRET_SIZE], ==, 0xa5);
	sign_key(generator, sizeof(generator), sig);
	munit_assert_int(chiaki_ecdh_derive_secret(&bob, secret, generator, sizeof(generator),
			handshake_key, sig, sizeof(sig)), ==, CHIAKI_ERR_SUCCESS);
	munit_assert_memory_equal(CHIAKI_ECDH_SECRET_SIZE, secret, twice_generator + 1);
	chiaki_ecdh_fini(&alice);
	chiaki_ecdh_fini(&bob);
	return MUNIT_OK;
}

static MunitResult test_invalid_local_keys(const MunitParameter params[], void *user)
{
	static const uint8_t order[] = {
		0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xfe,
		0xba, 0xae, 0xdc, 0xe6, 0xaf, 0x48, 0xa0, 0x3b, 0xbf, 0xd2, 0x5e, 0x8c, 0xd0, 0x36, 0x41, 0x41
	};
	const uint8_t zero = 0, one = 1, two = 2;
	uint8_t invalid_point[CHIAKI_ECDH_PUBLIC_KEY_SIZE] = { 4 };
	ChiakiECDH ecdh;
	init_key(&ecdh, one, generator);
	munit_assert_int(chiaki_ecdh_set_local_key(&ecdh, &zero, 1, generator, sizeof(generator)), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_ecdh_set_local_key(&ecdh, order, sizeof(order), generator, sizeof(generator)), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_ecdh_set_local_key(&ecdh, &two, 1, generator, sizeof(generator)), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_ecdh_set_local_key(&ecdh, &one, 1, invalid_point, sizeof(invalid_point)), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_ecdh_set_local_key(&ecdh, &one, 1, generator, sizeof(generator) - 1), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_ecdh_set_local_key(&ecdh, &one, 0, generator, sizeof(generator)), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_ecdh_set_local_key(&ecdh, &one, SIZE_MAX, generator, sizeof(generator)), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_ecdh_set_local_key(&ecdh, NULL, 1, generator, sizeof(generator)), ==, CHIAKI_ERR_INVALID_DATA);
	assert_local_key(&ecdh, generator);
	chiaki_ecdh_fini(&ecdh);
	return MUNIT_OK;
}

static MunitResult test_generated_round_trip(const MunitParameter params[], void *user)
{
	ChiakiECDH peers[2];
	uint8_t keys[2][CHIAKI_ECDH_PUBLIC_KEY_SIZE], signatures[2][CHIAKI_ECDH_SIGNATURE_SIZE];
	uint8_t secrets[2][CHIAKI_ECDH_SECRET_SIZE];
	for(size_t i = 0; i < 2; ++i)
	{
		munit_assert_int(chiaki_ecdh_init(&peers[i]), ==, CHIAKI_ERR_SUCCESS);
		size_t key_size = sizeof(keys[i]), sig_size = sizeof(signatures[i]);
		munit_assert_int(chiaki_ecdh_get_local_pub_key(&peers[i], keys[i], &key_size, handshake_key,
				signatures[i], &sig_size), ==, CHIAKI_ERR_SUCCESS);
		munit_assert_size(key_size, ==, sizeof(keys[i]));
		munit_assert_size(sig_size, ==, sizeof(signatures[i]));
	}
	for(size_t i = 0; i < 2; ++i)
	{
		munit_assert_int(chiaki_ecdh_derive_secret(&peers[i], secrets[i], keys[1 - i], sizeof(keys[1 - i]),
				handshake_key, signatures[1 - i], sizeof(signatures[1 - i])), ==, CHIAKI_ERR_SUCCESS);
		chiaki_ecdh_fini(&peers[i]);
	}
	munit_assert_memory_equal(sizeof(secrets[0]), secrets[0], secrets[1]);
	return MUNIT_OK;
}

static MunitResult test_invalid_peer(const MunitParameter params[], void *user)
{
	ChiakiECDH ecdh;
	init_key(&ecdh, 1, generator);
	uint8_t sig[CHIAKI_ECDH_SIGNATURE_SIZE + 1], secret[CHIAKI_ECDH_SECRET_SIZE];
	memset(secret, 0xa5, sizeof(secret));
	sign_key(twice_generator, sizeof(twice_generator), sig);
	for(size_t i = 0; i < CHIAKI_ECDH_SIGNATURE_SIZE; i += CHIAKI_ECDH_SIGNATURE_SIZE - 1)
	{
		sig[i] ^= 1;
		munit_assert_int(chiaki_ecdh_derive_secret(&ecdh, secret, twice_generator, sizeof(twice_generator),
				handshake_key, sig, CHIAKI_ECDH_SIGNATURE_SIZE), ==, CHIAKI_ERR_INVALID_MAC);
		sig[i] ^= 1;
	}
	munit_assert_int(chiaki_ecdh_derive_secret(&ecdh, secret, twice_generator, sizeof(twice_generator),
			handshake_key, sig, CHIAKI_ECDH_SIGNATURE_SIZE - 1), ==, CHIAKI_ERR_INVALID_MAC);
	munit_assert_int(chiaki_ecdh_derive_secret(&ecdh, secret, twice_generator, sizeof(twice_generator),
			handshake_key, sig, sizeof(sig)), ==, CHIAKI_ERR_INVALID_MAC);
	uint8_t wrong_handshake_key[CHIAKI_HANDSHAKE_KEY_SIZE] = { 0 };
	munit_assert_int(chiaki_ecdh_derive_secret(&ecdh, secret, twice_generator, sizeof(twice_generator),
			wrong_handshake_key, sig, CHIAKI_ECDH_SIGNATURE_SIZE), ==, CHIAKI_ERR_INVALID_MAC);

	// Sign malformed points correctly so these tests reach curve validation.
	uint8_t invalid_point[CHIAKI_ECDH_PUBLIC_KEY_SIZE] = { 4 };
	sign_key(invalid_point, sizeof(invalid_point), sig);
	munit_assert_int(chiaki_ecdh_derive_secret(&ecdh, secret, invalid_point, sizeof(invalid_point),
			handshake_key, sig, CHIAKI_ECDH_SIGNATURE_SIZE), ==, CHIAKI_ERR_INVALID_DATA);
	memset(invalid_point + 1, 0xff, sizeof(invalid_point) - 1);
	sign_key(invalid_point, sizeof(invalid_point), sig);
	munit_assert_int(chiaki_ecdh_derive_secret(&ecdh, secret, invalid_point, sizeof(invalid_point),
			handshake_key, sig, CHIAKI_ECDH_SIGNATURE_SIZE), ==, CHIAKI_ERR_INVALID_DATA);
	munit_assert_int(chiaki_ecdh_derive_secret(&ecdh, secret, twice_generator, sizeof(twice_generator) - 1,
			handshake_key, sig, CHIAKI_ECDH_SIGNATURE_SIZE), ==, CHIAKI_ERR_INVALID_DATA);
	const uint8_t infinity = 0;
	munit_assert_int(chiaki_ecdh_derive_secret(&ecdh, secret, &infinity, sizeof(infinity),
			handshake_key, sig, CHIAKI_ECDH_SIGNATURE_SIZE), ==, CHIAKI_ERR_INVALID_DATA);
	assert_filled(secret, sizeof(secret), 0xa5);
	assert_local_key(&ecdh, generator);
	chiaki_ecdh_fini(&ecdh);
	return MUNIT_OK;
}

static MunitResult test_output_bounds(const MunitParameter params[], void *user)
{
	ChiakiECDH ecdh;
	init_key(&ecdh, 1, generator);
	uint8_t key[CHIAKI_ECDH_PUBLIC_KEY_SIZE], sig[CHIAKI_ECDH_SIGNATURE_SIZE];
	memset(key, 0xa5, sizeof(key));
	memset(sig, 0x5a, sizeof(sig));
	for(size_t i = 0; i < 2; ++i)
	{
		size_t key_size = sizeof(key) - (i == 0), sig_size = sizeof(sig) - (i == 1);
		munit_assert_int(chiaki_ecdh_get_local_pub_key(&ecdh, key, &key_size, handshake_key, sig, &sig_size), ==, CHIAKI_ERR_BUF_TOO_SMALL);
		munit_assert_size(key_size, ==, sizeof(key) - (i == 0));
		munit_assert_size(sig_size, ==, sizeof(sig) - (i == 1));
		assert_filled(key, sizeof(key), 0xa5);
		assert_filled(sig, sizeof(sig), 0x5a);
	}
	chiaki_ecdh_fini(&ecdh);
	return MUNIT_OK;
}

#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
static MunitResult test_rng_reseed(const MunitParameter params[], void *user)
{
	ChiakiECDH ecdh;
	munit_assert_int(chiaki_ecdh_init(&ecdh), ==, CHIAKI_ERR_SUCCESS);
	// Force the retained entropy callback after chiaki_ecdh_init's stack is gone.
	munit_assert_int(mbedtls_ctr_drbg_reseed(&ecdh.drbg, NULL, 0), ==, 0);
	uint8_t random[32];
	munit_assert_int(mbedtls_ctr_drbg_random(&ecdh.drbg, random, sizeof(random)), ==, 0);
	chiaki_ecdh_fini(&ecdh);
	return MUNIT_OK;
}
#endif

MunitTest tests_ecdh[] = {
	{ "/small_scalar_vector", test_small_scalar_vector, NULL, NULL, MUNIT_TEST_OPTION_NONE, NULL },
	{ "/generated_round_trip", test_generated_round_trip, NULL, NULL, MUNIT_TEST_OPTION_NONE, NULL },
	{ "/invalid_local_keys", test_invalid_local_keys, NULL, NULL, MUNIT_TEST_OPTION_NONE, NULL },
	{ "/invalid_peer", test_invalid_peer, NULL, NULL, MUNIT_TEST_OPTION_NONE, NULL },
	{ "/output_bounds", test_output_bounds, NULL, NULL, MUNIT_TEST_OPTION_NONE, NULL },
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	{ "/rng_reseed", test_rng_reseed, NULL, NULL, MUNIT_TEST_OPTION_NONE, NULL },
#endif
	{ NULL, NULL, NULL, NULL, MUNIT_TEST_OPTION_NONE, NULL }
};
