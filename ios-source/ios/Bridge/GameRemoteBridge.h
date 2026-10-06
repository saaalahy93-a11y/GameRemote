// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct CBSession CBSession;
typedef struct CBRegistration CBRegistration;
typedef struct { uint8_t registration_key[16], morning[16]; } CBCredentials;
typedef struct { uint32_t buttons; uint8_t l2, r2; int16_t lx, ly, rx, ry; } CBController;
// Quit details delivered with event 2. Values are checked against the core at compile time.
typedef enum {
    CB_QUIT_NONE = 0, CB_QUIT_STOPPED = 1, CB_QUIT_SESSION_REQUEST_UNKNOWN = 2, CB_QUIT_SESSION_REQUEST_REFUSED = 3,
    CB_QUIT_IN_USE = 4, CB_QUIT_CRASH = 5, CB_QUIT_VERSION_MISMATCH = 6, CB_QUIT_CTRL_UNKNOWN = 7,
    CB_QUIT_CTRL_CONNECT_FAILED = 8, CB_QUIT_CTRL_REFUSED = 9, CB_QUIT_STREAM_UNKNOWN = 10,
    CB_QUIT_REMOTE_DISCONNECTED = 11, CB_QUIT_REMOTE_SHUTDOWN = 12
} CBQuitReason;
// All callback payloads are owned copies, valid until callback returns. Copy before queuing.
// Callbacks run on core threads. Never call stop/destroy/start or other lifecycle APIs in callbacks.
// Lifecycle/controller APIs must be serialized by the caller on its own worker queue.
typedef struct {
    // 1 connected; 2 quit (detail: CBQuitReason); 3 login PIN requested (detail: 1 when the previous PIN was rejected)
    void (*event)(void *context, int event, int detail);
    bool (*video)(void *context, const uint8_t *bytes, size_t size);
    void (*audio)(void *context, const int16_t *samples, size_t frames, uint32_t channels, uint32_t rate);
    void *context;
} CBCallbacks;
// Returns a core error (>0), -1 invalid input/allocation, -2 forbidden callback-thread lifecycle.
int cb_session_create(const char *host, bool ps5, const CBCredentials *credentials, CBCallbacks callbacks, CBSession **out);
int cb_session_start(CBSession *session);
int cb_session_destroy(CBSession *session); // stop -> join -> decoder fini -> session fini -> free
int cb_session_controller(CBSession *session, CBController controller);
int cb_session_login_pin(CBSession *session, const uint8_t *pin, size_t size);
typedef void (*CBRegistrationCallback)(void *context, int result, const CBCredentials *credentials);
int cb_registration_start(const char *host, bool ps5, const uint8_t account[8], uint32_t pin,
                          CBRegistrationCallback callback, void *context, CBRegistration **out);
int cb_registration_destroy(CBRegistration *registration); // stop -> fini (joins) -> free
#ifdef __cplusplus
}
#endif
