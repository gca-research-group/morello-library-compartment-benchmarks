#include "crypto_workload.h"

#include <openssl/evp.h>
#include <openssl/err.h>
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
#include <openssl/provider.h>
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct crypto_env {
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
    OSSL_PROVIDER *default_provider;
#endif
    EVP_MD *sha256;
    EVP_CIPHER *aes256gcm;
    EVP_PKEY *ed25519_sign_key;
    EVP_PKEY *ed25519_verify_key;
};

static int fail_openssl(const char *where) {
    unsigned long err = ERR_get_error();
    if (err != 0) {
        char buf[256];
        ERR_error_string_n(err, buf, sizeof(buf));
        fprintf(stderr, "%s: %s\n", where, buf);
    } else {
        fprintf(stderr, "%s: unknown OpenSSL error\n", where);
    }
    return 0;
}

static EVP_PKEY *create_ed25519_verify_key_from_private(EVP_PKEY *sign_key) {
    unsigned char pub[32];
    size_t pub_len = sizeof(pub);
    if (!sign_key) return NULL;
    if (EVP_PKEY_get_raw_public_key(sign_key, pub, &pub_len) != 1) {
        fail_openssl("EVP_PKEY_get_raw_public_key(ED25519)");
        return NULL;
    }
    return EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519, NULL, pub, pub_len);
}

crypto_env_t *crypto_env_create(void) {
    crypto_env_t *env = calloc(1, sizeof(*env));
    if (!env) return NULL;

    ERR_clear_error();
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
    env->default_provider = OSSL_PROVIDER_load(NULL, "default");
    if (!env->default_provider) {
        fail_openssl("OSSL_PROVIDER_load(default)");
        free(env);
        return NULL;
    }

    env->sha256 = EVP_MD_fetch(NULL, "SHA256", NULL);
    if (!env->sha256) {
        fail_openssl("EVP_MD_fetch(SHA256)");
        crypto_env_destroy(env);
        return NULL;
    }

    env->aes256gcm = EVP_CIPHER_fetch(NULL, "AES-256-GCM", NULL);
    if (!env->aes256gcm) {
        fail_openssl("EVP_CIPHER_fetch(AES-256-GCM)");
        crypto_env_destroy(env);
        return NULL;
    }

    env->ed25519_sign_key = EVP_PKEY_Q_keygen(NULL, NULL, "ED25519");
    if (!env->ed25519_sign_key) {
        fail_openssl("EVP_PKEY_Q_keygen(ED25519)");
        crypto_env_destroy(env);
        return NULL;
    }
#else
    env->sha256 = (EVP_MD *)EVP_sha256();
    env->aes256gcm = (EVP_CIPHER *)EVP_aes_256_gcm();
    EVP_PKEY_CTX *kctx = EVP_PKEY_CTX_new_id(EVP_PKEY_ED25519, NULL);
    if (!kctx) {
        fail_openssl("EVP_PKEY_CTX_new_id(ED25519)");
        crypto_env_destroy(env);
        return NULL;
    }
    if (EVP_PKEY_keygen_init(kctx) != 1 || EVP_PKEY_keygen(kctx, &env->ed25519_sign_key) != 1) {
        EVP_PKEY_CTX_free(kctx);
        fail_openssl("EVP_PKEY_keygen(ED25519)");
        crypto_env_destroy(env);
        return NULL;
    }
    EVP_PKEY_CTX_free(kctx);
#endif

    env->ed25519_verify_key = create_ed25519_verify_key_from_private(env->ed25519_sign_key);
    if (!env->ed25519_verify_key) {
        fail_openssl("create_ed25519_verify_key_from_private");
        crypto_env_destroy(env);
        return NULL;
    }

    return env;
}

void crypto_env_destroy(crypto_env_t *env) {
    if (!env) return;
    EVP_PKEY_free(env->ed25519_verify_key);
    EVP_PKEY_free(env->ed25519_sign_key);
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
    EVP_CIPHER_free(env->aes256gcm);
    EVP_MD_free(env->sha256);
    OSSL_PROVIDER_unload(env->default_provider);
#endif
    free(env);
}

int cw_sha256_once(crypto_env_t *env, const uint8_t *in, size_t in_len,
                   uint8_t out[32]) {
    if (!env || !in || !out) return 0;
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    unsigned int out_len = 0;
    if (!ctx) return 0;

#if OPENSSL_VERSION_NUMBER >= 0x30000000L
    int ok = EVP_DigestInit_ex2(ctx, env->sha256, NULL)
#else
    int ok = EVP_DigestInit_ex(ctx, env->sha256, NULL)
#endif
          && EVP_DigestUpdate(ctx, in, in_len)
          && EVP_DigestFinal_ex(ctx, out, &out_len)
          && out_len == 32;

    if (!ok) fail_openssl("cw_sha256_once");
    EVP_MD_CTX_free(ctx);
    return ok;
}

