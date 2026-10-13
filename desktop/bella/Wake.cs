using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

namespace Bella {
    public sealed class LocalWake : IWake {
        const string Lib="libvosk.dll";
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern void vosk_set_log_level(int level);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern IntPtr vosk_model_new(byte[] path);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern void vosk_model_free(IntPtr model);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern int vosk_model_find_word(IntPtr model, byte[] word);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern IntPtr vosk_recognizer_new_grm(IntPtr model,float rate,byte[] grammar);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern int vosk_recognizer_accept_waveform(IntPtr recognizer,byte[] pcm,int length);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern IntPtr vosk_recognizer_partial_result(IntPtr recognizer);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern IntPtr vosk_recognizer_result(IntPtr recognizer);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern void vosk_recognizer_reset(IntPtr recognizer);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern void vosk_recognizer_free(IntPtr recognizer);
        IntPtr model, recognizer;
        public LocalWake(string directory) {
            vosk_set_log_level(-1);
            model=vosk_model_new(Utf8(directory));
            if(model==IntPtr.Zero) throw new InvalidOperationException("O modelo português da Bella não carregou. Extraia o ZIP inteiro.");
            if(vosk_model_find_word(model,Utf8("bela"))<0) { Dispose(); throw new InvalidOperationException("Este modelo não reconhece o nome Bella."); }
            recognizer=vosk_recognizer_new_grm(model,16000,Utf8("[\"bela\", \"ei bela\", \"[unk]\"]"));
            if(recognizer==IntPtr.Zero) { Dispose(); throw new InvalidOperationException("Não consegui preparar a escuta local."); }
        }
        static byte[] Utf8(string s) { return Encoding.UTF8.GetBytes(s+"\0"); }
        static string ReadUtf8(IntPtr p) {
            int n=0; while(Marshal.ReadByte(p,n)!=0) n++;
            var b=new byte[n]; Marshal.Copy(p,b,0,n); return Encoding.UTF8.GetString(b);
        }
        public bool Hear(byte[] pcm) {
            int result=vosk_recognizer_accept_waveform(recognizer,pcm,pcm.Length);
            if(result<0) throw new InvalidOperationException("Falha na escuta local.");
            var json=new JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,object>>(
                ReadUtf8(result==1?vosk_recognizer_result(recognizer):vosk_recognizer_partial_result(recognizer)));
            object text; json.TryGetValue(result==1?"text":"partial",out text);
            return Array.IndexOf((text as string ?? "").Split(' '),"bela")>=0;
        }
        public void Reset() { if(recognizer!=IntPtr.Zero) vosk_recognizer_reset(recognizer); }
        public void Dispose() {
            if(recognizer!=IntPtr.Zero) { vosk_recognizer_free(recognizer); recognizer=IntPtr.Zero; }
            if(model!=IntPtr.Zero) { vosk_model_free(model); model=IntPtr.Zero; }
        }
    }
}
