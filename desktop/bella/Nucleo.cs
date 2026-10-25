using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

namespace Bella {
    // O NÚCLEO DA BELLA — escuta, saudação, pedido e resposta.
    //
    // É o mesmo comportamento que morava dentro da janela antiga (BellaForm),
    // separado da tela: quem desenha (Janela, MiniBella) só assina os eventos
    // e chama os métodos. Tudo roda na thread da interface; o que vem do
    // microfone entra por Ui(), como antes.
    public sealed class Nucleo : IDisposable {
        readonly Control dono;
        readonly Playback player=new Playback();
        readonly Arquivos arquivos;
        readonly IndicePastas indicePastas;
        readonly PedidosWindows pedidos=new PedidosWindows();
        readonly Programas programas;
        public System.Collections.Generic.Dictionary<string,long> Tempos {get {return pedidos.Tempos;}}
        public long TempoChamada {get;private set;}
        LocalWake wake;
        Capture capture;
        IMicrophone mic;
        readonly Func<IMicrophone> criarMicrofone;
        GreetingLibrary greetings;
        string greetingConnection;
        bool listening, starting, busy, quitting;
        readonly Stopwatch relogioNivel=Stopwatch.StartNew();
        long ultimoNivel;

        public Settings Config { get; private set; }
        public bool Escutando { get { return listening; } }
        public bool Ocupada { get { return busy; } }
        public Capture.Mode Modo { get { return capture==null ? (listening?Capture.Mode.Listening:Capture.Mode.Paused) : capture.State; } }

        /// <summary>Mudou o que a Bella está fazendo (modo, escuta, ocupada).</summary>
        public event Action EstadoMudou;
        /// <summary>Uma fala na conversa: de = "eu" | "bella"; via = "voz" | "texto".</summary>
        public event Action<string,string,string,Opcao[]> Mensagem;
        /// <summary>Um aviso do sistema na conversa (erro = true pinta de vermelho).</summary>
        public event Action<string,bool> Aviso;
        /// <summary>Energia do microfone (RMS), ~14 vezes por segundo enquanto ele está aberto.</summary>
        public event Action<double> Nivel;
        public event Action<int?> BuscaMudou;
        public void CancelarBusca() { arquivos.CancelarBusca(); }

        public Nucleo(Control ui,Settings inicial,Func<IMicrophone> microphoneFactory=null) {
            dono=ui; Config=inicial ?? new Settings();
            criarMicrofone=microphoneFactory ?? (()=>new Microphone());
            if(Config.PastasArquivos==null) Config.PastasArquivos=Arquivos.PastasPadrao();
            if(Config.ComandosPastas==null) Config.ComandosPastas=new ComandoPasta[0];
            Config.WakePhrases=Chamadas.Validar(Config.WakePhrases ?? Chamadas.Padrao());
            try { ApertarParaFalar.Validar(Config.TalkKey,Config.TalkModifiers,Config.TalkSeconds); }
            catch { Config.TalkKey=119; Config.TalkModifiers=0; Config.TalkSeconds=5; }
            indicePastas=new IndicePastas(()=>IndicePastas.RaizesLocais());
            arquivos=new Arquivos(()=>Config.PastasArquivos,commands:()=>Config.ComandosPastas,folderIndex:indicePastas);
            programas=new Programas(()=>Config.ComandosPastas);
            arquivos.ProgressoBusca+=q=> { if(!quitting) Ui(()=> { if(!quitting && BuscaMudou!=null) BuscaMudou(q); }); };
        }

        void Ui(Action action) { if(!dono.IsDisposed && dono.IsHandleCreated) dono.BeginInvoke(action); }
        void Note(string text,bool erro=false) { if(Aviso!=null) Aviso(text,erro); }
        void Falou(string de,string texto,string via,Opcao[] opcoes) { if(Mensagem!=null) Mensagem(de,texto ?? "",via,opcoes); }
        void Mudou() { if(EstadoMudou!=null) EstadoMudou(); }

        // ── Acesso e preferências ─────────────────────────────────────
        public bool TemChave { get { return !String.IsNullOrEmpty(Config.Key); } }