int cw_aes256gcm_encrypt_once(crypto_env_t *env,
                              const uint8_t *key, size_t key_len,
                              const uint8_t *iv, size_t iv_len,
                              const uint8_t *aad, size_t aad_len,
                              const uint8_t *pt, size_t pt_len,
                              uint8_t *ct, uint8_t tag[16]) {
    if (!env || !key || !iv || !pt || !ct || !tag) return 0;
    if (key_len != 32) return 0;

    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return 0;

    int out_len = 0;
    int tmp_len = 0;
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
    int ok = EVP_EncryptInit_ex2(ctx, env->aes256gcm, NULL, NULL, NULL)
#else
    int ok = EVP_EncryptInit_ex(ctx, env->aes256gcm, NULL, NULL, NULL)
#endif
          && EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_SET_IVLEN, (int)iv_len, NULL)
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
          && EVP_EncryptInit_ex2(ctx, NULL, key, iv, NULL);
#else
          && EVP_EncryptInit_ex(ctx, NULL, NULL, key, iv);
#endif

    if (ok && aad && aad_len > 0) {
        ok = EVP_EncryptUpdate(ctx, NULL, &tmp_len, aad, (int)aad_len);
    }
    if (ok) {
        ok = EVP_EncryptUpdate(ctx, ct, &out_len, pt, (int)pt_len);
    }
    if (ok) {
        ok = EVP_EncryptFinal_ex(ctx, ct + out_len, &tmp_len);
    }
    if (ok) {
        ok = EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_GET_TAG, 16, tag);
    }

    if (!ok) fail_openssl("cw_aes256gcm_encrypt_once");
    EVP_CIPHER_CTX_free(ctx);
    return ok;
}

int cw_aes256gcm_decrypt_once(crypto_env_t *env,
                              const uint8_t *key, size_t key_len,
                              const uint8_t *iv, size_t iv_len,
                              const uint8_t *aad, size_t aad_len,
                              const uint8_t *ct, size_t ct_len,
                              const uint8_t tag[16],
                              uint8_t *pt_out) {
    if (!env || !key || !iv || !ct || !tag || !pt_out) return 0;
    if (key_len != 32) return 0;

    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return 0;

    int out_len = 0;
    int tmp_len = 0;
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
    int ok = EVP_DecryptInit_ex2(ctx, env->aes256gcm, NULL, NULL, NULL)
#else
    int ok = EVP_DecryptInit_ex(ctx, env->aes256gcm, NULL, NULL, NULL)
#endif
          && EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_SET_IVLEN, (int)iv_len, NULL)
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
          && EVP_DecryptInit_ex2(ctx, NULL, key, iv, NULL);
#else
          && EVP_DecryptInit_ex(ctx, NULL, NULL, key, iv);
#endif

    if (ok && aad && aad_len > 0) {
        ok = EVP_DecryptUpdate(ctx, NULL, &tmp_len, aad, (int)aad_len);
    }
    if (ok) {
        ok = EVP_DecryptUpdate(ctx, pt_out, &out_len, ct, (int)ct_len);
    }
    if (ok) {
        ok = EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_SET_TAG, 16, (void *)tag);
    }
    if (ok) {
        ok = EVP_DecryptFinal_ex(ctx, pt_out + out_len, &tmp_len);
    }

    if (!ok) fail_openssl("cw_aes256gcm_decrypt_once");
    EVP_CIPHER_CTX_free(ctx);
    return ok;
}

int cw_ed25519_sign_once(crypto_env_t *env,
                         const uint8_t *msg, size_t msg_len,
                         uint8_t *sig_out, size_t *sig_len_out) {
    if (!env || !msg || !sig_out || !sig_len_out) return 0;
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    EVP_PKEY_CTX *pctx = NULL;
    if (!ctx) return 0;

    size_t sig_len = 0;
    int ok = EVP_DigestSignInit(ctx, &pctx, NULL, NULL, env->ed25519_sign_key)
          && EVP_DigestSign(ctx, NULL, &sig_len, msg, msg_len)
          && EVP_DigestSign(ctx, sig_out, &sig_len, msg, msg_len);

    if (ok) *sig_len_out = sig_len;
    if (!ok) fail_openssl("cw_ed25519_sign_once");
    EVP_MD_CTX_free(ctx);
    return ok;
}

int cw_ed25519_verify_once(crypto_env_t *env,
                           const uint8_t *msg, size_t msg_len,
                           const uint8_t *sig, size_t sig_len) {
    if (!env || !msg || !sig) return 0;
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    EVP_PKEY_CTX *pctx = NULL;
    if (!ctx) return 0;

    int verify_rc = 0;
    int ok = EVP_DigestVerifyInit(ctx, &pctx, NULL, NULL, env->ed25519_verify_key);
    if (ok) {
        verify_rc = EVP_DigestVerify(ctx, sig, sig_len, msg, msg_len);
        ok = (verify_rc == 1);
    }

    if (!ok) fail_openssl("cw_ed25519_verify_once");
    EVP_MD_CTX_free(ctx);
    return ok;
}
