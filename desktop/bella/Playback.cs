using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Bella {
    public sealed class Playback : IDisposable {
        [DllImport("winmm.dll",CharSet=CharSet.Unicode)] static extern int mciSendString(string command,StringBuilder result,int size,IntPtr callback);
        CancellationTokenSource cancel;
        public async Task Say(Reply reply) {
            Stop(); cancel=new CancellationTokenSource(); var token=cancel.Token;
            string path=null;
            bool temporary=false;
            try {
                if(reply.mime=="audio/mpeg" && (!String.IsNullOrEmpty(reply.AudioPath) || !String.IsNullOrEmpty(reply.audio_base64))) {
                    path=reply.AudioPath;
                    if(String.IsNullOrEmpty(path)) {
                        path=Path.Combine(Path.GetTempPath(),"Bella-"+Guid.NewGuid()+".mp3"); temporary=true;
                        File.WriteAllBytes(path,Convert.FromBase64String(reply.audio_base64));
                    }
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
                throw new InvalidOperationException("Não foi possível reproduzir a voz configurada no Solo Bot. Confira a conexão e a voz no painel; a resposta está na tela.");
            } finally {
                mciSendString("close BellaReply",null,0,IntPtr.Zero);
                if(temporary && path!=null && File.Exists(path)) File.Delete(path);
            }
        }
        public void Stop() {
            if(cancel!=null) { cancel.Cancel(); cancel.Dispose(); cancel=null; }
            mciSendString("stop BellaReply",null,0,IntPtr.Zero);
        }
        public void Dispose() { Stop(); }
    }
}
