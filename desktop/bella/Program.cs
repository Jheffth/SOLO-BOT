using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

namespace Bella {
    static class Program {
        [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
        const string BaixarWebView2="https://go.microsoft.com/fwlink/p/?LinkId=2124703";

        [STAThread] static int Main(string[] args) {
            ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
            if(args.Contains("--anexo-self-test")) {
                try { AnexoTestes.Run(); File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"anexo-self-test.txt"),"OK"); return 0; }
                catch(Exception e) { File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"anexo-self-test.txt"),e.ToString()); return 1; }
            }
            if(args.Contains("--avatar-self-test")) {
                try { AvatarTestes.Run(Path.GetTempPath()); File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"avatar-self-test.txt"),"OK"); return 0; }
                catch(Exception e) { File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"avatar-self-test.txt"),e.ToString()); return 1; }
            }
            if(args.Contains("--voice-self-test")) {
                try { VozRedeTestes.Run(); PastasTestes.Run(AppDomain.CurrentDomain.BaseDirectory); ArquivosLivresTestes.Run(AppDomain.CurrentDomain.BaseDirectory); ProgramasTestes.Run(); ImagensTestes.Run(AppDomain.CurrentDomain.BaseDirectory); ArquivosTestes.Run(AppDomain.CurrentDomain.BaseDirectory); NavegadorTestes.Run(); File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"voice-self-test.txt"),"OK"); return 0; }
                catch(Exception e) { File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"voice-self-test.txt"),e.ToString()); return 1; }
            }
            if(args.Contains("--word-self-test")) {
                try {ProgramasTestes.WordReal(); File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"word-self-test.txt"),"OK"); return 0;}
                catch(Exception e) {File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"word-self-test.txt"),e.ToString()); return 1;}
            }
            if(args.Contains("--self-test")) {
                try { SelfTest.Run(); File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"self-test.txt"),"OK"); return 0; }
                catch(Exception e) { File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"self-test.txt"),e.ToString()); return 1; }
            }
            // Nítida em telas com 125%/150%: o próprio app cuida da escala (Visual.Escala).
            try { SetProcessDPIAware(); } catch { }
            bool created;
            using(var instance=new Mutex(true,@"Local\SoloBellaDesktop",out created)) {
                if(!created) { MessageBox.Show("A Bella já está perto do relógio. Abra pelo ícone.","Bella"); return 0; }
                Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                if(!TemWebView2()) return 1;
                try {
                    Application.Run(new Janela(args.Contains("--minimized")));
                } catch(Exception e) { MessageBox.Show("Não consegui abrir a Bella: "+e.Message,"Bella"); return 1; }
            }
            return 0;
        }

        // A tela da Bella é desenhada pelo Microsoft Edge WebView2. Ele já vem no Windows 11 e
        // na maioria dos Windows 10; se faltar, mostramos de onde baixar (página oficial da Microsoft).
        static bool TemWebView2() {
            string versao=null;
            try { versao=CoreWebView2Environment.GetAvailableBrowserVersionString(); }
            catch(WebView2RuntimeNotFoundException) { versao=null; }
            catch(DllNotFoundException) {
                MessageBox.Show("Faltam arquivos da Bella (WebView2Loader.dll). Extraia o ZIP inteiro numa pasta e abra o Bella.exe de lá.","Bella",MessageBoxButtons.OK,MessageBoxIcon.Warning);
                return false;
            }
            catch(Exception) { versao=null; }
            if(!String.IsNullOrEmpty(versao)) return true;
            var r=MessageBox.Show("A Bella usa o Microsoft Edge WebView2 para desenhar a tela, e ele não está instalado neste computador.\n\n"
                +"É gratuito e da própria Microsoft. Abrir a página de download agora?","Bella",MessageBoxButtons.YesNo,MessageBoxIcon.Information);
            if(r==DialogResult.Yes) { try { System.Diagnostics.Process.Start(BaixarWebView2); } catch { } }
            return false;
        }
    }
    static class SelfTest {
        sealed class Wake : IWake { public bool Trigger; public bool Hear(byte[] b) { return Trigger; } public void Reset() { Trigger=false; } public void Dispose() {} }
        static void Check(bool condition,string name) { if(!condition) throw new Exception(name); }
        public static void Run() {
            AnexoTestes.Run();
            PastasTestes.Run(AppDomain.CurrentDomain.BaseDirectory); ArquivosLivresTestes.Run(AppDomain.CurrentDomain.BaseDirectory);
            ImagensTestes.Run(AppDomain.CurrentDomain.BaseDirectory);
            ProgramasTestes.Run();
            VozRedeTestes.Run();
            ArquivosTestes.Run(AppDomain.CurrentDomain.BaseDirectory);
            NavegadorTestes.Run();
            CapturaTestes.Run();
            var wake=new Wake(); var c=new Capture(wake); int requests=0; byte[] result=null;
            c.RequestReady+=b=>{ requests++; result=b; };
            var silence=new byte[3200]; var voice=new byte[3200]; for(int i=1;i<voice.Length;i+=2) voice[i]=10;
            wake.Trigger=true; c.Feed(voice); Check(c.State==Capture.Mode.Paused,"pausa captura nada");
            c.Listen(); c.Feed(voice); Check(c.State==Capture.Mode.Listening,"audio ambiente nao ativa");
            int calls=0; c.WakeDetected+=()=>calls++;
            wake.Trigger=true; c.Feed(voice); Check(c.State==Capture.Mode.Greeting && calls==1,"Bella sauda antes de gravar");
            for(int i=0;i<70;i++) c.Feed(voice); c.Begin();
            Check(requests==0 && calls==1 && c.State==Capture.Mode.Greeting,"saudacao nao vira pedido nem duplica chamada");
            c.RecordAfterGreeting(); Check(c.State==Capture.Mode.Recording,"grava somente depois da saudacao");
            for(int i=0;i<6;i++) c.Feed(voice); for(int i=0;i<15;i++) c.Feed(silence);
            Check(requests==1 && result.Length>44 && c.State==Capture.Mode.Processing,"uma pausa envia um WAV");
            c.Feed(voice); c.Begin(); Check(requests==1 && c.State==Capture.Mode.Processing,"pedido em andamento nao duplica");
            c.Speaking(); wake.Trigger=true; c.Feed(voice); Check(requests==1,"resposta falada nao ativa");
            c.Listen(); c.Begin(); c.RecordAfterGreeting(); for(int i=0;i<65;i++) c.Feed(silence);
            Check(requests==1 && c.State==Capture.Mode.Listening,"silencio nao vira pedido");
            c.Begin(); c.RecordAfterGreeting(); for(int i=0;i<310 && c.State==Capture.Mode.Recording;i++) c.Feed(voice);
            Check(requests==2 && result.Length<=30*32000+44,"gravacao termina antes de 30 segundos");
            c.Listen(); c.Begin(); c.Pause(); c.RecordAfterGreeting();
            Check(c.State==Capture.Mode.Paused,"pausar durante saudacao nao reabre microfone");
            AvatarTestes.Run(Path.GetTempPath());
            ApertarParaFalarTestes.Run();
            ChamadasTestes.Run();
            var cacheDirectory=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"self-test-saudacoes");
            try { GreetingLibrary.SelfTest(cacheDirectory); }
            finally { if(Directory.Exists(cacheDirectory)) Directory.Delete(cacheDirectory,true); }
            using(var local=new LocalWake(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"modelo"))) {
                Check(!local.Hear(silence),"modelo real ignora silencio"); local.Reset();
            }
            bool rejected=false; try { Settings.Validate("http://example.com","bella_"+new string('x',43)); } catch { rejected=true; }
            Check(rejected,"chave nunca enviada por HTTP publico");
            // A tela e o WebView2 vão no pacote.
            var raiz=AppDomain.CurrentDomain.BaseDirectory;
            foreach(var arquivo in new[] { @"ui\index.html",@"ui\bella.css",@"ui\bella.js","Microsoft.Web.WebView2.Core.dll","Microsoft.Web.WebView2.WinForms.dll","WebView2Loader.dll" })
                Check(File.Exists(Path.Combine(raiz,arquivo)),"pacote inclui "+arquivo);
            // A foto: só imagem de verdade entra, e o recorte sobrevive ao reinício.
            var pastaFoto=Path.Combine(raiz,"self-test-foto");
            try {
                var jpeg="data:image/jpeg;base64,"+Convert.ToBase64String(new byte[] { 0xFF,0xD8,0xFF,0xE0,0,0x10,(byte)'J',(byte)'F',(byte)'I',(byte)'F' });
                Foto.Salvar(jpeg,jpeg,pastaFoto);
                Check(Foto.Recorte(pastaFoto)==jpeg && Foto.Original(pastaFoto)==jpeg,"foto salva e lida de volta");
                rejected=false; try { Foto.Salvar("data:image/png;base64,"+Convert.ToBase64String(System.Text.Encoding.ASCII.GetBytes("<script>")),null,pastaFoto); } catch { rejected=true; }
                Check(rejected && Foto.Recorte(pastaFoto)==jpeg,"arquivo que nao e imagem e recusado");
                rejected=false; try { Foto.Salvar("file:///C:/Windows/win.ini",null,pastaFoto); } catch { rejected=true; }
                Check(rejected,"foto so aceita data URL de imagem");
                Foto.Remover(pastaFoto); Check(Foto.Recorte(pastaFoto)==null,"remover apaga a foto");
            } finally { if(Directory.Exists(pastaFoto)) Directory.Delete(pastaFoto,true); }
        }
    }
}
