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
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern void vosk_recognizer_set_words(IntPtr recognizer,int words);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern int vosk_recognizer_accept_waveform(IntPtr recognizer,byte[] pcm,int length);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern IntPtr vosk_recognizer_result(IntPtr recognizer);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern void vosk_recognizer_reset(IntPtr recognizer);
        [DllImport(Lib, CallingConvention=CallingConvention.Cdecl)] static extern void vosk_recognizer_free(IntPtr recognizer);
        IntPtr model, recognizer;
        readonly string[] frases;
        public LocalWake(string directory,string[] chamadas=null) {
            frases=Chamadas.Validar(chamadas ?? Chamadas.Padrao());
            vosk_set_log_level(-1);
            model=vosk_model_new(Utf8(directory));
            if(model==IntPtr.Zero) throw new InvalidOperationException("O modelo português da Bella não carregou. Extraia o ZIP inteiro.");
            foreach(var frase in frases) foreach(var palavra in Chamadas.Fonetica(frase).Split(' '))
                if(vosk_model_find_word(model,Utf8(palavra))<0 && vosk_model_find_word(model,Utf8(Chamadas.Normalizar(palavra)))<0) {
                    Dispose(); throw new InvalidOperationException("O modelo local não reconhece a palavra “"+palavra+"”. Escolha outra frase.");
                }
            var gramatica=new System.Collections.Generic.List<string>();
            foreach(var frase in frases) gramatica.Add(Chamadas.Fonetica(frase));
            gramatica.Add("[unk]"); // Permite rejeitar falas que não são chamadas.
            recognizer=vosk_recognizer_new_grm(model,16000,Utf8(new JavaScriptSerializer().Serialize(gramatica)));
            if(recognizer==IntPtr.Zero) { Dispose(); throw new InvalidOperationException("Não consegui preparar a escuta local."); }
            vosk_recognizer_set_words(recognizer,1);
        }
        static byte[] Utf8(string s) { return Encoding.UTF8.GetBytes(s+"\0"); }
        static string ReadUtf8(IntPtr p) {
            int n=0; while(Marshal.ReadByte(p,n)!=0) n++;
            var b=new byte[n]; Marshal.Copy(p,b,0,n); return Encoding.UTF8.GetString(b);
        }
        public bool Hear(byte[] pcm) {
            int result=vosk_recognizer_accept_waveform(recognizer,pcm,pcm.Length);
            if(result<0) throw new InvalidOperationException("Falha na escuta local.");
            if(result!=1) return false;
            var json=new JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,object>>(
                ReadUtf8(vosk_recognizer_result(recognizer)));
            return Chamadas.Aceita(json,frases);
        }
        public void Reset() { if(recognizer!=IntPtr.Zero) vosk_recognizer_reset(recognizer); }
        public void Dispose() {
            if(recognizer!=IntPtr.Zero) { vosk_recognizer_free(recognizer); recognizer=IntPtr.Zero; }
            if(model!=IntPtr.Zero) { vosk_model_free(model); model=IntPtr.Zero; }
        }
    }
}
