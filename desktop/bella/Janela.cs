using System;
using System.Collections.Generic;
using System.Drawing;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Modo = Bella.Capture.Mode;

namespace Bella {
    // A JANELA DA BELLA: a tela em HTML (ui/index.html) + o ícone perto do relógio
    // + o atalho Ctrl+Alt+B + a Mini-Bella. A lógica toda está no Nucleo.
    public sealed class Janela : Form {
        [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr h,int id,uint modifiers,uint key);
        [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr h,int id);
        [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
        [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();

        readonly WebView2 web=new WebView2();
        readonly Vista tela;
        readonly Nucleo bella;
        readonly NotifyIcon tray=new NotifyIcon();
        readonly ToolStripMenuItem itemEscuta;
        readonly Timer esconderMini=new Timer { Interval=5000 };
        readonly Timer teclaFalar=new Timer { Interval=20 };
        readonly EsperaTecla esperaTecla=new EsperaTecla();
        readonly Stopwatch tempoTecla=Stopwatch.StartNew();
        readonly string pastaUi=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"ui");
        readonly bool minimized;
        CoreWebView2Environment ambiente;
        MiniBella mini;
        string foto;
        bool quitting, medidor, avisouBandeja, atalhoLivre=true;

        public Janela(bool startMinimized) {
            minimized=startMinimized;
            Text="Bella"; BackColor=Visual.Fundo; ForeColor=Color.White;
            Size=Visual.Medida(480,820); MinimumSize=Visual.Medida(380,560);
            StartPosition=FormStartPosition.CenterScreen; AutoScaleMode=AutoScaleMode.None;
            Icon=Visual.Icone(null);
            if(minimized) Opacity=0;
            web.Dock=DockStyle.Fill; web.DefaultBackgroundColor=Visual.Fundo; Controls.Add(web);
            tela=new Vista(web);
            tela.Recebeu+=Receber;

            bella=new Nucleo(this,Settings.Load());
            foto=Foto.Recorte();
            bella.EstadoMudou+=AoMudar;
            bella.Mensagem+=(de,texto,via,opcoes)=>{
                var m=new { tipo="msg", de=de, texto=texto, via=via, opcoes=opcoes ?? new Opcao[0] };
                tela.Postar(m); if(mini!=null) mini.Postar(m);
            };
            bella.Aviso+=(texto,erro)=>tela.Postar(new { tipo="aviso", texto=texto, erro=erro });
            bella.Nivel+=energia=>{
                var m=new { tipo="nivel", v=energia, limiar=bella.Config.Threshold };
                if(Visible && (medidor || bella.Modo==Modo.Recording)) tela.Postar(m);
                if(mini!=null && mini.Visible && bella.Modo==Modo.Recording) mini.Postar(m);
            };

            // Ícone perto do relógio
            var menu=new ContextMenuStrip { Renderer=Visual.MenuEscuro(), ShowImageMargin=false, Font=new Font("Segoe UI",9.5f) };
            menu.Items.Add("Abrir Bella",null,(s,e)=>Reveal());
            menu.Items.Add("Falar agora",null,async(s,e)=>await Seguro(bella.Begin));
            itemEscuta=new ToolStripMenuItem("Pausar escuta",null,async(s,e)=>await Seguro(bella.AlternarEscuta));
            menu.Items.Add(itemEscuta);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Sair",null,(s,e)=>Sair());
            tray.ContextMenuStrip=menu; tray.DoubleClick+=(s,e)=>Reveal();
            tray.Icon=Visual.Icone(Modo.Paused,SystemInformation.SmallIconSize.Width*2);
            tray.Text="Bella · escuta pausada"; tray.Visible=true;

            esconderMini.Tick+=(s,e)=>{ esconderMini.Stop(); if(mini!=null) mini.Hide(); };
            teclaFalar.Tick+=(s,e)=>ObservarTecla();
            if(IsHandleCreated) AtualizarAtalho();
            FormClosing+=(s,e)=>{
                if(quitting) return;
                e.Cancel=true; Hide();
                if(!avisouBandeja) { avisouBandeja=true; tray.ShowBalloonTip(1500,"Bella",bella.Config.PushToTalk
                    ? "Continuo perto do relógio. Segure "+ApertarParaFalar.Nome(bella.Config.TalkKey,bella.Config.TalkModifiers)+" para falar."
                    : "Continuo aqui perto do relógio. Diga “"+bella.Config.WakePhrases[0]+"” quando precisar.",ToolTipIcon.None); }
            };
            VisibleChanged+=(s,e)=>AtualizarMini();
            Resize+=(s,e)=>AtualizarMini();
            Shown+=async(s,e)=>await Abrir();
        }

        protected override void OnHandleCreated(EventArgs e) {
            base.OnHandleCreated(e);
            Visual.JanelaEscura(this);
            AtualizarAtalho();
        }
        protected override void WndProc(ref Message m) {
            if(m.Msg==0x0312 && m.WParam.ToInt32()==1) PeloAtalho();
            base.WndProc(ref m);
        }
        async void PeloAtalho() { await Seguro(bella.Begin); }
        void AtualizarAtalho() {
            if(bella==null || !IsHandleCreated) return;
            teclaFalar.Enabled=bella.Config.PushToTalk;
            UnregisterHotKey(Handle,1);
            atalhoLivre=bella.Config.PushToTalk || RegisterHotKey(Handle,1,0x4000|0x0002|0x0001,(uint)Keys.B);
            esperaTecla.Reiniciar();
        }
        static bool TeclaAbaixada(int tecla) { return GetAsyncKeyState(tecla)<0; }
        void ObservarTecla() {
            if(quitting) return;
            var c=bella.Config;
            bool habilitada=c.PushToTalk && bella.Escutando && !bella.Ocupada && !medidor && GetForegroundWindow()!=IntPtr.Zero;
            bool pressionada=false;
            if(habilitada) {
                int modificadores=(TeclaAbaixada(18)?1:0)|(TeclaAbaixada(17)?2:0)|(TeclaAbaixada(16)?4:0);
                pressionada=TeclaAbaixada(c.TalkKey) && modificadores==c.TalkModifiers
                    && !TeclaAbaixada(91) && !TeclaAbaixada(92);
            }
            int anterior=esperaTecla.Restantes; bool contando=esperaTecla.Contando;
            var acao=esperaTecla.Atualizar(habilitada,pressionada,tempoTecla.Elapsed.TotalMilliseconds,c.TalkSeconds);
            if(acao==AcaoTecla.Comecar && !bella.ComecarPorTecla()) esperaTecla.Reiniciar();
            if(acao==AcaoTecla.Enviar) bella.SoltarTecla();
            if(acao==AcaoTecla.Cancelar) bella.SoltarTecla(true);
            if(anterior!=esperaTecla.Restantes || contando!=esperaTecla.Contando || acao!=AcaoTecla.Nenhuma) AoMudar();
        }

        async Task Abrir() {
            if(minimized) { Hide(); Opacity=1; }
            try {
                ambiente=await CoreWebView2Environment.CreateAsync(null,Path.Combine(Foto.Pasta,"WebView2"));
                await tela.Iniciar(ambiente,pastaUi,"index.html");
            } catch(Exception e) {
                MessageBox.Show("Não consegui abrir a tela da Bella: "+e.Message+"\n\nConfira se a pasta “ui” está ao lado do Bella.exe e se o Microsoft Edge WebView2 está instalado.",
                    "Bella",MessageBoxButtons.OK,MessageBoxIcon.Warning);
                Sair(); return;
            }
            if(!atalhoLivre) tela.Postar(new { tipo="aviso", texto="Ctrl + Alt + B está em uso por outro aplicativo. Use o botão do microfone.", erro=false });
            if(bella.TemChave) await Seguro(bella.StartListening);   // com a chave salva, ela já abre ouvindo
        }

        // ── Da tela para o núcleo ─────────────────────────────────────
        async void Receber(Dictionary<string,object> d) {
            try {
                switch(Vista.Texto(d,"acao")) {
                    case "pronto": PostarConfig(); AoMudar(); break;
                    case "escuta": await bella.AlternarEscuta(); break;
                    case "falar": await bella.Begin(); break;
                    case "parar_voz": bella.PararVoz(); break;
                    case "enviar": await bella.SendText(Vista.Texto(d,"texto"),Vista.Texto(d,"exibir")); break;
                    case "medidor": medidor=Vista.Logico(d,"ligado")==true; break;
                    case "abrir_painel": AbrirPainel(Vista.Texto(d,"servidor")); break;
                    case "sair": Sair(); break;
                    case "comando_pasta":
                        try {
                            bella.ComandoPasta(Vista.Texto(d,"id"),Vista.Texto(d,"frase"),Vista.Texto(d,"caminho"),Vista.Logico(d,"remover")==true,Vista.Texto(d,"tipo"),Vista.Texto(d,"termo"));
                            PostarConfig(); tela.Postar(new {tipo="comando_salvo", removido=Vista.Logico(d,"remover")==true});
                        } catch(Exception e) { tela.Postar(new {tipo="toast",texto=e.Message,erro=true}); }
                        break;
                    case "comando_escolher_pasta":
                        using(var pastaComando=new FolderBrowserDialog {Description="Escolha a pasta para este comando abrir.",ShowNewFolderButton=false}) {
                            if(pastaComando.ShowDialog(this)==DialogResult.OK) tela.Postar(new {tipo="comando_caminho",caminho=pastaComando.SelectedPath});
                        }
                        break;
                    case "pasta_arquivos":
                        if(bella.Ocupada) throw new InvalidOperationException("Espere o pedido atual terminar.");
                        var remover=Vista.Inteiro(d,"remover");
                        if(remover.HasValue) bella.Pastas(null,remover);
                        else using(var escolha=new FolderBrowserDialog { Description="Escolha uma pasta que a Bella pode usar.", ShowNewFolderButton=true }) {
                            if(escolha.ShowDialog(this)==DialogResult.OK) bella.Pastas(escolha.SelectedPath,null);
                        }
                        PostarConfig(); break;
                    case "salvar":
                        try { bella.SalvarAcesso(Vista.Texto(d,"servidor"),Vista.Texto(d,"chave")); }
                        catch(Exception e) { tela.Postar(new { tipo="erro_salvar", texto=e.Message }); break; }
                        PostarConfig();
                        tela.Postar(new { tipo="salvo", texto="Acesso salvo neste usuário do Windows." });
                        if(!bella.Escutando) await bella.StartListening();
                        break;
                    case "chamadas":
                        try {
                            await bella.SalvarChamadas(Vista.Textos(d,"frases"));
                            tela.Postar(new {tipo="toast",texto="Frases de ativação salvas neste computador.",erro=false});
                        } catch(Exception e) { tela.Postar(new {tipo="toast",texto=e.Message,erro=true}); }
                        PostarConfig(); AoMudar();
                        break;
                    case "preferencias":
                        try {
                            await bella.Preferencias(Vista.Logico(d,"iniciar"),Vista.Logico(d,"mini"),Vista.Inteiro(d,"sensibilidade"),Vista.Texto(d,"aparencia"),
                                Vista.Logico(d,"apertarParaFalar"),Vista.Inteiro(d,"teclaFalar"),Vista.Inteiro(d,"modificadoresFalar"),Vista.Inteiro(d,"esperaFalar"));
                            if(d.ContainsKey("apertarParaFalar") || d.ContainsKey("teclaFalar") || d.ContainsKey("esperaFalar") || d.ContainsKey("modificadoresFalar")) AtualizarAtalho();
                        } catch(Exception e) { tela.Postar(new {tipo="toast",texto=e.Message,erro=true}); }
                        PostarConfig(); AtualizarMini();
                        break;
                    case "foto":
                        try {
                            var url=Vista.Texto(d,"dataUrl");
                            if(url==null) Foto.Remover(); else Foto.Salvar(url,Vista.Texto(d,"original"));
                            foto=Foto.Recorte();
                            PostarConfig();
                            tela.Postar(new { tipo="toast", texto=url==null?"Foto removida. Voltei ao orbe.":"Foto da Bella atualizada.", erro=false });
                        } catch(Exception e) { tela.Postar(new { tipo="toast", texto=e.Message, erro=true }); }
                        break;
                    case "foto_original":
                        tela.Postar(new { tipo="foto_original", dataUrl=Foto.Original() ?? foto });
                        break;
                }
            } catch(Exception e) { tela.Postar(new { tipo="aviso", texto=e.Message, erro=true }); }
        }

        async Task Seguro(Func<Task> acao) {
            try { await acao(); } catch(Exception e) { tela.Postar(new { tipo="aviso", texto=e.Message, erro=true }); }
        }

        // ── Do núcleo para a tela ─────────────────────────────────────
        object Config() {
            var c=bella.Config;
            string final=String.IsNullOrEmpty(c.Key) || c.Key.Length<4 ? "" : c.Key.Substring(c.Key.Length-4);
            return new { tipo="config", temChave=bella.TemChave, servidor=c.Server, chaveFinal=final, iniciar=c.Startup,
                         apertarParaFalar=c.PushToTalk, teclaFalar=c.TalkKey, modificadoresFalar=c.TalkModifiers, esperaFalar=c.TalkSeconds,
                         frasesAtivacao=c.WakePhrases,
                         nomeTeclaFalar=ApertarParaFalar.Nome(c.TalkKey,c.TalkModifiers),
                         mini=c.MiniBella, sensibilidade=c.Threshold, aparencia=c.Aparencia ?? "foto", foto=foto, pastasArquivos=c.PastasArquivos,
                         comandosPastas=c.ComandosPastas, modelosComandos=Navegador.Modelos() };
        }
        void PostarConfig() { var c=Config(); tela.Postar(c); if(mini!=null) mini.Postar(c); }

        static string NomeDoModo(Modo modo) {
            switch(modo) {
                case Modo.Listening: return "espera";
                case Modo.Greeting: return "saudando";
                case Modo.Recording: return "ouvindo";
                case Modo.Processing: return "pensando";
                case Modo.Speaking: return "falando";
                default: return "pausada";
            }
        }
        static readonly Dictionary<Modo,string> Dica=new Dictionary<Modo,string> {
            { Modo.Paused, "escuta pausada" }, { Modo.Listening, "esperando chamada" },
            { Modo.Greeting, "respondendo à chamada" }, { Modo.Recording, "pode falar" },
            { Modo.Processing, "pensando" }, { Modo.Speaking, "respondendo" }
        };

        void AoMudar() {
            var modo=bella.Modo;
            if(!bella.Escutando && modo==Modo.Listening) modo=Modo.Paused;
            var m=new { tipo="estado", modo=NomeDoModo(modo), escutando=bella.Escutando, ocupada=bella.Ocupada,
                        segurando=esperaTecla.Contando, restante=esperaTecla.Restantes };
            tela.Postar(m); if(mini!=null) mini.Postar(m);
            tray.Icon=Visual.Icone(modo,SystemInformation.SmallIconSize.Width*2);
            var dica="Bella · "+(bella.Escutando && modo==Modo.Listening ? (bella.Config.PushToTalk ? "segure "+ApertarParaFalar.Nome(bella.Config.TalkKey,bella.Config.TalkModifiers) : "diga “"+bella.Config.WakePhrases[0]+"”") : Dica[modo]); tray.Text=dica.Length>63?dica.Substring(0,63):dica;
            itemEscuta.Text=bella.Escutando?"Pausar escuta":"Ligar escuta";
            AtualizarMini();
        }

        // ── Mini-Bella: aparece quando a janela está fechada e ela está em ação ──
        void AtualizarMini() {
            if(quitting || ambiente==null) return;
            bool fora=!Visible || WindowState==FormWindowState.Minimized;
            var modo=bella.Modo;
            bool emAcao=esperaTecla.Contando || modo==Modo.Greeting || modo==Modo.Recording || modo==Modo.Processing || modo==Modo.Speaking;
            if(!fora || !bella.Config.MiniBella) { esconderMini.Stop(); if(mini!=null) mini.Hide(); return; }
            if(emAcao) {
                esconderMini.Stop();
                if(mini==null) {
                    mini=new MiniBella(ambiente,pastaUi);
                    mini.Abrir+=Reveal;
                    mini.Pronta+=()=>{ mini.Postar(Config()); AoMudar(); };
                }
                mini.Mostrar();
            } else if(mini!=null && mini.Visible && !esconderMini.Enabled) esconderMini.Start();
        }

        public void Reveal() {
            Show(); if(WindowState==FormWindowState.Minimized) WindowState=FormWindowState.Normal;
            Activate(); if(mini!=null) mini.Hide();
        }

        void AbrirPainel(string servidor) {
            try {
                var uri=new Uri(String.IsNullOrEmpty(servidor)?bella.Config.Server:servidor);
                if(uri.Scheme!="https") throw new InvalidOperationException("Use o endereço HTTPS do painel.");
                System.Diagnostics.Process.Start(uri.GetLeftPart(UriPartial.Authority)+"/painel");
            } catch(Exception e) { tela.Postar(new { tipo="toast", texto=e.Message, erro=true }); }
        }

        public void Sair() {
            if(quitting) return;
            quitting=true; teclaFalar.Stop(); bella.Encerrar(); tray.Visible=false;
            if(mini!=null) mini.Close();
            Close();
        }

        protected override void Dispose(bool disposing) {
            if(disposing) {
                if(IsHandleCreated) UnregisterHotKey(Handle,1);
                teclaFalar.Dispose(); bella.Dispose(); tray.Dispose(); esconderMini.Dispose();
                if(mini!=null) mini.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
