// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL

#include <gameremote/session.h>
#include <gameremote/ecdh.h>

#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
#include <mbedtls/constant_time.h>
#include <mbedtls/md.h>
#else
#include <openssl/evp.h>
#include <openssl/ec.h>
#include <openssl/hmac.h>
#include <openssl/bn.h>
#include <openssl/ecdh.h>
#include <openssl/crypto.h>
#endif

#include <string.h>

static ChiakiErrorCode ecdh_public_key_sig(const uint8_t *public_key, size_t public_key_size,
		const uint8_t *handshake_key, uint8_t *sig_out)
{
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	if(mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), handshake_key,
			CHIAKI_HANDSHAKE_KEY_SIZE, public_key, public_key_size, sig_out) != 0)
		return CHIAKI_ERR_UNKNOWN;
#else
	unsigned int sig_size = 0;
	if(!HMAC(EVP_sha256(), handshake_key, CHIAKI_HANDSHAKE_KEY_SIZE,
			public_key, public_key_size, sig_out, &sig_size)
			|| sig_size != CHIAKI_ECDH_SIGNATURE_SIZE)
		return CHIAKI_ERR_UNKNOWN;
#endif
	return CHIAKI_ERR_SUCCESS;
}

CHIAKI_EXPORT ChiakiErrorCode chiaki_ecdh_init(ChiakiECDH *ecdh)
{
	if(!ecdh)
		return CHIAKI_ERR_INVALID_DATA;
	memset(ecdh, 0, sizeof(*ecdh));
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	const unsigned char pers[] = "ecdh";
	mbedtls_ecp_group_init(&ecdh->group);
	mbedtls_mpi_init(&ecdh->private_key);
	mbedtls_ecp_point_init(&ecdh->public_key);
	mbedtls_ctr_drbg_init(&ecdh->drbg);
	mbedtls_entropy_init(&ecdh->entropy);

	if(mbedtls_ctr_drbg_seed(&ecdh->drbg, mbedtls_entropy_func, &ecdh->entropy, pers, sizeof(pers)) != 0
			|| mbedtls_ecp_group_load(&ecdh->group, MBEDTLS_ECP_DP_SECP256K1) != 0
			|| mbedtls_ecdh_gen_public(&ecdh->group, &ecdh->private_key, &ecdh->public_key,
				mbedtls_ctr_drbg_random, &ecdh->drbg) != 0)
	{
		chiaki_ecdh_fini(ecdh);
		return CHIAKI_ERR_UNKNOWN;
	}
#else
	ecdh->group = EC_GROUP_new_by_curve_name(NID_secp256k1);
	ecdh->key_local = EC_KEY_new();
	if(!ecdh->group || !ecdh->key_local
			|| !EC_KEY_set_group(ecdh->key_local, ecdh->group)
			|| !EC_KEY_generate_key(ecdh->key_local))
	{
		chiaki_ecdh_fini(ecdh);
		return CHIAKI_ERR_UNKNOWN;
	}
#endif
	return CHIAKI_ERR_SUCCESS;
}

CHIAKI_EXPORT void chiaki_ecdh_fini(ChiakiECDH *ecdh)
{
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	mbedtls_ecp_point_free(&ecdh->public_key);
	mbedtls_mpi_free(&ecdh->private_key);
	mbedtls_ecp_group_free(&ecdh->group);
	mbedtls_ctr_drbg_free(&ecdh->drbg);
	mbedtls_entropy_free(&ecdh->entropy);
#else
	EC_KEY_free(ecdh->key_local);
	EC_GROUP_free(ecdh->group);
#endif
}