        /// <summary>Salva servidor e chave. Chave vazia mantém a atual. Lança com a mensagem para o usuário.</summary>
        public void SalvarAcesso(string servidor,string chave) {
            var novo=Copia();
            if(!String.IsNullOrEmpty(servidor)) novo.Server=servidor.Trim().TrimEnd('/');
            if(!String.IsNullOrEmpty(chave)) novo.Key=chave.Trim();
            Settings.Validate(novo.Server,novo.Key);
            novo.Save(); Config=novo;
            AplicarInicioComWindows();
            if(capture!=null) capture.Threshold=Config.Threshold;
            greetings=null;                      // outra chave, outro catálogo de saudações
            arquivos.Cancelar();
            pedidos.Cancelar();
            if(listening && !Config.PushToTalk && !Config.FastWake) WarmGreetings(Config);
        }

        /// <summary>Preferências que mudam na hora (sem botão Salvar). Nulo = não mexe.</summary>
        public async Task Preferencias(bool? iniciar,bool? mini,int? sensibilidade,string aparencia,
            bool? apertar=null,int? tecla=null,int? modificadores=null,int? segundos=null,bool? rapida=null,bool? safada=null) {
            var novo=Copia();
            bool mudarFala=apertar.HasValue || tecla.HasValue || modificadores.HasValue || segundos.HasValue;
            if(mudarFala && (busy || starting)) throw new InvalidOperationException("Espere o pedido atual terminar antes de trocar o modo de fala.");
            if(apertar.HasValue) novo.PushToTalk=apertar.Value;
            if(rapida.HasValue) novo.FastWake=rapida.Value;
            if(safada.HasValue) {
                if(busy || starting) throw new InvalidOperationException("Espere o pedido atual terminar antes de trocar o modo de conversa.");
                novo.ModoSafada=safada.Value;
            }
            if(tecla.HasValue) novo.TalkKey=tecla.Value;
            if(modificadores.HasValue) novo.TalkModifiers=modificadores.Value;
            if(segundos.HasValue) novo.TalkSeconds=segundos.Value;
            ApertarParaFalar.Validar(novo.TalkKey,novo.TalkModifiers,novo.TalkSeconds);
            if(iniciar.HasValue) novo.Startup=iniciar.Value;
            if(mini.HasValue) novo.MiniBella=mini.Value;
            if(sensibilidade.HasValue) novo.Threshold=Math.Max(50,Math.Min(4000,sensibilidade.Value));
            if(aparencia=="foto" || aparencia=="orbe") novo.Aparencia=aparencia;
            if(TemChave) novo.Save();
            bool retomar=listening && mudarFala;
            if(mudarFala) { Pause(); capture=null; }
            Config=novo;
            if(capture!=null) capture.Threshold=Config.Threshold;
            if(TemChave && iniciar.HasValue) AplicarInicioComWindows();
            if(retomar) await StartListening();
            Mudou();
        }

        Settings Copia() {
            return new Settings { Server=Config.Server, Key=Config.Key, Startup=Config.Startup, Threshold=Config.Threshold,
                                  MiniBella=Config.MiniBella, Aparencia=Config.Aparencia, PastasArquivos=(string[])Config.PastasArquivos.Clone(),
                                  PushToTalk=Config.PushToTalk, TalkKey=Config.TalkKey, TalkModifiers=Config.TalkModifiers, TalkSeconds=Config.TalkSeconds,
                                  WakePhrases=(string[])Config.WakePhrases.Clone(),
                                  FastWake=Config.FastWake, ModoSafada=Config.ModoSafada,
                                  ComandosPastas=(ComandoPasta[])Config.ComandosPastas.Clone() };
        }

        public async Task SalvarChamadas(string[] frases) {
            if(busy || starting) throw new InvalidOperationException("Espere o pedido atual terminar antes de trocar as frases.");
            var validas=Chamadas.Validar(frases);
            LocalWake novoDetector=null;
            starting=true;
            try {
                novoDetector=await Task.Run(()=>new LocalWake(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"modelo"),validas));
                if(quitting) return;
                var novo=Copia(); novo.WakePhrases=validas;
                if(TemChave) novo.Save();
                bool retomar=listening;
                Pause(); capture=null;
                if(wake!=null) wake.Dispose();
                wake=novoDetector; novoDetector=null; Config=novo;
                starting=false;
                if(retomar) await StartListening();
                Mudou();
            } finally { starting=false; if(novoDetector!=null) novoDetector.Dispose(); }
        }

        public void ComandoPasta(string id,string frase,string caminho,bool remover,string tipo=null,string termo=null) {
            if(busy) throw new InvalidOperationException("Espere o pedido atual terminar antes de editar os comandos.");
            var novo=Copia(); novo.ComandosPastas=Bella.ComandosPastas.Atualizar(novo.ComandosPastas,id,frase,caminho,remover,tipo,termo);
            novo.Save(); Config=novo; arquivos.Cancelar(); pedidos.Cancelar();
        }

