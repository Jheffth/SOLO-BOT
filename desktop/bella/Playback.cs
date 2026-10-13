using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Speech.Synthesis;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Bella {
    public sealed class Playback : IDisposable {
        [DllImport("winmm.dll",CharSet=CharSet.Unicode)] static extern int mciSendString(string command,StringBuilder result,int size,IntPtr callback);
        readonly SpeechSynthesizer speech=new SpeechSynthesizer();
        CancellationTokenSource cancel;
        public Playback() {
            var pt=speech.GetInstalledVoices().FirstOrDefault(v=>v.Enabled && v.VoiceInfo.Culture.Name.StartsWith("pt"));
            if(pt!=null) speech.SelectVoice(pt.VoiceInfo.Name);
        }
        public async Task Say(Reply reply) {
            Stop(); cancel=new CancellationTokenSource(); var token=cancel.Token;
            string path=null;
            try {
                if(!String.IsNullOrEmpty(reply.audio_base64) && reply.mime=="audio/mpeg") {
                    path=Path.Combine(Path.GetTempPath(),"Bella-"+Guid.NewGuid()+".mp3");
                    File.WriteAllBytes(path,Convert.FromBase64String(reply.audio_base64));
                    if(mciSendString("open \""+path+"\" type mpegvideo alias BellaReply",null,0,IntPtr.Zero)==0
                        && mciSendString("play BellaReply",null,0,IntPtr.Zero)==0) {
                        while(true) {
                            token.ThrowIfCancellationRequested();
                            var mode=new StringBuilder(64);
                            if(mciSendString("status BellaReply mode",mode,mode.Capacity,IntPtr.Zero)!=0 || mode.ToString()!="playing") break;
                            await Task.Delay(100,token);
                        }
                        return;
                    }
                }
                token.ThrowIfCancellationRequested();
                var done=new TaskCompletionSource<bool>();
                EventHandler<SpeakCompletedEventArgs> ended=(s,e)=>done.TrySetResult(true);
                speech.SpeakCompleted+=ended;
                try {
                    using(token.Register(()=>done.TrySetCanceled())) {
                        speech.SpeakAsync(reply.falar ?? reply.texto ?? "Pronto.");
                        await done.Task;
                    }
                } finally { speech.SpeakCompleted-=ended; }
            } finally {
                mciSendString("close BellaReply",null,0,IntPtr.Zero);
                if(path!=null && File.Exists(path)) File.Delete(path);
            }
        }
        public void Stop() {
            if(cancel!=null) { cancel.Cancel(); cancel.Dispose(); cancel=null; }
            mciSendString("stop BellaReply",null,0,IntPtr.Zero);
            speech.SpeakAsyncCancelAll();
        }
        public void Dispose() { Stop(); speech.Dispose(); }
    }
}