CHIAKI_EXPORT ChiakiErrorCode chiaki_ecdh_set_local_key(ChiakiECDH *ecdh, const uint8_t *private_key, size_t private_key_size, const uint8_t *public_key, size_t public_key_size)
{
	if(!ecdh || !private_key || private_key_size == 0 || private_key_size > CHIAKI_ECDH_SECRET_SIZE
			|| !public_key || public_key_size != CHIAKI_ECDH_PUBLIC_KEY_SIZE || public_key[0] != 4)
		return CHIAKI_ERR_INVALID_DATA;

	ChiakiErrorCode err = CHIAKI_ERR_INVALID_DATA;
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	mbedtls_mpi private_key_tmp;
	mbedtls_ecp_point public_key_tmp, public_key_derived;
	mbedtls_mpi_init(&private_key_tmp);
	mbedtls_ecp_point_init(&public_key_tmp);
	mbedtls_ecp_point_init(&public_key_derived);

	if(mbedtls_mpi_read_binary(&private_key_tmp, private_key, private_key_size) != 0
			|| mbedtls_ecp_check_privkey(&ecdh->group, &private_key_tmp) != 0
			|| mbedtls_ecp_point_read_binary(&ecdh->group, &public_key_tmp, public_key, public_key_size) != 0
			|| mbedtls_ecp_check_pubkey(&ecdh->group, &public_key_tmp) != 0)
		goto end;

	// G is a documented public, read-only domain parameter in Mbed TLS 3.x.
	if(mbedtls_ecp_mul(&ecdh->group, &public_key_derived, &private_key_tmp, &ecdh->group.G,
			mbedtls_ctr_drbg_random, &ecdh->drbg) != 0)
	{
		err = CHIAKI_ERR_UNKNOWN;
		goto end;
	}
	if(mbedtls_ecp_point_cmp(&public_key_tmp, &public_key_derived) != 0)
		goto end;

	// Transfer the validated pair together; the temporary owns the old point.
	mbedtls_ecp_point public_key_old = ecdh->public_key;
	ecdh->public_key = public_key_tmp;
	public_key_tmp = public_key_old;
	mbedtls_mpi_swap(&ecdh->private_key, &private_key_tmp);
	err = CHIAKI_ERR_SUCCESS;
end:
	mbedtls_ecp_point_free(&public_key_derived);
	mbedtls_ecp_point_free(&public_key_tmp);
	mbedtls_mpi_free(&private_key_tmp);
#else
	BIGNUM *private_key_bn = BN_bin2bn(private_key, (int)private_key_size, NULL);
	EC_POINT *public_key_point = EC_POINT_new(ecdh->group);
	EC_KEY *key_tmp = EC_KEY_new();
	if(!private_key_bn || !public_key_point || !key_tmp)
	{
		err = CHIAKI_ERR_MEMORY;
		goto end;
	}
	if(!EC_POINT_oct2point(ecdh->group, public_key_point, public_key, public_key_size, NULL)
			|| !EC_KEY_set_group(key_tmp, ecdh->group)
			|| !EC_KEY_set_private_key(key_tmp, private_key_bn)
			|| !EC_KEY_set_public_key(key_tmp, public_key_point)
			|| !EC_KEY_check_key(key_tmp))
		goto end;

	EC_KEY_free(ecdh->key_local);
	ecdh->key_local = key_tmp;
	key_tmp = NULL;
	err = CHIAKI_ERR_SUCCESS;
end:
	EC_KEY_free(key_tmp);
	EC_POINT_free(public_key_point);
	BN_clear_free(private_key_bn);
#endif
	return err;
}

CHIAKI_EXPORT ChiakiErrorCode chiaki_ecdh_get_local_pub_key(ChiakiECDH *ecdh, uint8_t *key_out, size_t *key_out_size, const uint8_t *handshake_key, uint8_t *sig_out, size_t *sig_out_size)
{
	if(!ecdh || !key_out || !key_out_size || !handshake_key || !sig_out || !sig_out_size)
		return CHIAKI_ERR_INVALID_DATA;
	if(*key_out_size < CHIAKI_ECDH_PUBLIC_KEY_SIZE || *sig_out_size < CHIAKI_ECDH_SIGNATURE_SIZE)
		return CHIAKI_ERR_BUF_TOO_SMALL;

	uint8_t public_key[CHIAKI_ECDH_PUBLIC_KEY_SIZE];
	uint8_t sig[CHIAKI_ECDH_SIGNATURE_SIZE];
	size_t public_key_size;
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	if(mbedtls_ecp_point_write_binary(&ecdh->group, &ecdh->public_key, MBEDTLS_ECP_PF_UNCOMPRESSED,
			&public_key_size, public_key, sizeof(public_key)) != 0)
		return CHIAKI_ERR_UNKNOWN;
#else
	const EC_POINT *point = EC_KEY_get0_public_key(ecdh->key_local);
	if(!point)
		return CHIAKI_ERR_UNKNOWN;
	public_key_size = EC_POINT_point2oct(ecdh->group, point, POINT_CONVERSION_UNCOMPRESSED,
			public_key, sizeof(public_key), NULL);
#endif
	if(public_key_size != sizeof(public_key))
		return CHIAKI_ERR_UNKNOWN;
	ChiakiErrorCode err = ecdh_public_key_sig(public_key, public_key_size, handshake_key, sig);
	if(err != CHIAKI_ERR_SUCCESS)
		return err;
	memcpy(key_out, public_key, sizeof(public_key));
	memcpy(sig_out, sig, sizeof(sig));
	*key_out_size = sizeof(public_key);
	*sig_out_size = sizeof(sig);
	return CHIAKI_ERR_SUCCESS;
}