        public void Pastas(string adicionar,int? remover) {
            if(busy) throw new InvalidOperationException("Espere o pedido atual terminar antes de trocar as pastas.");
            var novo=Copia(); var lista=new System.Collections.Generic.List<string>(novo.PastasArquivos);
            if(remover.HasValue && remover.Value>=0 && remover.Value<lista.Count) lista.RemoveAt(remover.Value);
            if(!String.IsNullOrEmpty(adicionar)) {
                string p=Arquivos.Canonico(adicionar); Arquivos.ConferirAtalhos(p);
                if(!Directory.Exists(p)) throw new InvalidOperationException("Essa pasta não está disponível.");
                if(!lista.Exists(x=>String.Equals(x,p,StringComparison.OrdinalIgnoreCase))) lista.Add(p);
            }
            if(lista.Count>20) throw new InvalidOperationException("Escolha até 20 pastas principais.");
            novo.PastasArquivos=lista.ToArray(); novo.Save(); Config=novo; arquivos.Cancelar(); pedidos.Cancelar();
        }

        void AplicarInicioComWindows() {
            using(var reg=Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run")) {
                if(Config.Startup) reg.SetValue("SoloBella","\""+Application.ExecutablePath+"\" --minimized");
                else reg.DeleteValue("SoloBella",false);
            }
        }

