#define _POSIX_C_SOURCE 200809L
#include "crypto_workload.h"

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define AES_KEY_LEN 32
#define AES_IV_LEN 12
#define AES_TAG_LEN 16
#define ED25519_SIG_MAX 128

typedef enum {
    WL_SHA256,
    WL_AES_GCM_ENC,
    WL_AES_GCM_DEC,
    WL_ED25519_SIGN,
    WL_ED25519_VERIFY,
    WL_ALL
} workload_t;

typedef struct {
    const char *mode_label;
    workload_t workload;
    size_t *sizes;
    size_t size_count;
    int repetitions;
    int warmup;
    FILE *csv;
} config_t;

static void usage(const char *prog) {
    fprintf(stderr,
            "Usage: %s --mode outside|purecap|benchmark --workload sha256|aes-enc|aes-dec|ed25519-sign|ed25519-verify|all\n"
            "          [--sizes size1,size2,...] [--repetitions N] [--warmup N] [--csv output.csv]\n"
            "Sizes accept suffixes B, K, M, G (binary multiples, e.g. 1M, 16M, 100M, 4K).\n",
            prog);
}

static double read_monotonic_clock_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

static void fill_pattern(uint8_t *buf, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        buf[i] = (uint8_t)((i * 131u + 17u) & 0xffu);
    }
}

static void touch_buffer(volatile uint8_t *buf, size_t len) {
    uint8_t acc = 0;
    for (size_t i = 0; i < len; i += 4096) acc ^= buf[i];
    if (len > 0) acc ^= buf[len - 1];
    (void)acc;
}

static size_t parse_size_token(const char *s, int *ok) {
    errno = 0;
    char *end = NULL;
    unsigned long long val = strtoull(s, &end, 10);
    if (errno || end == s) {
        *ok = 0;
        return 0;
    }
    size_t mult = 1;
    if (*end != '\0') {
        if (end[1] != '\0') {
            *ok = 0;
            return 0;
        }
        switch (*end) {
            case 'b': case 'B': mult = 1; break;
            case 'k': case 'K': mult = 1024ull; break;
            case 'm': case 'M': mult = 1024ull * 1024ull; break;
            case 'g': case 'G': mult = 1024ull * 1024ull * 1024ull; break;
            default: *ok = 0; return 0;
        }
    }
    *ok = 1;
    return (size_t)val * mult;
}

