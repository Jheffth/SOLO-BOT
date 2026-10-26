using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace Bella {
    // Sem servidor ou watcher. Cada geracao vive em um processo e libera a GPU ao terminar.
    public static class AvatarAnimado {
        const int MaxVideo=16*1024*1024;
        internal static Func<ProcessStartInfo,CancellationToken,Action<string>,Task<int>> Executar=Processar;
        internal static string CacheRaiz=Path.Combine(Foto.Pasta,"avatar-cache");
        internal static string Script=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"avatar","gerar.py");
        public static string EncontrarMotor(string escolhido=null) {
            if(!String.IsNullOrEmpty(escolhido)) return Path.GetFullPath(escolhido);
            var pasta=new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);
            for(int i=0;i<7 && pasta!=null;i++,pasta=pasta.Parent) {
                var motor=Path.Combine(pasta.FullName,".cache","sadtalker-test");
                if(File.Exists(Path.Combine(motor,"inference.py"))) return motor;
            }
            return null;
        }
        internal static string Python(string motor) {
            return Path.Combine(Directory.GetParent(motor).FullName,"sadtalker-env","Scripts","python.exe");
        }
        public static bool Disponivel(string escolhido=null) {
            try { Validar(escolhido); return true; } catch { return false; }
        }
        public static string Validar(string escolhido=null) {
            string motor=EncontrarMotor(escolhido);
            if(motor==null || !File.Exists(Path.Combine(motor,"inference.py")) || !File.Exists(Python(motor))
                || !File.Exists(Path.Combine(motor,"checkpoints","SadTalker_V0.0.2_256.safetensors"))
                || !File.Exists(Path.Combine(motor,"checkpoints","mapping_00229-model.pth.tar"))
                || !File.Exists(Path.Combine(motor,"gfpgan","weights","alignment_WFLW_4HG.pth"))
                || !File.Exists(Path.Combine(motor,"gfpgan","weights","detection_Resnet50_Final.pth"))
                || !File.Exists(Script))
                throw new InvalidOperationException("Selecione a instalacao local do SadTalker com o ambiente sadtalker-env ao lado.");
            return motor;
        }
        internal static string Aspas(string valor) {
            if(valor.IndexOfAny(new[]{'\r','\n','\0'})>=0) throw new ArgumentException("Caminho invalido");
            // Escapamento Windows para argumentos; nunca invoca cmd ou PowerShell.
            return "\""+Regex.Replace(valor,@"(\\*)""", "$1$1\\\"").ReplaceTrailingSlash()+"\"";
        }
        static string ReplaceTrailingSlash(this string valor) {
            int n=0; for(int i=valor.Length-1;i>=0 && valor[i]=='\\';i--) n++;
            return valor+new string('\\',n);
        }
        internal static bool VideoValido(string path) {
            if(!File.Exists(path)) return false;
            var tamanho=new FileInfo(path).Length;
            if(tamanho<32 || tamanho>MaxVideo) return false;
            using(var f=File.OpenRead(path)) { byte[] b=new byte[12]; if(f.Read(b,0,12)!=12) return false; return Encoding.ASCII.GetString(b,4,4)=="ftyp"; }
        }
        public static async Task<string> Preparar(Settings config,Reply reply,CancellationToken token,Action<string> progresso=null,string foto=null) {
            // Este retorno vem antes de qualquer acesso a disco, decodificacao ou processo.
            if(!config.AvatarAnimado) return null;
            token.ThrowIfCancellationRequested();
            string motor=Validar(config.AvatarMotor);
            string imagem=foto ?? Foto.Original() ?? Foto.Recorte();
            if(imagem==null) throw new InvalidOperationException("Escolha uma foto para usar o avatar animado.");
            var retrato=Foto.Decodificar(imagem,12*1024*1024);
            if(reply.mime!="audio/mpeg") throw new InvalidOperationException("O avatar precisa do audio da voz configurada.");
            byte[] audio=!String.IsNullOrEmpty(reply.AudioPath) ? File.ReadAllBytes(reply.AudioPath) : Convert.FromBase64String(reply.audio_base64 ?? "");
            if(audio.Length==0 || audio.Length>6*1024*1024) throw new InvalidOperationException("Audio indisponivel ou grande demais para animar.");
            return await Task.Run(async()=> {
                token.ThrowIfCancellationRequested();
                string identidade;
                using(var hash=SHA256.Create()) {
                    var dados=retrato.Concat(audio).Concat(File.ReadAllBytes(Script)).Concat(Encoding.UTF8.GetBytes("256-b1-v1|"+motor+"|"+
                        File.GetLastWriteTimeUtc(Path.Combine(motor,"inference.py")).Ticks+"|"+
                        File.GetLastWriteTimeUtc(Path.Combine(motor,"checkpoints","SadTalker_V0.0.2_256.safetensors")).Ticks)).ToArray();
                    identidade=BitConverter.ToString(hash.ComputeHash(dados)).Replace("-","").ToLowerInvariant();
                }
                Directory.CreateDirectory(CacheRaiz);
                string final=Path.Combine(CacheRaiz,identidade+".mp4");
                if(VideoValido(final)) { File.SetLastWriteTimeUtc(final,DateTime.UtcNow); return final; }
                string work=Path.Combine(CacheRaiz,"work-"+Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(work);
                try {
                    var fotoPath=Path.Combine(work,"foto."+(Foto.Tipo(retrato)=="jpeg"?"jpg":Foto.Tipo(retrato)));
                    var audioPath=Path.Combine(work,"voz.mp3"); var videoPath=Path.Combine(work,"video.mp4");
                    File.WriteAllBytes(fotoPath,retrato); File.WriteAllBytes(audioPath,audio);
                    var info=new ProcessStartInfo(Python(motor),Aspas(Script)+" --motor "+Aspas(motor)+" --foto "+Aspas(fotoPath)+" --audio "+Aspas(audioPath)+" --destino "+Aspas(videoPath)) {
                        UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=motor,RedirectStandardOutput=true,RedirectStandardError=true
                    };
                    info.EnvironmentVariables["NUMBA_CACHE_DIR"]=Path.Combine(CacheRaiz,"numba");
                    info.EnvironmentVariables["TEMP"]=work; info.EnvironmentVariables["TMP"]=work;
                    int code=await Executar(info,token,progresso);
                    token.ThrowIfCancellationRequested();
                    if(code==3) throw new InvalidOperationException("A fala passa de 30 segundos. Vou reproduzir o audio sem animacao.");
                    if(code!=0 || !VideoValido(videoPath)) throw new InvalidOperationException("O avatar nao foi gerado. Confira CUDA e a instalacao do SadTalker.");
                    if(File.Exists(final)) File.Delete(final);
                    File.Move(videoPath,final);
                    foreach(var antigo in new DirectoryInfo(CacheRaiz).GetFiles("*.mp4").OrderByDescending(f=>f.LastWriteTimeUtc).Skip(5)) antigo.Delete();
                    return final;
                } finally {
                    // work e um diretorio novo, com nome interno; nunca vem de um caminho enviado pela UI.
                    if(Directory.Exists(work) && Path.GetFullPath(work).StartsWith(Path.GetFullPath(CacheRaiz)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) {
                        try { Directory.Delete(work,true); } catch { }
                    }
                }
            },token);
        }
        internal static async Task<int> Processar(ProcessStartInfo info,CancellationToken token,Action<string> progresso) {
            using(var p=new Process {StartInfo=info}) {
                Action<string> report=line=> {
                    if(line==null || progresso==null) return;
                    try {
                    if(line.StartsWith("AVATAR|",StringComparison.Ordinal)) {
                        var etapa=line.Substring(7);
                        if(new[]{"audio","modelo","geracao","pronto"}.Contains(etapa)) progresso(etapa);
                    } else if(line.Contains("Face Renderer")) {
                        var m=Regex.Match(line,@"(\d{1,3})%"); if(m.Success) progresso("quadros:"+m.Groups[1].Value);
                    }
                    } catch(InvalidOperationException) { /* A interface pode estar sendo encerrada. */ }
                };
                p.OutputDataReceived+=(s,e)=>report(e.Data); p.ErrorDataReceived+=(s,e)=>report(e.Data);
                token.ThrowIfCancellationRequested(); p.Start();
                // Cancelar/fechar a Bella encerra o processo sincronicamente, mesmo antes da continuacao async.
                using(token.Register(()=> {try {if(!p.HasExited) p.Kill();}catch {}})) {
                var tempo=Stopwatch.StartNew();
                try {
                    p.BeginOutputReadLine(); p.BeginErrorReadLine();
                    while(!p.HasExited) {
                        token.ThrowIfCancellationRequested();
                        if(tempo.Elapsed.TotalMinutes>5) throw new InvalidOperationException("A geracao do avatar excedeu cinco minutos.");
                        await Task.Delay(100,token);
                    }
                    p.WaitForExit(); return p.ExitCode;
                } finally { if(!p.HasExited) { try { p.Kill(); p.WaitForExit(5000); } catch { } } }
                }
            }
        }
    }
}