        // ── Escuta ───────────────────────────────────────────────────
        public async Task StartListening() {
            if(starting || listening) return;
            starting=true;
            try {
                Settings.Validate(Config.Server,Config.Key);
                if(!Config.PushToTalk && wake==null)
                    wake=await Task.Run(()=>new LocalWake(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"modelo"),Config.WakePhrases));
                if(quitting) return;
                if(capture==null) {
                    var origem=new Capture(Config.PushToTalk ? null : wake) {PushToTalk=Config.PushToTalk};
                    capture=origem; capture.Changed+=mode=>Ui(Mudou);
                    capture.WakeDetected+=()=>Ui(async()=>await Greet());
                    capture.RequestReady+=audio=>Ui(async()=>{ if(capture==origem && origem.State==Capture.Mode.Processing && listening) await Send(null,audio); });
                }
                capture.Threshold=Config.Threshold; capture.Listen(); listening=true;
                if(!Config.PushToTalk) AbrirMicrofone();
                Mudou();
                if(!Config.PushToTalk && !Config.FastWake) WarmGreetings(Config);
            } catch(Exception e) { Pause(); Note("Não consegui ligar a escuta: "+e.Message,true); }
            finally { starting=false; }
        }

        void Medir(byte[] pcm) {
            // Roda na thread do microfone: só calcula e despacha de vez em quando.
            long agora=relogioNivel.ElapsedMilliseconds;
            if(agora-ultimoNivel<70 || Nivel==null) return;
            ultimoNivel=agora;
            double energia=Capture.Energy(pcm);
            Ui(()=>{ if(Nivel!=null) Nivel(energia); });
        }

        public void Pause() {
            listening=false; player.Stop(); if(capture!=null) capture.Pause();
            if(mic!=null) { try { mic.Dispose(); mic=null; } catch(Exception e) { Note(e.Message,true); } }
            Mudou();
        }

        public async Task AlternarEscuta() { if(listening) Pause(); else await StartListening(); }

        public async Task Begin() {
            if(Config.PushToTalk) { Note("Segure "+ApertarParaFalar.Nome(Config.TalkKey,Config.TalkModifiers)+" por "+Config.TalkSeconds+" segundos. Fale e solte para enviar."); return; }
            if(busy) { Note("Ainda estou cuidando do pedido anterior."); return; }
            player.Stop();
            if(!listening) await StartListening();
            if(listening) capture.Begin();
        }

        public void PararVoz() { player.Stop(); }

        void AbrirMicrofone() {
            var origem=capture;
            mic=criarMicrofone();
            mic.Start(pcm=>{ origem.Feed(pcm); Medir(pcm); },message=>Ui(()=>{ Pause(); Note(message,true); }));
        }
        void FecharMicrofone() {
            if(mic!=null) { mic.Dispose(); mic=null; }
        }
        public bool ComecarPorTecla() {
            if(quitting || starting || busy || !listening || !Config.PushToTalk || capture==null || !capture.BeginHeld()) return false;
            player.Stop();
            try { AbrirMicrofone(); Mudou(); return true; }
            catch(Exception e) { Pause(); Note("Não consegui abrir o microfone: "+e.Message,true); return false; }
        }
        public void SoltarTecla(bool cancelar=false) {
            if(!Config.PushToTalk || capture==null || capture.State!=Capture.Mode.Recording) return;
            try {
                FecharMicrofone();
                if(cancelar) capture.Listen(); else capture.EndHeld();
            } catch(Exception e) { Pause(); Note(e.Message,true); }
            Mudou();
        }

        // ── Saudações ────────────────────────────────────────────────
        GreetingLibrary GreetingsFor(Settings value) {
            string connection=value.Server+"\n"+value.Key;
            if(greetings==null || greetingConnection!=connection) {
                greetings=new GreetingLibrary(value); greetingConnection=connection;
            }
            return greetings;
        }
        async void WarmGreetings(Settings value) {
            try {
                var library=GreetingsFor(value);
                using(var client=new Client(value.Server,value.Key)) {
                    await library.Warm(client,()=>!quitting && listening && !Config.FastWake && greetingConnection==value.Server+"\n"+value.Key);
                }
            } catch(Exception) { /* A chamada usa o cache; falha de áudio é informada na tela. */ }
        }
        async Task Greet() {
            if(busy || !listening || capture.State!=Capture.Mode.Greeting) return;
            busy=true; Mudou();
            var tempo=Stopwatch.StartNew();
            try {
                if(Config.FastWake) return;
                try {
                    var value=Config; var library=GreetingsFor(value);
                    using(var client=new Client(value.Server,value.Key)) {
                        var reply=await library.Next(client);
                        if(!listening || quitting || capture.State!=Capture.Mode.Greeting) return;
                        Falou("bella",reply.texto,"voz",null);
                        await player.Say(reply);
                        WarmGreetings(value);
                    }
                }
                catch(UnauthorizedAccessException e) { Pause(); if(!quitting) Note(e.Message,true); }
                catch(OperationCanceledException) { }
                catch(Exception e) {
                    if(listening && !quitting) { Note("Voz ElevenLabs indisponível: "+e.Message+" Pode falar seu pedido.",true); }
                }
                await Task.Delay(180);
            } finally {
                // O detector ignora a saudação inteira; só depois captura o pedido.
                TempoChamada=tempo.ElapsedMilliseconds;
                busy=false;
                if(!quitting && listening) capture.RecordAfterGreeting();
                Mudou();
            }
        }

        // ── Pedidos ──────────────────────────────────────────────────
        public async Task SendText(string text,string exibir=null) {
            text=(text ?? "").Trim(); if(text.Length==0 || busy) return;
            await Send(text,null,exibir);
        }
        async Task Send(string text,byte[] audio,string exibir=null) {
            if(busy) return; busy=true; player.Stop();
            if(capture!=null) capture.Processing();
            if(text!=null) {
                if(text.StartsWith("/arquivos escolher ") || text.StartsWith("/solo-escolher ")) exibir=exibir ?? "Escolher opção";
                Falou("eu",exibir ?? text,"texto",null);
            }
            Mudou();
            try {
                var value=Config;
                var reply=await pedidos.Enviar(text,audio,arquivos,()=>new Client(value.Server,value.Key),
                    t=>Falou("eu",t ?? "pedido por voz","voz",null),()=>!quitting,
                    r=> { if(!quitting) Falou("bella",r.texto,audio!=null?"voz":"texto",r.opcoes); },programas,value.ModoSafada);
                if(!quitting) {
                    if(capture!=null) capture.Speaking();
                    Mudou();
                    await player.Say(reply);
                }
            } catch(OperationCanceledException) { }
            catch(UnauthorizedAccessException e) { if(!quitting) Note(e.Message,true); }
            catch(Exception e) { if(!quitting) Note(e.Message,true); }
            finally {
                busy=false;
                if(!quitting && BuscaMudou!=null) BuscaMudou(null);
                if(!quitting && capture!=null) { if(listening) capture.Listen(); else capture.Pause(); }
                if(!quitting) Mudou();
            }
        }

        public void Encerrar() { quitting=true; indicePastas.Dispose(); arquivos.Cancelar(); pedidos.Cancelar(); Pause(); }
        public void Dispose() {
            quitting=true;
            if(mic!=null) { try { mic.Dispose(); } catch { } mic=null; }
            if(wake!=null) { wake.Dispose(); wake=null; }
            indicePastas.Dispose();
            player.Dispose();
        }
    }
}