CHIAKI_EXPORT ChiakiErrorCode chiaki_ecdh_derive_secret(ChiakiECDH *ecdh, uint8_t *secret_out, const uint8_t *remote_key, size_t remote_key_size, const uint8_t *handshake_key, const uint8_t *remote_sig, size_t remote_sig_size)
{
	if(!ecdh || !secret_out || !remote_key || remote_key_size != CHIAKI_ECDH_PUBLIC_KEY_SIZE
			|| remote_key[0] != 4 || !handshake_key || !remote_sig)
		return CHIAKI_ERR_INVALID_DATA;
	if(remote_sig_size != CHIAKI_ECDH_SIGNATURE_SIZE)
		return CHIAKI_ERR_INVALID_MAC;

	// BANG signs the raw uncompressed public key with the session handshake key.
	uint8_t expected_sig[CHIAKI_ECDH_SIGNATURE_SIZE];
	ChiakiErrorCode err = ecdh_public_key_sig(remote_key, remote_key_size, handshake_key, expected_sig);
	if(err != CHIAKI_ERR_SUCCESS)
		return err;
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	if(mbedtls_ct_memcmp(remote_sig, expected_sig, sizeof(expected_sig)) != 0)
#else
	if(CRYPTO_memcmp(remote_sig, expected_sig, sizeof(expected_sig)) != 0)
#endif
		return CHIAKI_ERR_INVALID_MAC;

	uint8_t secret[CHIAKI_ECDH_SECRET_SIZE];
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	mbedtls_ecp_point remote_public_key;
	mbedtls_mpi shared_secret;
	mbedtls_ecp_point_init(&remote_public_key);
	mbedtls_mpi_init(&shared_secret);
	err = CHIAKI_ERR_INVALID_DATA;
	if(mbedtls_ecp_point_read_binary(&ecdh->group, &remote_public_key, remote_key, remote_key_size) != 0
			|| mbedtls_ecp_check_pubkey(&ecdh->group, &remote_public_key) != 0)
		goto end;
	err = CHIAKI_ERR_UNKNOWN;
	if(mbedtls_ecdh_compute_shared(&ecdh->group, &shared_secret, &remote_public_key, &ecdh->private_key,
			mbedtls_ctr_drbg_random, &ecdh->drbg) != 0
			|| mbedtls_mpi_write_binary(&shared_secret, secret, sizeof(secret)) != 0)
		goto end;
	err = CHIAKI_ERR_SUCCESS;
end:
	mbedtls_mpi_free(&shared_secret);
	mbedtls_ecp_point_free(&remote_public_key);
#else
	EC_POINT *remote_public_key = EC_POINT_new(ecdh->group);
	if(!remote_public_key)
		return CHIAKI_ERR_MEMORY;
	if(!EC_POINT_oct2point(ecdh->group, remote_public_key, remote_key, remote_key_size, NULL)
			|| EC_POINT_is_at_infinity(ecdh->group, remote_public_key)
			|| EC_POINT_is_on_curve(ecdh->group, remote_public_key, NULL) != 1)
		err = CHIAKI_ERR_INVALID_DATA;
	else if(ECDH_compute_key(secret, sizeof(secret), remote_public_key, ecdh->key_local, NULL) != sizeof(secret))
		err = CHIAKI_ERR_UNKNOWN;
	EC_POINT_free(remote_public_key);
#endif
	if(err == CHIAKI_ERR_SUCCESS)
		memcpy(secret_out, secret, sizeof(secret));
#ifdef CHIAKI_LIB_ENABLE_MBEDTLS
	mbedtls_platform_zeroize(secret, sizeof(secret));
#else
	OPENSSL_cleanse(secret, sizeof(secret));
#endif
	return err;
}