static int parse_sizes(const char *arg, size_t **out_sizes, size_t *out_count) {
    char *copy = strdup(arg);
    if (!copy) return 0;

    size_t cap = 8;
    size_t count = 0;
    size_t *sizes = malloc(cap * sizeof(*sizes));
    if (!sizes) {
        free(copy);
        return 0;
    }

    char *save = NULL;
    for (char *tok = strtok_r(copy, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
        int ok = 0;
        size_t sz = parse_size_token(tok, &ok);
        if (!ok || sz == 0) {
            free(sizes);
            free(copy);
            return 0;
        }
        if (count == cap) {
            cap *= 2;
            size_t *tmp = realloc(sizes, cap * sizeof(*tmp));
            if (!tmp) {
                free(sizes);
                free(copy);
                return 0;
            }
            sizes = tmp;
        }
        sizes[count++] = sz;
    }

    free(copy);
    *out_sizes = sizes;
    *out_count = count;
    return count > 0;
}

static workload_t parse_workload(const char *s, int *ok) {
    *ok = 1;
    if (strcmp(s, "sha256") == 0) return WL_SHA256;
    if (strcmp(s, "aes-enc") == 0) return WL_AES_GCM_ENC;
    if (strcmp(s, "aes-dec") == 0) return WL_AES_GCM_DEC;
    if (strcmp(s, "ed25519-sign") == 0) return WL_ED25519_SIGN;
    if (strcmp(s, "ed25519-verify") == 0) return WL_ED25519_VERIFY;
    if (strcmp(s, "all") == 0) return WL_ALL;
    *ok = 0;
    return WL_ALL;
}

static const char *workload_name(workload_t wl) {
    switch (wl) {
        case WL_SHA256: return "sha256";
        case WL_AES_GCM_ENC:
        case WL_AES_GCM_DEC: return "aes256gcm";
        case WL_ED25519_SIGN:
        case WL_ED25519_VERIFY: return "ed25519";
        case WL_ALL: return "all";
    }
    return "unknown";
}

static const char *operation_name(workload_t wl) {
    switch (wl) {
        case WL_SHA256: return "hash";
        case WL_AES_GCM_ENC: return "encrypt";
        case WL_AES_GCM_DEC: return "decrypt";
        case WL_ED25519_SIGN: return "sign";
        case WL_ED25519_VERIFY: return "verify";
        case WL_ALL: return "all";
    }
    return "unknown";
}

static void write_csv_header(FILE *f) {
    fprintf(f, "mode,workload,operation,size_bytes,repetition,start_time_ms,end_time_ms,success\n");
}

static int run_buffer_workload(config_t *cfg, crypto_env_t *env, workload_t wl, size_t size,
                               const uint8_t *key, const uint8_t *iv, const uint8_t *aad, size_t aad_len) {
    uint8_t digest[32];
    uint8_t tag[AES_TAG_LEN];
    uint8_t *input = malloc(size ? size : 1);
    uint8_t *ciphertext = malloc(size ? size : 1);
    uint8_t *plaintext_out = malloc(size ? size : 1);
    if (!input || !ciphertext || !plaintext_out) {
        fprintf(stderr, "allocation failure for size=%zu\n", size);
        free(input); free(ciphertext); free(plaintext_out);
        return 0;
    }

    fill_pattern(input, size);
    memset(ciphertext, 0, size ? size : 1);
    memset(plaintext_out, 0, size ? size : 1);
    touch_buffer((volatile uint8_t *)input, size);
    touch_buffer((volatile uint8_t *)ciphertext, size);
    touch_buffer((volatile uint8_t *)plaintext_out, size);

    if (wl == WL_AES_GCM_DEC) {
        if (!cw_aes256gcm_encrypt_once(env, key, AES_KEY_LEN, iv, AES_IV_LEN, aad, aad_len,
                                       input, size, ciphertext, tag)) {
            free(input); free(ciphertext); free(plaintext_out);
            return 0;
        }
    }

    for (int w = 0; w < cfg->warmup; ++w) {
        int success = 0;
        switch (wl) {
            case WL_SHA256:
                success = cw_sha256_once(env, input, size, digest);
                break;
            case WL_AES_GCM_ENC:
                success = cw_aes256gcm_encrypt_once(env, key, AES_KEY_LEN, iv, AES_IV_LEN, aad, aad_len,
                                                    input, size, ciphertext, tag);
                break;
            case WL_AES_GCM_DEC:
                success = cw_aes256gcm_decrypt_once(env, key, AES_KEY_LEN, iv, AES_IV_LEN, aad, aad_len,
                                                    ciphertext, size, tag, plaintext_out);
                break;
            default:
                success = 0;
        }
        if (!success) {
            free(input); free(ciphertext); free(plaintext_out);
            return 0;
        }
    }

    for (int rep = 1; rep <= cfg->repetitions; ++rep) {
        int success = 0;
        double start_time_ms = read_monotonic_clock_ms();
        switch (wl) {
            case WL_SHA256:
                success = cw_sha256_once(env, input, size, digest);
                break;
            case WL_AES_GCM_ENC:
                success = cw_aes256gcm_encrypt_once(env, key, AES_KEY_LEN, iv, AES_IV_LEN, aad, aad_len,
                                                    input, size, ciphertext, tag);
                break;
            case WL_AES_GCM_DEC:
                success = cw_aes256gcm_decrypt_once(env, key, AES_KEY_LEN, iv, AES_IV_LEN, aad, aad_len,
                                                    ciphertext, size, tag, plaintext_out);
                break;
            default:
                success = 0;
        }
        double end_time_ms = read_monotonic_clock_ms();
        fprintf(cfg->csv, "%s,%s,%s,%zu,%d,%.6f,%.6f,%d\n",
                cfg->mode_label, workload_name(wl), operation_name(wl), size, rep,
                start_time_ms, end_time_ms, success);
        if (!success) {
            free(input); free(ciphertext); free(plaintext_out);
            return 0;
        }
    }

    free(input);
    free(ciphertext);
    free(plaintext_out);
    return 1;
}

static int run_signature_workload(config_t *cfg, crypto_env_t *env, workload_t wl, size_t size) {
    uint8_t *message = malloc(size ? size : 1);
    uint8_t signature[ED25519_SIG_MAX];
    size_t signature_len = 0;
    if (!message) {
        fprintf(stderr, "allocation failure for size=%zu\n", size);
        return 0;
    }

    fill_pattern(message, size);
    touch_buffer((volatile uint8_t *)message, size);

    if (wl == WL_ED25519_VERIFY) {
        if (!cw_ed25519_sign_once(env, message, size, signature, &signature_len)) {
            free(message);
            return 0;
        }
    }

    for (int w = 0; w < cfg->warmup; ++w) {
        int success = 0;
        switch (wl) {
            case WL_ED25519_SIGN:
                success = cw_ed25519_sign_once(env, message, size, signature, &signature_len);
                break;
            case WL_ED25519_VERIFY:
                success = cw_ed25519_verify_once(env, message, size, signature, signature_len);
                break;
            default:
                success = 0;
        }
        if (!success) {
            free(message);
            return 0;
        }
    }

    for (int rep = 1; rep <= cfg->repetitions; ++rep) {
        int success = 0;
        double start_time_ms = read_monotonic_clock_ms();
        switch (wl) {
            case WL_ED25519_SIGN:
                success = cw_ed25519_sign_once(env, message, size, signature, &signature_len);
                break;
            case WL_ED25519_VERIFY:
                success = cw_ed25519_verify_once(env, message, size, signature, signature_len);
                break;
            default:
                success = 0;
        }
        double end_time_ms = read_monotonic_clock_ms();
        fprintf(cfg->csv, "%s,%s,%s,%zu,%d,%.6f,%.6f,%d\n",
                cfg->mode_label, workload_name(wl), operation_name(wl), size, rep,
                start_time_ms, end_time_ms, success);
        if (!success) {
            free(message);
            return 0;
        }
    }

    free(message);
    return 1;
}

static int default_sizes_for_workload(workload_t wl, size_t **sizes, size_t *count) {
    switch (wl) {
        case WL_SHA256:
        case WL_AES_GCM_ENC:
        case WL_AES_GCM_DEC: {
            static const size_t s[] = {1ull<<20, 16ull<<20, 64ull<<20, 100ull<<20};
            *count = sizeof(s) / sizeof(s[0]);
            *sizes = malloc(sizeof(s));
            if (!*sizes) return 0;
            memcpy(*sizes, s, sizeof(s));
            return 1;
        }
        case WL_ED25519_SIGN:
        case WL_ED25519_VERIFY: {
            static const size_t s[] = {1ull<<10, 4ull<<10, 16ull<<10};
            *count = sizeof(s) / sizeof(s[0]);
            *sizes = malloc(sizeof(s));
            if (!*sizes) return 0;
            memcpy(*sizes, s, sizeof(s));
            return 1;
        }
        default:
            return 0;
    }
}

int main(int argc, char **argv) {
    config_t cfg = {
        .mode_label = "outside",
        .workload = WL_ALL,
        .sizes = NULL,
        .size_count = 0,
        .repetitions = 100,
        .warmup = 1,
        .csv = stdout
    };
    const char *csv_path = NULL;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--mode") == 0 && i + 1 < argc) {
            cfg.mode_label = argv[++i];
        } else if (strcmp(argv[i], "--workload") == 0 && i + 1 < argc) {
            int ok = 0;
            cfg.workload = parse_workload(argv[++i], &ok);
            if (!ok) {
                usage(argv[0]);
                return 2;
            }
        } else if (strcmp(argv[i], "--sizes") == 0 && i + 1 < argc) {
            free(cfg.sizes);
            cfg.sizes = NULL;
            cfg.size_count = 0;
            if (!parse_sizes(argv[++i], &cfg.sizes, &cfg.size_count)) {
                fprintf(stderr, "Invalid --sizes argument\n");
                return 2;
            }
        } else if (strcmp(argv[i], "--repetitions") == 0 && i + 1 < argc) {
            cfg.repetitions = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--warmup") == 0 && i + 1 < argc) {
            cfg.warmup = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--csv") == 0 && i + 1 < argc) {
            csv_path = argv[++i];
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    if (cfg.repetitions <= 0 || cfg.warmup < 0) {
        fprintf(stderr, "repetitions must be > 0 and warmup >= 0\n");
        return 2;
    }

    if (csv_path) {
        cfg.csv = fopen(csv_path, "w");
        if (!cfg.csv) {
            perror("fopen(csv)");
            return 1;
        }
    }
    write_csv_header(cfg.csv);

    crypto_env_t *env = crypto_env_create();
    if (!env) {
        if (cfg.csv != stdout) fclose(cfg.csv);
        return 1;
    }

    uint8_t aes_key[AES_KEY_LEN];
    uint8_t aes_iv[AES_IV_LEN];
    uint8_t aes_aad[32];
    fill_pattern(aes_key, sizeof(aes_key));
    fill_pattern(aes_iv, sizeof(aes_iv));
    fill_pattern(aes_aad, sizeof(aes_aad));

    workload_t list[5];
    size_t list_count = 0;
    if (cfg.workload == WL_ALL) {
        list[0] = WL_SHA256;
        list[1] = WL_AES_GCM_ENC;
        list[2] = WL_AES_GCM_DEC;
        list[3] = WL_ED25519_SIGN;
        list[4] = WL_ED25519_VERIFY;
        list_count = 5;
    } else {
        list[0] = cfg.workload;
        list_count = 1;
    }

    int overall_ok = 1;
    for (size_t wi = 0; wi < list_count; ++wi) {
        workload_t wl = list[wi];
        size_t *sizes = cfg.sizes;
        size_t count = cfg.size_count;
        if (!sizes) {
            if (!default_sizes_for_workload(wl, &sizes, &count)) {
                fprintf(stderr, "failed to get default sizes\n");
                overall_ok = 0;
                break;
            }
        }
        for (size_t si = 0; si < count; ++si) {
            int ok = 0;
            if (wl == WL_SHA256 || wl == WL_AES_GCM_ENC || wl == WL_AES_GCM_DEC) {
                ok = run_buffer_workload(&cfg, env, wl, sizes[si], aes_key, aes_iv, aes_aad, sizeof(aes_aad));
            } else {
                ok = run_signature_workload(&cfg, env, wl, sizes[si]);
            }
            if (!ok) {
                overall_ok = 0;
                break;
            }
        }
        if (!cfg.sizes) free(sizes);
        if (!overall_ok) break;
    }

    crypto_env_destroy(env);
    if (cfg.csv != stdout) fclose(cfg.csv);
    free(cfg.sizes);
    return overall_ok ? 0 : 1;
}
