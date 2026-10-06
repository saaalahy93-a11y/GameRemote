#include "GameRemoteBridge.h"
#include <gameremote/session.h>
#include <gameremote/opusdecoder.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
static ChiakiSession *core;
static ChiakiRegist *reg;
static ChiakiOpusDecoder *decoder;
static int init_error, start_error, stop_error, join_error, step;
static CBSession *handle;
static CBRegistration *registration;
ChiakiErrorCode chiaki_lib_init(void) { return CHIAKI_ERR_SUCCESS; }
void chiaki_connect_video_profile_preset(ChiakiConnectVideoProfile *p, ChiakiVideoResolutionPreset r, ChiakiVideoFPSPreset f) { (void)r; p->max_fps=f; }
ChiakiErrorCode chiaki_session_init(ChiakiSession *s, ChiakiConnectInfo *i, ChiakiLog *l) { assert(i->video_profile.codec == CHIAKI_CODEC_H264); assert(l && l->level_mask == 0); core=s; return init_error; }
ChiakiErrorCode chiaki_session_start(ChiakiSession *s) { assert(s==core); return start_error; }
ChiakiErrorCode chiaki_session_stop(ChiakiSession *s) { assert(s==core); if(stop_error) return stop_error; assert(step==0 || step==1); step=1; return 0; }
ChiakiErrorCode chiaki_session_join(ChiakiSession *s) { assert(s==core); if(join_error) return join_error; assert(step==1); step=2; return 0; }
void chiaki_session_fini(ChiakiSession *s) { assert(s==core); assert(step==0 || step==3); step=4; }
void chiaki_opus_decoder_init(ChiakiOpusDecoder *d, ChiakiLog *l) { assert(l); decoder=d; }
void chiaki_opus_decoder_fini(ChiakiOpusDecoder *d) { assert(d==decoder); assert(step==0 || step==2); if(step==2) step=3; }
void chiaki_opus_decoder_get_sink(ChiakiOpusDecoder *d, ChiakiAudioSink *sink) { (void)d; memset(sink,0,sizeof(*sink)); }
void chiaki_controller_state_set_idle(ChiakiControllerState *s) { memset(s,0,sizeof(*s)); }
ChiakiErrorCode chiaki_session_set_controller_state(ChiakiSession *s, ChiakiControllerState *c) { assert(s==core); assert(c->buttons==1 && c->left_x==123); return 0; }
ChiakiErrorCode chiaki_session_set_login_pin(ChiakiSession *s, const uint8_t *p, size_t n) { (void)s; assert(p && n==4); return 0; }
ChiakiErrorCode chiaki_regist_start(ChiakiRegist *r, ChiakiLog *l, const ChiakiRegistInfo *i, ChiakiRegistCb cb, void *u) { assert(l && !l->level_mask && !i->broadcast); reg=r; r->cb=cb; r->cb_user=u; return start_error; }
void chiaki_regist_stop(ChiakiRegist *r) { assert(r==reg && step==0); step=1; }
void chiaki_regist_fini(ChiakiRegist *r) { assert(r==reg && step==1); step=4; }
static const uint8_t *borrowed_video;
static const int16_t *borrowed_audio;
static bool video(void *c, const uint8_t *b, size_t n) { (void)c; assert(b!=borrowed_video && n==4 && b[3]==1); assert(cb_session_destroy(handle)==-2); return true; }
static void audio(void *c, const int16_t *b, size_t f, uint32_t ch, uint32_t rate) { (void)c; assert(b!=borrowed_audio && f==2 && ch==2 && rate==48000 && b[3]==4); }
static int expected_event=2, expected_detail=CB_QUIT_STOPPED, events;
static void event(void *c, int e, int detail) { (void)c; assert(e==expected_event && detail==expected_detail); assert(cb_session_destroy(handle)==-2); events++; }
static void registered(void *c, int result, const CBCredentials *credentials) { (void)c; assert(!result && credentials && credentials->morning[0]==9); assert(cb_registration_destroy(registration)==-2); }
int main(void) {
    CBCredentials credentials={0}; CBCallbacks callbacks={event,video,audio,NULL};
    assert(cb_session_create("",true,&credentials,callbacks,&handle)==-1 && !handle);
    init_error=CHIAKI_ERR_UNKNOWN; assert(cb_session_create("console",true,&credentials,callbacks,&handle)==init_error && !handle); init_error=0;
    assert(!cb_session_create("console",true,&credentials,callbacks,&handle)); start_error=CHIAKI_ERR_UNKNOWN; assert(cb_session_start(handle)==start_error); assert(!cb_session_destroy(handle)); start_error=0; step=0;
    assert(!cb_session_create("console",true,&credentials,callbacks,&handle)); assert(!cb_session_start(handle)); assert(cb_session_start(handle)==-1);
    uint8_t bytes[]={0,0,0,1}; borrowed_video=bytes; assert(core->video_sample_cb(bytes,4,0,false,core->video_sample_cb_user));
    int16_t samples[]={1,2,3,4}; borrowed_audio=samples; decoder->settings_cb(2,48000,decoder->cb_user); decoder->frame_cb(samples,2,decoder->cb_user);
    ChiakiEvent quit={.type=CHIAKI_EVENT_QUIT}; quit.quit.reason=CHIAKI_QUIT_REASON_STOPPED; core->event_cb(&quit,core->event_cb_user);
    ChiakiEvent login={.type=CHIAKI_EVENT_LOGIN_PIN_REQUEST}; expected_event=3; expected_detail=0; core->event_cb(&login,core->event_cb_user);
    login.login_pin_request.pin_incorrect=true; expected_detail=1; core->event_cb(&login,core->event_cb_user); assert(events==3);
    CBController controller={.buttons=1,.lx=123}; assert(!cb_session_controller(handle,controller));
    stop_error=CHIAKI_ERR_UNKNOWN; assert(cb_session_destroy(handle)==stop_error && step==0); stop_error=0;
    join_error=CHIAKI_ERR_UNKNOWN; assert(cb_session_destroy(handle)==join_error && step==1); join_error=0;
    assert(!cb_session_destroy(handle) && step==4); handle=NULL;
    step=0; uint8_t account[8]={0}; assert(!cb_registration_start("console",true,account,12345678,registered,NULL,&registration));
    ChiakiRegisteredHost host={0}; host.rp_key[0]=9; ChiakiRegistEvent success={CHIAKI_REGIST_EVENT_TYPE_FINISHED_SUCCESS,&host}; reg->cb(&success,reg->cb_user);
    assert(!cb_registration_destroy(registration) && step==4);
    start_error=CHIAKI_ERR_UNKNOWN; assert(cb_registration_start("console",true,account,12345678,registered,NULL,&registration)==start_error && !registration);
    puts("bridge lifecycle, owned callback copies, stereo sizing, login-PIN retry detail, failed start/stop and callback-thread rejection passed (mock core)");
}
