// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
#include "GameRemoteBridge.h"
#include <gameremote/session.h>
#include <gameremote/opusdecoder.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
struct CBSession { ChiakiSession core; ChiakiLog log; ChiakiOpusDecoder decoder; CBCallbacks callbacks; bool started; uint32_t channels, rate; };
struct CBRegistration { ChiakiRegist core; ChiakiLog log; CBRegistrationCallback callback; void *context; };
static _Thread_local unsigned callback_depth;
static pthread_once_t once = PTHREAD_ONCE_INIT;
static int init_result;
static void initialize(void) { init_result = chiaki_lib_init(); }
static void wipe(void *p, size_t n) { volatile uint8_t *v = p; while(n--) *v++ = 0; }
#define SAME(bridge, core) _Static_assert((int)(bridge) == (int)(core), #bridge)
SAME(CB_QUIT_NONE, CHIAKI_QUIT_REASON_NONE); SAME(CB_QUIT_STOPPED, CHIAKI_QUIT_REASON_STOPPED);
SAME(CB_QUIT_SESSION_REQUEST_UNKNOWN, CHIAKI_QUIT_REASON_SESSION_REQUEST_UNKNOWN); SAME(CB_QUIT_SESSION_REQUEST_REFUSED, CHIAKI_QUIT_REASON_SESSION_REQUEST_CONNECTION_REFUSED);
SAME(CB_QUIT_IN_USE, CHIAKI_QUIT_REASON_SESSION_REQUEST_RP_IN_USE); SAME(CB_QUIT_CRASH, CHIAKI_QUIT_REASON_SESSION_REQUEST_RP_CRASH);
SAME(CB_QUIT_VERSION_MISMATCH, CHIAKI_QUIT_REASON_SESSION_REQUEST_RP_VERSION_MISMATCH); SAME(CB_QUIT_CTRL_UNKNOWN, CHIAKI_QUIT_REASON_CTRL_UNKNOWN);
SAME(CB_QUIT_CTRL_CONNECT_FAILED, CHIAKI_QUIT_REASON_CTRL_CONNECT_FAILED); SAME(CB_QUIT_CTRL_REFUSED, CHIAKI_QUIT_REASON_CTRL_CONNECTION_REFUSED);
SAME(CB_QUIT_STREAM_UNKNOWN, CHIAKI_QUIT_REASON_STREAM_CONNECTION_UNKNOWN); SAME(CB_QUIT_REMOTE_DISCONNECTED, CHIAKI_QUIT_REASON_STREAM_CONNECTION_REMOTE_DISCONNECTED);
SAME(CB_QUIT_REMOTE_SHUTDOWN, CHIAKI_QUIT_REASON_STREAM_CONNECTION_REMOTE_SHUTDOWN);
// The Swift input layer passes these bits through CBController.buttons unchanged.
SAME(1 << 12, CHIAKI_CONTROLLER_BUTTON_OPTIONS); SAME(1 << 13, CHIAKI_CONTROLLER_BUTTON_SHARE);
SAME(1 << 14, CHIAKI_CONTROLLER_BUTTON_TOUCHPAD); SAME(1 << 15, CHIAKI_CONTROLLER_BUTTON_PS);
static void event(ChiakiEvent *e, void *user) {
    CBSession *s = user; int kind = 0, reason = 0;
    if(e->type == CHIAKI_EVENT_CONNECTED) kind = 1;
    else if(e->type == CHIAKI_EVENT_QUIT) { kind = 2; reason = e->quit.reason; }
    else if(e->type == CHIAKI_EVENT_LOGIN_PIN_REQUEST) { kind = 3; reason = e->login_pin_request.pin_incorrect ? 1 : 0; }
    if(kind && s->callbacks.event) { callback_depth++; s->callbacks.event(s->callbacks.context, kind, reason); callback_depth--; }
}
static bool video(uint8_t *bytes, size_t size, int32_t lost, bool recovered, void *user) {
    (void)lost; (void)recovered; CBSession *s = user;
    if(!s->callbacks.video || !size || size > 8 * 1024 * 1024) return false;
    uint8_t *copy = malloc(size); if(!copy) return false; memcpy(copy, bytes, size);
    callback_depth++; bool accepted = s->callbacks.video(s->callbacks.context, copy, size); callback_depth--;
    free(copy); return accepted;
}
static void audio_settings(uint32_t channels, uint32_t rate, void *user) { CBSession *s = user; s->channels = channels; s->rate = rate; }
static void audio(int16_t *samples, size_t frames, void *user) {
    CBSession *s = user;
    if(!s->callbacks.audio || !s->channels || s->channels > 2 || frames > 5760 || !s->rate) return;
    size_t size = frames * s->channels * sizeof(int16_t); int16_t *copy = malloc(size); if(!copy) return;
    memcpy(copy, samples, size); callback_depth++; s->callbacks.audio(s->callbacks.context, copy, frames, s->channels, s->rate); callback_depth--; free(copy);
}
int cb_session_create(const char *host, bool ps5, const CBCredentials *credentials, CBCallbacks callbacks, CBSession **out) {
    if(out) *out = NULL;
    if(callback_depth) return -2;
    if(!out || !host || !host[0] || strlen(host) > 255 || !credentials) return -1;
    pthread_once(&once, initialize); if(init_result) return init_result;
    CBSession *s = calloc(1, sizeof(*s)); if(!s) return -1;
    ChiakiConnectInfo info = {0}; info.host = host; info.ps5 = ps5; info.packet_loss_max = 0.01;
    info.enable_idr_on_fec_failure = true;
    memcpy(info.regist_key, credentials->registration_key, 16); memcpy(info.morning, credentials->morning, 16);
    chiaki_connect_video_profile_preset(&info.video_profile, CHIAKI_VIDEO_RESOLUTION_PRESET_720p, CHIAKI_VIDEO_FPS_PRESET_60);
    info.video_profile.codec = CHIAKI_CODEC_H264;
    int result = chiaki_session_init(&s->core, &info, &s->log); wipe(&info, sizeof(info));
    if(result) { wipe(s, sizeof(*s)); free(s); return result; }
    s->callbacks = callbacks; chiaki_opus_decoder_init(&s->decoder, &s->log);
    chiaki_opus_decoder_set_cb(&s->decoder, audio_settings, audio, s);
    ChiakiAudioSink sink; chiaki_opus_decoder_get_sink(&s->decoder, &sink); chiaki_session_set_audio_sink(&s->core, &sink);
    chiaki_session_set_event_cb(&s->core, event, s); chiaki_session_set_video_sample_cb(&s->core, video, s);
    *out = s; return 0;
}
int cb_session_start(CBSession *s) { if(callback_depth) return -2; if(!s || s->started) return -1; int r = chiaki_session_start(&s->core); if(!r) s->started = true; return r; }
int cb_session_destroy(CBSession *s) {
    if(callback_depth) return -2; if(!s) return 0;
    if(s->started) { int r = chiaki_session_stop(&s->core); if(r) return r; r = chiaki_session_join(&s->core); if(r) return r; s->started = false; }
    chiaki_opus_decoder_fini(&s->decoder); chiaki_session_fini(&s->core); wipe(s, sizeof(*s)); free(s); return 0;
}
int cb_session_controller(CBSession *s, CBController c) {
    if(!s || !s->started) return -1;
    ChiakiControllerState state; chiaki_controller_state_set_idle(&state);
    state.buttons = c.buttons; state.l2_state = c.l2; state.r2_state = c.r2; state.left_x = c.lx; state.left_y = c.ly; state.right_x = c.rx; state.right_y = c.ry;
    return chiaki_session_set_controller_state(&s->core, &state);
}
int cb_session_login_pin(CBSession *s, const uint8_t *pin, size_t size) { if(!s || !s->started || !pin || size != 4) return -1; return chiaki_session_set_login_pin(&s->core, pin, size); }
static void registered(ChiakiRegistEvent *e, void *user) {
    CBRegistration *r = user; CBCredentials c = {0}; int result = -1;
    if(e->type == CHIAKI_REGIST_EVENT_TYPE_FINISHED_SUCCESS && e->registered_host) {
        memcpy(c.registration_key, e->registered_host->rp_regist_key, 16); memcpy(c.morning, e->registered_host->rp_key, 16); result = 0;
    }
    callback_depth++; r->callback(r->context, result, result ? NULL : &c); callback_depth--; wipe(&c, sizeof(c));
}
int cb_registration_start(const char *host, bool ps5, const uint8_t account[8], uint32_t pin, CBRegistrationCallback callback, void *context, CBRegistration **out) {
    if(out) *out = NULL; if(callback_depth) return -2;
    if(!out || !host || !host[0] || strlen(host) > 255 || !account || !callback || pin > 99999999) return -1;
    pthread_once(&once, initialize); if(init_result) return init_result;
    CBRegistration *r = calloc(1, sizeof(*r)); if(!r) return -1; r->callback = callback; r->context = context;
    ChiakiRegistInfo info = {0}; info.host = host; info.target = ps5 ? CHIAKI_TARGET_PS5_1 : CHIAKI_TARGET_PS4_10;
    info.broadcast = false; info.pin = pin; memcpy(info.psn_account_id, account, 8);
    int result = chiaki_regist_start(&r->core, &r->log, &info, registered, r); wipe(&info, sizeof(info));
    if(result) { free(r); return result; } *out = r; return 0;
}
int cb_registration_destroy(CBRegistration *r) { if(callback_depth) return -2; if(!r) return 0; chiaki_regist_stop(&r->core); chiaki_regist_fini(&r->core); wipe(r, sizeof(*r)); free(r); return 0; }
