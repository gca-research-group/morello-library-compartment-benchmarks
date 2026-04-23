#ifndef CRYPTO_WORKLOAD_H
#define CRYPTO_WORKLOAD_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct crypto_env crypto_env_t;

crypto_env_t *crypto_env_create(void);
void crypto_env_destroy(crypto_env_t *env);

/* One-shot workloads. Return 1 on success, 0 on failure. */
int cw_sha256_once(crypto_env_t *env, const uint8_t *in, size_t in_len,
                   uint8_t out[32]);

int cw_aes256gcm_encrypt_once(crypto_env_t *env,
                              const uint8_t *key, size_t key_len,
                              const uint8_t *iv, size_t iv_len,
                              const uint8_t *aad, size_t aad_len,
                              const uint8_t *pt, size_t pt_len,
                              uint8_t *ct, uint8_t tag[16]);

int cw_aes256gcm_decrypt_once(crypto_env_t *env,
                              const uint8_t *key, size_t key_len,
                              const uint8_t *iv, size_t iv_len,
                              const uint8_t *aad, size_t aad_len,
                              const uint8_t *ct, size_t ct_len,
                              const uint8_t tag[16],
                              uint8_t *pt_out);

int cw_ed25519_sign_once(crypto_env_t *env,
                         const uint8_t *msg, size_t msg_len,
                         uint8_t *sig_out, size_t *sig_len_out);

int cw_ed25519_verify_once(crypto_env_t *env,
                           const uint8_t *msg, size_t msg_len,
                           const uint8_t *sig, size_t sig_len);

#ifdef __cplusplus
}
#endif

#endif
