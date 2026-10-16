using System;
using System.Collections.Generic;
using System.IO;
using System.Speech.AudioFormat;
using System.Speech.Synthesis;
using System.Web.Script.Serialization;

namespace Bella {
    internal static class ChamadasTestes {
        static void Check(bool ok,string message) { if(!ok) throw new Exception("Frases de ativação: "+message); }
        static Dictionary<string,object> Fala(string texto,double confianca=0.99) {
            var palavras=new List<object>();
            foreach(var palavra in texto.Split(' ')) palavras.Add(new Dictionary<string,object> {{"word",palavra},{"conf",confianca}});
            return new Dictionary<string,object> {{"text",texto},{"result",palavras.ToArray()}};
        }
        sealed class Detector : IWake {
            public Dictionary<string,object> Resultado;
            public string[] Frases=Chamadas.Padrao();
            public bool Hear(byte[] pcm) { return Chamadas.Aceita(Resultado,Frases); }
            public void Reset() { }
            public void Dispose() { }
        }
        public static void Run() {
            var frases=Chamadas.Validar(new[] {"Olá Bella,", "Oi Bella", "E aí Bella"});
            foreach(var texto in new[] {"olá bela", "oi bela", "e aí bela"})
                Check(Chamadas.Aceita(Fala(texto),frases),"reconhece cada uma das três frases completas");
            Check(Chamadas.Aceita(Fala("OLA BELLA"),frases),"acentos, caixa e grafia fonética são equivalentes");
            foreach(var texto in new[] {"bela", "olá", "ei", "ei bela", "a casa é bela", "olá bela tudo bem", "não diga olá bela", "olá [unk] bela", "abra os downloads"})
                Check(!Chamadas.Aceita(Fala(texto),frases),"ignora conversa, frase não cadastrada e chamada incompleta: "+texto);
            Check(!Chamadas.Aceita(new Dictionary<string,object> {{"partial","olá bela"}},frases),"resultado parcial nunca ativa");
            Check(!Chamadas.Aceita(Fala("olá bela",0.6),frases),"baixa confiança não ativa");
            var inconsistente=Fala("olá bela"); inconsistente["result"]=Fala("outra coisa")["result"];
            Check(!Chamadas.Aceita(inconsistente,frases),"palavras reconhecidas precisam conferir com a frase final");
            foreach(var invalida in new[] {new string[0], new[] {"", " "}, new[] {"Olá Bella", "ola bela"},
                     new[] {"um", "dois", "três", "quatro"}, new[] {new string('a',81)}, new[] {"[unk]"}}) {
                bool recusou=false; try { Chamadas.Validar(invalida); } catch(InvalidOperationException) { recusou=true; }
                Check(recusou,"recusa configuração vazia, duplicada, excessiva ou inválida");
            }
            var personalizada=Chamadas.Validar(new[] {"Oi Bella", "", " "});
            Check(personalizada.Length==1 && Chamadas.Aceita(Fala("oi bela"),personalizada) &&
                  !Chamadas.Aceita(Fala("olá bela"),personalizada),"edição substitui frases antigas e ignora campos vazios");
            var json=new JavaScriptSerializer();
            var antiga=json.Deserialize<Settings>("{\"Threshold\":350}");
            Check(antiga.WakePhrases.Length==3 && antiga.WakePhrases[0]=="Olá Bella","configuração antiga ganha os três padrões seguros");
            var restaurada=json.Deserialize<Settings>(json.Serialize(new Settings {WakePhrases=personalizada}));
            Check(restaurada.WakePhrases.Length==1 && restaurada.WakePhrases[0]=="Oi Bella","frases personalizadas sobrevivem à serialização das preferências");
            var detector=new Detector {Resultado=Fala("abra os downloads")};
            var captura=new Capture(detector); int chamadas=0, pedidos=0;
            captura.WakeDetected+=()=>chamadas++; captura.RequestReady+=b=>pedidos++;
            captura.Listen(); captura.Feed(new byte[3200]);
            Check(chamadas==0 && pedidos==0 && captura.State==Capture.Mode.Listening,"conversa comum não saúda nem grava pedido");
            detector.Resultado=Fala("olá bela"); captura.Feed(new byte[3200]);
            Check(chamadas==1 && pedidos==0 && captura.State==Capture.Mode.Greeting,"frase completa inicia apenas a saudação");
            captura.Pause(); captura.Feed(new byte[3200]);
            Check(chamadas==1,"escuta pausada não ativa");
            var modelo=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"modelo");
            using(var local=new LocalWake(modelo,personalizada)) {
                for(int i=0;i<40;i++) Check(!local.Hear(new byte[3200]),"modelo real personalizado ignora silêncio");
                local.Reset();
            }
            bool desconhecida=false;
            try { using(var local=new LocalWake(modelo,new[] {"xyzqwertz bela"})) { } }
            catch(InvalidOperationException) { desconhecida=true; }
            Check(desconhecida,"não salva palavras que o modelo local não pode reconhecer");
            TestarAudioPortugues(modelo);
        }
        static void TestarAudioPortugues(string modelo) {
            using(var sintetizador=new SpeechSynthesizer()) {
                string voz=null;
                foreach(var instalada in sintetizador.GetInstalledVoices())
                    if(instalada.Enabled && instalada.VoiceInfo.Culture.Name=="pt-BR") { voz=instalada.VoiceInfo.Name; break; }
                // O Windows do CI pode ter só inglês. A filtragem e o modelo real são testados acima.
                if(voz==null) return;
                sintetizador.SelectVoice(voz);
                using(var detector=new LocalWake(modelo)) {
                    int indice=0;
                    foreach(var frase in new[] {"Olá Bela", "Oi Bela", "E aí Bela", "Ei Bela",
                             "Hoje eu vou abrir meus documentos", "Vamos trabalhar agora", "A casa ficou bela", "Bela"}) {
                        using(var audio=new MemoryStream()) {
                            sintetizador.SetOutputToAudioStream(audio,new SpeechAudioFormatInfo(16000,AudioBitsPerSample.Sixteen,AudioChannel.Mono));
                            sintetizador.Speak(frase);
                            var pcm=audio.ToArray(); bool ativou=false;
                            // Simula a espera silenciosa antes da fala, sem usar o microfone.
                            for(int i=0;i<12;i++) detector.Hear(new byte[3200]);
                            for(int inicio=0;inicio<pcm.Length;inicio+=3200) {
                                var trecho=new byte[Math.Min(3200,pcm.Length-inicio)];
                                Array.Copy(pcm,inicio,trecho,0,trecho.Length);
                                if(detector.Hear(trecho)) ativou=true;
                            }
                            for(int i=0;i<22;i++) if(detector.Hear(new byte[3200])) ativou=true;
                            Check(ativou==(indice<3),"áudio português: "+frase);
                            indice++; detector.Reset();
                        }
                    }
                }
            }
        }
    }
}
