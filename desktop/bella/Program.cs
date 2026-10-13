using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Threading;
using System.Windows.Forms;

namespace Bella {
    static class Program {
        [STAThread] static int Main(string[] args) {
            ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
            if(args.Length==2 && args[0]=="--preview-image") {
                Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                using(var form=new BellaForm(false,true)) using(var bitmap=new System.Drawing.Bitmap(form.Width,form.Height)) {
                    form.ShowInTaskbar=false; form.StartPosition=FormStartPosition.Manual;
                    form.Location=new System.Drawing.Point(-2000,-2000);
                    form.Show(); Application.DoEvents(); form.PerformLayout();
                    form.DrawToBitmap(bitmap,new System.Drawing.Rectangle(0,0,bitmap.Width,bitmap.Height));
                    bitmap.Save(args[1],System.Drawing.Imaging.ImageFormat.Png);
                    form.Hide();
                }
                return 0;
            }
            if(args.Contains("--self-test")) {
                try { SelfTest.Run(); File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"self-test.txt"),"OK"); return 0; }
                catch(Exception e) { File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"self-test.txt"),e.ToString()); return 1; }
            }
            bool created;
            using(var instance=new Mutex(true,@"Local\SoloBellaDesktop",out created)) {
                if(!created) { MessageBox.Show("A Bella já está perto do relógio. Abra pelo ícone.","Bella"); return 0; }
                Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                try {
                    var form=new BellaForm(args.Contains("--minimized"),args.Contains("--preview"));
                    Application.Run(form);
                } catch(Exception e) { MessageBox.Show("Não consegui abrir a Bella: "+e.Message,"Bella"); return 1; }
            }
            return 0;
        }
    }
    static class SelfTest {
        sealed class Wake : IWake { public bool Trigger; public bool Hear(byte[] b) { return Trigger; } public void Reset() { Trigger=false; } public void Dispose() {} }
        static void Check(bool condition,string name) { if(!condition) throw new Exception(name); }
        public static void Run() {
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
            var cacheDirectory=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"self-test-saudacoes");
            try { GreetingLibrary.SelfTest(cacheDirectory); }
            finally { if(Directory.Exists(cacheDirectory)) Directory.Delete(cacheDirectory,true); }
            using(var local=new LocalWake(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"modelo"))) {
                Check(!local.Hear(silence),"modelo real ignora silencio"); local.Reset();
            }
            bool rejected=false; try { Settings.Validate("http://example.com","bella_"+new string('x',43)); } catch { rejected=true; }
            Check(rejected,"chave nunca enviada por HTTP publico");
        }
    }
}
