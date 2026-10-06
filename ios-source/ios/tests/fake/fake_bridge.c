#include "FakeBridge.h"
#include <stdlib.h>
#include <string.h>
struct CBSession { CBCallbacks callbacks; bool started; };
struct CBRegistration { CBRegistrationCallback callback; void *context; };
static FakeBridgeState state;
static CBSession *session;
static CBRegistration *registration;
FakeBridgeState *fake_bridge(void) { return &state; }
void fake_bridge_reset(void) { memset(&state, 0, sizeof(state)); session = NULL; registration = NULL; }
void fake_emit_event(int event, int detail) { if(session) session->callbacks.event(session->callbacks.context, event, detail); }
void fake_finish_registration(int result, uint8_t key) {
    if(!registration) return;
    CBCredentials c; memset(&c, key, sizeof(c));
    registration->callback(registration->context, result, result ? NULL : &c);
}
int cb_session_create(const char *host, bool ps5, const CBCredentials *credentials, CBCallbacks callbacks, CBSession **out) {
    *out = NULL; state.session_creates++;
    if(!host || !credentials) return -1;
    if(state.session_create_result) return state.session_create_result;
    session = calloc(1, sizeof(*session)); session->callbacks = callbacks; state.live_sessions++;
    strncpy(state.last_host, host, sizeof(state.last_host) - 1); state.last_ps5 = ps5;
    *out = session; return 0;
}
int cb_session_start(CBSession *s) { if(state.session_start_result) return state.session_start_result; s->started = true; return 0; }
int cb_session_destroy(CBSession *s) {
    if(!s) return 0;
    if(state.session_destroy_failures > 0) { state.session_destroy_failures--; return state.destroy_error; }
    if(state.emit_during_destroy) s->callbacks.event(s->callbacks.context, 2, CB_QUIT_STOPPED);
    free(s); session = NULL; state.live_sessions--; return 0;
}
int cb_session_controller(CBSession *s, CBController c) { if(!s || !s->started) return -1; state.last_controller = c; state.controller_submissions++; return 0; }
int cb_session_login_pin(CBSession *s, const uint8_t *pin, size_t size) { if(!s || !pin || size != 4) return -1; state.login_pins++; return 0; }
int cb_registration_start(const char *host, bool ps5, const uint8_t account[8], uint32_t pin, CBRegistrationCallback callback, void *context, CBRegistration **out) {
    *out = NULL; state.registration_starts++;
    if(state.registration_start_result) return state.registration_start_result;
    registration = calloc(1, sizeof(*registration)); registration->callback = callback; registration->context = context; state.live_registrations++;
    memcpy(state.last_account, account, 8); state.last_pin = pin; state.last_ps5 = ps5; strncpy(state.last_host, host, sizeof(state.last_host) - 1);
    *out = registration; return 0;
}
int cb_registration_destroy(CBRegistration *r) {
    if(!r) return 0;
    if(state.emit_during_destroy) { CBCredentials c; memset(&c, 7, sizeof(c)); r->callback(r->context, 0, &c); }
    free(r); registration = NULL; state.live_registrations--; return 0;
}
