// Host-test double for GameRemoteBridge.c. Implements the same C ABI with scripted outcomes;
// it performs no networking and is never part of the app target.
#pragma once
#include "GameRemoteBridge.h"
typedef struct {
    int registration_start_result, session_create_result, session_start_result;
    int session_destroy_failures;      // next N destroys fail with destroy_error and keep the session
    int destroy_error;
    bool emit_during_destroy;          // fire a callback from inside destroy, as a core thread can
    int live_sessions, live_registrations, session_creates, registration_starts, login_pins;
    CBController last_controller; int controller_submissions;
    uint8_t last_account[8]; uint32_t last_pin; bool last_ps5; char last_host[256];
} FakeBridgeState;
FakeBridgeState *fake_bridge(void);
void fake_bridge_reset(void);
void fake_emit_event(int event, int detail);            // on the live session
void fake_finish_registration(int result, uint8_t key); // on the live registration
