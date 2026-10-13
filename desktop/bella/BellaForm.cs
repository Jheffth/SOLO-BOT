using System;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

namespace Bella {
    public sealed class BellaForm : Form {
        [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr h,int id,uint modifiers,uint key);
        [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr h,int id);
        readonly Settings settings;
        readonly TextBox server=new TextBox(), key=new TextBox(), input=new TextBox();
        readonly TextBox conversation=new TextBox { Multiline=true, ScrollBars=ScrollBars.Vertical };
        readonly CheckBox startup=new CheckBox();
        readonly NumericUpDown threshold=new NumericUpDown();
        readonly Label status=new Label();
        readonly Button listen=new Button(), talk=new Button(), send=new Button();
        readonly NotifyIcon tray=new NotifyIcon();
        readonly Playback player=new Playback();
        LocalWake wake;
        Capture capture;
        Microphone mic;
        GreetingLibrary greetings;
        string greetingConnection;
        bool listening, starting, busy, quitting;
        readonly bool preview;
        readonly Color surface=Color.FromArgb(27,29,43), ink=Color.FromArgb(232,234,245), accent=Color.FromArgb(170,150,245);
        public BellaForm(bool minimized,bool isPreview) {
            preview=isPreview; settings=preview?new Settings():Settings.Load();
            Text="Bella · Solo"; BackColor=Color.FromArgb(17,19,30); ForeColor=ink;
            Font=new Font("Segoe UI",10); Size=new Size(650,790); MinimumSize=new Size(540,660);
            StartPosition=FormStartPosition.CenterScreen; AutoScaleMode=AutoScaleMode.Dpi;
            Icon=SystemIcons.Information;
            var layout=new TableLayoutPanel { Dock=DockStyle.Fill, Padding=new Padding(22), ColumnCount=1, RowCount=8 };
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,65));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,192));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,48));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,45));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,46));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,35));
            Controls.Add(layout);
            layout.Controls.Add(new Label { Text="Bella", Font=new Font("Segoe UI",27,FontStyle.Bold), ForeColor=accent, Dock=DockStyle.Fill },0,0);
            var setup=new TableLayoutPanel { Dock=DockStyle.Fill, ColumnCount=2, RowCount=5 };
            setup.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,130)); setup.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            AddField(setup,"Servidor",server,0); AddField(setup,"Chave da Bella",key,1);
            key.UseSystemPasswordChar=true; server.Text=settings.Server; key.Text=settings.Key;
            startup.Text="Iniciar com Windows"; startup.Checked=settings.Startup; startup.AutoSize=true;
            setup.Controls.Add(startup,1,2);
            threshold.Minimum=50; threshold.Maximum=4000; threshold.Value=Math.Max(50,Math.Min(4000,settings.Threshold));
            threshold.BackColor=surface; threshold.ForeColor=ink;
            threshold.Dock=DockStyle.Fill; setup.Controls.Add(new Label { Text="Sensibilidade", AutoSize=true },0,3); setup.Controls.Add(threshold,1,3);
            var actions=new FlowLayoutPanel { Dock=DockStyle.Fill };
            var save=Button("Salvar acesso",()=>Save());
            var panel=Button("Abrir painel",()=>OpenPanel()); actions.Controls.Add(save); actions.Controls.Add(panel);
            setup.Controls.Add(actions,1,4); layout.Controls.Add(setup,0,1);
            status.Text="Escuta pausada · microfone desligado"; status.ForeColor=accent; status.Dock=DockStyle.Fill; status.TextAlign=ContentAlignment.MiddleLeft;
            layout.Controls.Add(status,0,2);
            var control=new FlowLayoutPanel { Dock=DockStyle.Fill };
            Style(listen,"Ativar escuta"); listen.Click+=async(s,e)=>{ if(listening) Pause(); else await StartListening(); };
            Style(talk,"Falar agora"); talk.Click+=async(s,e)=>await Begin();
            var stop=Button("Interromper voz",()=>player.Stop());
            control.Controls.Add(listen); control.Controls.Add(talk); control.Controls.Add(stop); layout.Controls.Add(control,0,3);
            conversation.Dock=DockStyle.Fill; conversation.ReadOnly=true; conversation.BackColor=surface; conversation.ForeColor=ink;
            conversation.BorderStyle=BorderStyle.FixedSingle;
            conversation.Text="Olá, sou a Bella.\n\nGere sua chave na seção Bella do painel, cole acima e salve.\n\nAtive a escuta e diga ‘Bella’. Vou responder à chamada. Depois da saudação, faça o pedido.\n\nTenho 20 saudações com seu login. Guardo os áudios de cada voz para reutilizar.\n\nCtrl + Alt + B também me chama.\n\nAo fechar esta janela, continuo perto do relógio. Pelo ícone você pode pausar ou sair.\n".Replace("\n",Environment.NewLine);
            layout.Controls.Add(conversation,0,4);
            input.Dock=DockStyle.Fill; input.BackColor=surface; input.ForeColor=ink;
            input.KeyDown+=async(s,e)=>{ if(e.KeyCode==Keys.Enter) { e.SuppressKeyPress=true; await SendText(); } };
            layout.Controls.Add(input,0,5);
            Style(send,"Enviar texto"); send.Click+=async(s,e)=>await SendText(); layout.Controls.Add(send,0,6);
            layout.Controls.Add(new Label { Text="Pedidos ativados vão ao Solo Bot. O áudio de espera fica local.", ForeColor=Color.FromArgb(159,163,188), Dock=DockStyle.Fill, Font=new Font("Segoe UI",9) },0,7);
            tray.Icon=Icon; tray.Text="Bella · escuta pausada"; tray.Visible=!preview;
            var menu=new ContextMenuStrip(); menu.Items.Add("Abrir Bella",null,(s,e)=>Reveal());
            menu.Items.Add("Falar agora",null,async(s,e)=>await Begin());
            menu.Items.Add("Pausar escuta",null,(s,e)=>Pause()); menu.Items.Add("Sair",null,(s,e)=>Exit());
            tray.ContextMenuStrip=menu; tray.DoubleClick+=(s,e)=>Reveal();
            FormClosing+=(s,e)=>{ if(!quitting) { e.Cancel=true; Hide(); if(!preview) tray.ShowBalloonTip(1500,"Bella","Estou perto do relógio. Use o ícone para abrir ou sair.",ToolTipIcon.Info); } };
            Shown+=async(s,e)=>{ if(minimized && !preview) { Hide(); if(!String.IsNullOrEmpty(settings.Key)) await StartListening(); } };
        }
        void AddField(TableLayoutPanel p,string text,TextBox box,int row) {
            p.Controls.Add(new Label { Text=text, Dock=DockStyle.Fill, TextAlign=ContentAlignment.MiddleLeft },0,row);
            box.Dock=DockStyle.Fill; box.BackColor=surface; box.ForeColor=ink; p.Controls.Add(box,1,row);
        }
        void Style(Button b,string text) { b.Text=text; b.AutoSize=true; b.Padding=new Padding(9,5,9,5); b.FlatStyle=FlatStyle.Flat; b.BackColor=surface; b.ForeColor=ink; }
        Button Button(string text,Action action) { var b=new Button(); Style(b,text); b.Click+=(s,e)=>action(); return b; }
        void Ui(Action action) { if(!IsDisposed && IsHandleCreated) BeginInvoke(action); }
        void Note(string text) { conversation.AppendText(Environment.NewLine+text.Replace("\r\n","\n").Replace("\n",Environment.NewLine)+Environment.NewLine); conversation.SelectionStart=conversation.TextLength; conversation.ScrollToCaret(); }
        Settings Current() { return new Settings { Server=server.Text.Trim().TrimEnd('/'), Key=key.Text.Trim(), Startup=startup.Checked, Threshold=(int)threshold.Value }; }
        void Save() {
            try {
                var value=Current(); value.Save();
                using(var reg=Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run")) {
                    if(value.Startup) reg.SetValue("SoloBella","\""+Application.ExecutablePath+"\" --minimized"); else reg.DeleteValue("SoloBella",false);
                }
                if(capture!=null) capture.Threshold=value.Threshold;
                Note("Acesso salvo neste usuário do Windows.");
                if(listening) WarmGreetings(value);
            } catch(Exception e) { Note(e.Message); }
        }
        void OpenPanel() {
            try { var uri=new Uri(server.Text.Trim()); if(uri.Scheme!="https") throw new Exception("Use o endereço HTTPS do painel."); System.Diagnostics.Process.Start(uri.GetLeftPart(UriPartial.Authority)+"/painel"); }
            catch(Exception e) { Note(e.Message); }
        }
        public void Reveal() { Show(); WindowState=FormWindowState.Normal; Activate(); }
        async Task StartListening() {
            if(starting || listening || preview) return;
            starting=true; status.Text="Preparando a escuta local…";
            try {
                var value=Current(); Settings.Validate(value.Server,value.Key);
                if(wake==null) {
                    wake=await Task.Run(()=>new LocalWake(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"modelo")));
                    capture=new Capture(wake); capture.Changed+=mode=>Ui(()=>ShowMode(mode));
                    capture.WakeDetected+=()=>Ui(async()=>await Greet());
                    capture.RequestReady+=audio=>Ui(async()=>{ if(capture.State==global::Bella.Capture.Mode.Processing && listening) await Send(null,audio); });
                }
                capture.Threshold=value.Threshold; capture.Listen(); listening=true;
                mic=new Microphone(); mic.Start(capture.Feed,message=>Ui(()=>{ Pause(); Note(message); }));
                listen.Text="Pausar escuta"; ShowMode(global::Bella.Capture.Mode.Listening);
                WarmGreetings(value);
            } catch(Exception e) { Pause(); Note("Não consegui iniciar: "+e.Message); }
            finally { starting=false; }
        }
        void ShowMode(global::Bella.Capture.Mode mode) {
            string text=mode==global::Bella.Capture.Mode.Listening?"Aguardando ‘Bella’ · escuta local":mode==global::Bella.Capture.Mode.Greeting?"Respondendo à sua chamada…":mode==global::Bella.Capture.Mode.Recording?"Pode falar · paro após uma pausa":mode==global::Bella.Capture.Mode.Processing?"Processando seu pedido…":mode==global::Bella.Capture.Mode.Speaking?"Respondendo · microfone não envia áudio":"Escuta pausada · microfone desligado";
            status.Text=text; tray.Text=("Bella · "+text).Substring(0,Math.Min(63,("Bella · "+text).Length));
            if(mode==global::Bella.Capture.Mode.Recording && !preview) {
                if(!Visible) tray.ShowBalloonTip(1200,"Bella","Pode falar seu pedido.",ToolTipIcon.Info);
            }
            send.Enabled=!busy; talk.Enabled=!busy;
        }
        void Pause() {
            listening=false; player.Stop(); if(capture!=null) capture.Pause();
            if(mic!=null) { try { mic.Dispose(); mic=null; } catch(Exception e) { Note(e.Message); } }
            listen.Text="Ativar escuta"; ShowMode(global::Bella.Capture.Mode.Paused);
        }
        async Task Begin() {
            if(busy) { Note("O pedido anterior ainda está sendo processado."); return; }
            player.Stop();
            if(!listening) await StartListening();
            if(listening) capture.Begin();
        }
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
                    await library.Warm(client,()=>!quitting && listening && greetingConnection==value.Server+"\n"+value.Key);
                }
            } catch(Exception) { /* A chamada usa o cache ou a voz do Windows se a preparação falhar. */ }
        }
        async Task Greet() {
            if(busy || !listening || capture.State!=global::Bella.Capture.Mode.Greeting) return;
            busy=true; ShowMode(global::Bella.Capture.Mode.Greeting);
            try {
                bool fallback=false;
                try {
                    var value=Current(); var library=GreetingsFor(value);
                    using(var client=new Client(value.Server,value.Key)) {
                        var reply=await library.Next(client);
                        if(!listening || quitting || capture.State!=global::Bella.Capture.Mode.Greeting) return;
                        Note("Bella: "+reply.texto);
                        await player.Say(reply);
                        WarmGreetings(value);
                    }
                }
                catch(UnauthorizedAccessException e) { Pause(); if(!quitting) Note(e.Message); }
                catch(OperationCanceledException) { }
                catch(Exception e) {
                    if(listening && !quitting) { Note("Não consegui buscar a saudação: "+e.Message); fallback=true; }
                }
                if(fallback) {
                    try { await player.Say(new Reply { falar="Estou aqui. Pode falar." }); } catch(OperationCanceledException) { }
                    catch(Exception e) { if(!quitting) Note("Não consegui reproduzir a voz: "+e.Message); }
                }
                await Task.Delay(180);
            } finally {
                // O detector ignora a saudação inteira; só depois captura o pedido.
                busy=false;
                if(!quitting && listening) { capture.RecordAfterGreeting(); ShowMode(capture.State); }
            }
        }
        async Task SendText() {
            var text=input.Text.Trim(); if(text.Length==0 || busy) return;
            input.Clear(); await Send(text,null);
        }
        async Task Send(string text,byte[] audio) {
            if(busy) return; busy=true; player.Stop();
            if(capture!=null) capture.Processing(); ShowMode(global::Bella.Capture.Mode.Processing);
            try {
                var value=Current();
                using(var client=new Client(value.Server,value.Key)) {
                    var reply=await client.Send(text,audio);
                    Note("Você: "+(reply.ouvido ?? text ?? "pedido por voz")); Note("Bella: "+reply.texto);
                    if(!quitting) {
                        if(capture!=null) capture.Speaking(); ShowMode(global::Bella.Capture.Mode.Speaking);
                        await player.Say(reply);
                    }
                }
            } catch(OperationCanceledException) { }
            catch(Exception e) { if(!quitting) Note(e.Message); }
            finally {
                busy=false;
                if(!quitting) { if(capture!=null) { if(listening) capture.Listen(); else capture.Pause(); } ShowMode(listening?global::Bella.Capture.Mode.Listening:global::Bella.Capture.Mode.Paused); }
            }
        }
        protected override void OnHandleCreated(EventArgs e) {
            base.OnHandleCreated(e);
            if(!preview && !RegisterHotKey(Handle,1,0x4000|0x0002|0x0001,(uint)Keys.B)) Note("Ctrl + Alt + B está em uso por outro aplicativo. Use Falar agora.");
        }
        protected override void WndProc(ref Message m) { if(m.Msg==0x0312 && m.WParam.ToInt32()==1) { BeginFromHotkey(); } base.WndProc(ref m); }
        async void BeginFromHotkey() { await Begin(); }
        public void Exit() { quitting=true; Pause(); tray.Visible=false; Close(); }
        protected override void Dispose(bool disposing) {
            if(disposing) { UnregisterHotKey(Handle,1); if(mic!=null) mic.Dispose(); if(wake!=null) wake.Dispose(); player.Dispose(); tray.Dispose(); }
            base.Dispose(disposing);
        }
    }
}
