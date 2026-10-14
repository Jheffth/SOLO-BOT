using System;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using System.Threading;

namespace Bella {
    internal static class ApertarParaFalarTestes {
        sealed class MicrofoneFalso : IMicrophone {
            public int Aberturas, Fechamentos;
            public void Start(Action<byte[]> data,Action<string> error) { Aberturas++; }
            public void Dispose() { Fechamentos++; }
        }
        sealed class Chamada : IWake {
            public int Leituras;
            public bool Hear(byte[] pcm) { Leituras++; return true; }
            public void Reset() { }
            public void Dispose() { }
        }
        static void Check(bool ok,string message) { if(!ok) throw new Exception("Apertar para falar: "+message); }
        public static void Run() {
            var wake=new Chamada(); var captura=new Capture(wake) {PushToTalk=true};
            var tecla=new EsperaTecla();
            int pedidos=0, chamadas=0; byte[] audio=null;
            captura.RequestReady+=b=>{ pedidos++; audio=b; }; captura.WakeDetected+=()=>chamadas++;
            byte[] silencio=new byte[3200], voz=new byte[3200];
            for(int i=1;i<voz.Length;i+=2) voz[i]=10;
            captura.Listen();
            for(int i=0;i<90;i++) captura.Feed(voz);
            captura.Begin(); captura.RecordAfterGreeting(); captura.EndHeld();
            Check(pedidos==0 && chamadas==0 && wake.Leituras==0 && captura.State==Capture.Mode.Listening,"ambiente, chamada e atalho antigo não abrem gravação");
            double agora=0;
            tecla.Atualizar(true,true,agora,5);
            for(int i=0;i<100;i++) { agora+=20; Check(tecla.Atualizar(true,true,agora,5)==AcaoTecla.Nenhuma,"tecla segurada ao iniciar não ativa"); }
            tecla.Atualizar(true,false,agora+=20,5);
            tecla.Atualizar(true,true,agora+=20,5);
            for(int i=0;i<249;i++) { agora+=20; Check(tecla.Atualizar(true,true,agora,5)==AcaoTecla.Nenhuma,"não grava antes dos cinco segundos"); }
            Check(tecla.Atualizar(true,false,agora+=1,5)==AcaoTecla.Nenhuma && pedidos==0,"soltar cedo não envia");
            tecla.Atualizar(true,true,agora+=20,5);
            for(int i=0;i<249;i++) tecla.Atualizar(true,true,agora+=20,5);
            Check(tecla.Atualizar(true,true,agora+=20,5)==AcaoTecla.Comecar && captura.BeginHeld(),"cinco segundos abrem uma gravação");
            for(int i=0;i<6;i++) captura.Feed(voz);
            for(int i=0;i<75;i++) captura.Feed(silencio);
            Check(pedidos==0 && captura.State==Capture.Mode.Recording,"silêncio não envia enquanto segura");
            Check(tecla.Atualizar(true,false,agora+=20,5)==AcaoTecla.Enviar,"soltar conclui"); captura.EndHeld();
            captura.EndHeld();
            Check(pedidos==1 && audio.Length>44 && captura.State==Capture.Mode.Processing,"soltar envia um único WAV");
            captura.Listen(); captura.BeginHeld(); for(int i=0;i<80;i++) captura.Feed(silencio); captura.EndHeld();
            Check(pedidos==1 && captura.State==Capture.Mode.Listening,"soltar sem falar não envia");
            captura.BeginHeld(); for(int i=0;i<600;i++) captura.Feed(voz);
            Check(pedidos==1,"limite de gravação não executa enquanto segura"); captura.EndHeld();
            Check(pedidos==2 && audio.Length<=30*32000+44,"áudio limitado a menos de trinta segundos");
            captura.Listen(); captura.BeginHeld(); captura.Feed(voz); captura.Pause(); captura.EndHeld();
            Check(pedidos==2,"pausar descarta a gravação");
            // Outra espera e bloqueios: resposta em andamento, suspensão ou troca de configuração.
            tecla.Reiniciar(); tecla.Atualizar(true,false,agora+=20,1); tecla.Atualizar(true,true,agora+=20,1);
            for(int i=0;i<49;i++) tecla.Atualizar(true,true,agora+=20,1);
            Check(tecla.Atualizar(true,true,agora+=20,1)==AcaoTecla.Comecar,"tempo configurado de um segundo funciona");
            Check(tecla.Atualizar(false,true,agora+=20,1)==AcaoTecla.Cancelar,"bloqueio cancela em vez de enviar");
            for(int i=0;i<80;i++) Check(tecla.Atualizar(true,true,agora+=20,1)==AcaoTecla.Nenhuma,"ocupada não deixa tecla ainda pressionada ativar depois");
            tecla.Atualizar(true,false,agora+=20,1); tecla.Atualizar(true,true,agora+=20,1);
            Check(tecla.Atualizar(true,true,agora+=2000,1)==AcaoTecla.Nenhuma && !tecla.Contando,"suspensão reinicia espera");
            var parser=new JavaScriptSerializer(); var antigo=parser.Deserialize<Settings>("{}");
            Check(!antigo.PushToTalk && antigo.TalkKey==119 && antigo.TalkSeconds==5,"cadastro antigo preserva chamada por voz");
            var salvo=parser.Deserialize<Settings>(parser.Serialize(new Settings {PushToTalk=true,TalkKey=120,TalkModifiers=6,TalkSeconds=3}));
            Check(salvo.PushToTalk && salvo.TalkKey==120 && salvo.TalkModifiers==6 && salvo.TalkSeconds==3,"tecla, modificadores e tempo sobrevivem ao reinício");
            foreach(int invalid in new[] {0,31}) {
                bool recusou=false; try { ApertarParaFalar.Validar(119,0,invalid); } catch(InvalidOperationException) { recusou=true; }
                Check(recusou,"tempo inválido não é salvo");
            }
            Check(!ApertarParaFalar.TeclaValida(17) && !ApertarParaFalar.TeclaValida(1),"modificador isolado e botão do mouse não viram atalho");
            var microfone=new MicrofoneFalso();
            var contexto=SynchronizationContext.Current;
            bool autoInstalar=WindowsFormsSynchronizationContext.AutoInstall;
            try {
            // Não instala um contexto de janela em um autoteste sem loop de mensagens.
            WindowsFormsSynchronizationContext.AutoInstall=false;
            using(var janela=new Control())
            using(var nucleo=new Nucleo(janela,new Settings {PushToTalk=true,Server="https://test.invalid",Key="bella_"+new string('x',43)},()=>microfone)) {
                nucleo.StartListening().GetAwaiter().GetResult();
                nucleo.Begin().GetAwaiter().GetResult();
                Check(nucleo.Escutando && microfone.Aberturas==0,"modo armado e botão antigo mantêm microfone fechado");
                Check(nucleo.ComecarPorTecla() && microfone.Aberturas==1,"ativação abre o microfone uma vez");
                Check(!nucleo.ComecarPorTecla() && microfone.Aberturas==1,"tecla repetida não cria segunda gravação");
                nucleo.SoltarTecla(true);
                Check(microfone.Fechamentos==1 && nucleo.Modo==Capture.Mode.Listening,"cancelar fecha o microfone e preserva a espera");
                nucleo.Pause();
                Check(!nucleo.ComecarPorTecla() && microfone.Aberturas==1,"modo pausado não ativa pela tecla");
            }
            } finally {
                WindowsFormsSynchronizationContext.AutoInstall=autoInstalar;
                SynchronizationContext.SetSynchronizationContext(contexto);
            }
        }
    }
}
