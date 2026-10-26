using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace Bella {
    static class AvatarTestes {
        static void Check(bool ok,string label) { if(!ok) throw new Exception(label); }
        static void Video(string caminho) { var b=new byte[40]; Encoding.ASCII.GetBytes("ftyp").CopyTo(b,4); Directory.CreateDirectory(Path.GetDirectoryName(caminho)); File.WriteAllBytes(caminho,b); }
        internal static void Run(string root) { RunAsync(root).GetAwaiter().GetResult(); }
        static async Task RunAsync(string root) {
            root=Path.Combine(root,"avatar-test-"+Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
            var executor=AvatarAnimado.Executar; var cache=AvatarAnimado.CacheRaiz; var script=AvatarAnimado.Script;
            try {
                AvatarAnimado.CacheRaiz=Path.Combine(root,"cache"); AvatarAnimado.Script=Path.Combine(root,"gerar.py");
                int calls=0;
                AvatarAnimado.Executar=(info,token,progress)=> {
                    calls++; token.ThrowIfCancellationRequested();
                    var marker=" --destino "; var pos=info.Arguments.LastIndexOf(marker,StringComparison.Ordinal);
                    string output=info.Arguments.Substring(pos+marker.Length).Trim('"'); Video(output);
                    return Task.FromResult(0);
                };
                var cfg=new Settings(); var reply=new Reply {mime="audio/mpeg",audio_base64="SUQz"};
                Check(!cfg.AvatarAnimado,"padrao desligado");
                var old=new JavaScriptSerializer().Deserialize<Settings>("{\"Server\":\"https://test.invalid\"}");
                Check(!old.AvatarAnimado,"configuracao anterior fica desligada");
                Check(await AvatarAnimado.Preparar(cfg,reply,CancellationToken.None)==null,"desligado retorna sem instalar motor");
                Check(calls==0 && !Directory.Exists(AvatarAnimado.CacheRaiz),"desligado nao cria arquivos nem processos");
                string motor=Path.Combine(root,"motor com espaco"); Directory.CreateDirectory(motor);
                var arquivos=new[]{Path.Combine(motor,"inference.py"),AvatarAnimado.Python(motor),AvatarAnimado.Script,
                    Path.Combine(motor,"checkpoints","SadTalker_V0.0.2_256.safetensors"),Path.Combine(motor,"checkpoints","mapping_00229-model.pth.tar"),
                    Path.Combine(motor,"gfpgan","weights","alignment_WFLW_4HG.pth"),Path.Combine(motor,"gfpgan","weights","detection_Resnet50_Final.pth")};
                foreach(var f in arquivos) {Directory.CreateDirectory(Path.GetDirectoryName(f)); File.WriteAllText(f,"fixture");}
                cfg.AvatarAnimado=true;cfg.AvatarMotor=motor;
                string foto="data:image/jpeg;base64,/9j/AA==";
                var a=await AvatarAnimado.Preparar(cfg,reply,CancellationToken.None,foto:foto);
                Check(AvatarAnimado.VideoValido(a) && calls==1,"primeiro pedido gera video");
                Check(await AvatarAnimado.Preparar(cfg,reply,CancellationToken.None,foto:foto)==a && calls==1,"cache evita repetir geracao");
                reply.audio_base64="SUQzAQ==";
                Check(await AvatarAnimado.Preparar(cfg,reply,CancellationToken.None,foto:foto)!=a && calls==2,"voz diferente separa cache");
                for(int i=0;i<7;i++) {reply.audio_base64=Convert.ToBase64String(new byte[]{73,68,51,(byte)(i+3)});await AvatarAnimado.Preparar(cfg,reply,CancellationToken.None,foto:foto);}
                Check(Directory.GetFiles(AvatarAnimado.CacheRaiz,"*.mp4").Length==5,"cache limitado a cinco videos");
                var serialized=new JavaScriptSerializer().Serialize(cfg);
                var copy=new JavaScriptSerializer().Deserialize<Settings>(serialized);
                Check(copy.AvatarAnimado && copy.AvatarMotor==motor,"opcao e motor persistem");
                var canceled=new CancellationTokenSource(); canceled.Cancel(); bool rejeitou=false;
                try { await AvatarAnimado.Preparar(cfg,reply,canceled.Token,foto:foto); } catch(OperationCanceledException) {rejeitou=true;}
                Check(rejeitou,"pedido cancelado nao inicia geracao");
                AvatarAnimado.Executar=(info,token,progress)=>Task.FromResult(3);
                reply.audio_base64="SUQzZg==";rejeitou=false;
                try {await AvatarAnimado.Preparar(cfg,reply,CancellationToken.None,foto:foto);} catch(InvalidOperationException e) {rejeitou=e.Message.Contains("30 segundos");}
                Check(rejeitou,"fala longa volta ao audio");
                Check(Directory.GetDirectories(AvatarAnimado.CacheRaiz,"work-*").Length==0,"limpa temporarios apos sucesso e falha");
                AvatarAnimado.Executar=async(info,token,progress)=> {await Task.Delay(10000,token);return 0;};
                using(var durante=new CancellationTokenSource()) {
                    var task=AvatarAnimado.Preparar(cfg,reply,durante.Token,foto:foto);durante.CancelAfter(100);
                    rejeitou=false;try {await task;}catch(OperationCanceledException){rejeitou=true;}
                    Check(rejeitou,"cancela durante a geracao");
                }
                Check(Directory.GetDirectories(AvatarAnimado.CacheRaiz,"work-*").Length==0,"cancelamento limpa temporarios");
                Check(AvatarAnimado.Aspas("C:\\pasta com espaco\\")=="\"C:\\pasta com espaco\\\\\"","argumento termina com barra");
                Check(AvatarAnimado.Aspas("x\"y")=="\"x\\\"y\"","escapa aspas sem shell");
                using(var cancelarProcesso=new CancellationTokenSource()) {
                    var info=new System.Diagnostics.ProcessStartInfo(Path.Combine(Environment.SystemDirectory,"WindowsPowerShell","v1.0","powershell.exe"),
                        "-NoProfile -NonInteractive -Command \"Write-Output 'AVATAR|modelo'; Start-Sleep -Seconds 30\"") {
                        UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true
                    };
                    var inicio=System.Diagnostics.Stopwatch.StartNew();
                    var processo=AvatarAnimado.Processar(info,cancelarProcesso.Token,etapa=> {if(etapa=="modelo")cancelarProcesso.Cancel();});
                    cancelarProcesso.CancelAfter(5000);
                    try {await processo;} catch(OperationCanceledException) { }
                    Check(cancelarProcesso.IsCancellationRequested && inicio.Elapsed.TotalSeconds<10,"encerra processo nativo sem esperar o trabalho terminar");
                }
            } finally {
                AvatarAnimado.Executar=executor; AvatarAnimado.CacheRaiz=cache;AvatarAnimado.Script=script;
                if(Directory.Exists(root)) Directory.Delete(root,true);
            }
        }
    }
}
