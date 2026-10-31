using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Threading;
using System.Web.Script.Serialization;

namespace Bella {
    public sealed class Settings {
        public string Server="https://solobot.duckdns.org";
        public string Key="";
        public bool Startup;
        public int Threshold=220;
        public bool MiniBella=true;          // a pílula sobre a barra de tarefas quando a janela está fechada
        public bool PushToTalk;
        public bool FastWake;
        public bool ModoSafada;
        public bool AvatarAnimado; // Desligado em instalacoes novas e configuracoes antigas.
        public string AvatarMotor="";
        public string[] WakePhrases=Chamadas.Padrao();
        public int TalkKey=119;              // F8
        public int TalkModifiers;
        public int TalkSeconds=5;
        public string Aparencia="foto";      // "foto" (foto com o anel) ou "orbe"
        public string[] PastasArquivos=Arquivos.PastasPadrao();
        public ComandoPasta[] ComandosPastas=new ComandoPasta[0];
        static readonly string FilePath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Solo","Bella","acesso.dat");
        public static Settings Load() {
            if(!File.Exists(FilePath)) return new Settings();
            try {
                var bytes=ProtectedData.Unprotect(File.ReadAllBytes(FilePath),null,DataProtectionScope.CurrentUser);
                return new JavaScriptSerializer().Deserialize<Settings>(Encoding.UTF8.GetString(bytes));
            } catch { return new Settings(); }
        }
        public void Save() {
            Validate(Server,Key);
            ApertarParaFalar.Validar(TalkKey,TalkModifiers,TalkSeconds);
            WakePhrases=Chamadas.Validar(WakePhrases);
            var bytes=Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(this));
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath));
            File.WriteAllBytes(FilePath,ProtectedData.Protect(bytes,null,DataProtectionScope.CurrentUser));
        }
        public static void Validate(string server,string key) {
            Uri uri;
            if(!Uri.TryCreate(server,UriKind.Absolute,out uri) || !String.IsNullOrEmpty(uri.UserInfo)
                || !String.IsNullOrEmpty(uri.Query) || !String.IsNullOrEmpty(uri.Fragment)
                || (uri.Scheme!="https" && !(uri.Scheme=="http" && uri.IsLoopback)))
                throw new InvalidOperationException("Use o endereço HTTPS do Solo Bot.");
            if(!System.Text.RegularExpressions.Regex.IsMatch(key,"^bella_[A-Za-z0-9_-]{40,80}$"))
                throw new InvalidOperationException("Cole a chave gerada na seção Bella do painel.");
        }
    }
    public class Reply {
        public string texto { get; set; }
        public string falar { get; set; }
        public string ouvido { get; set; }
        public string audio_base64 { get; set; }
        public string mime { get; set; }
        public string voz_id { get; set; }
        public string imagem_base64 { get; set; }
        public string imagem_mime { get; set; }
        public Opcao[] opcoes { get; set; }
        internal string AudioPath;
        internal string CodigoVoz;
        internal bool SomenteLocal; // Não envia o pedido à interpretação; voz configurada continua permitida.
        internal bool ExigirVozConfigurada;
    }
    public sealed class Opcao {
        public int numero { get; set; }
        public string rotulo { get; set; }
        public string titulo { get; set; }
        public string comando { get; set; } // ação local com identificador, não se mistura aos números do hub
    }
    public sealed class InterpretacaoComando {
        public string comando_id { get; set; }
        public string[] candidatos { get; set; }
        public string assunto { get; set; }
    }
    public sealed class Client : IDisposable {
        readonly HttpClient http;
        readonly string server,key;
        readonly CancellationToken voiceCancellation;
        // Limite de espera, não atraso: respostas prontas retornam imediatamente.
        const int VoiceWaitSeconds=145;
        public Client(string url,string credential,HttpMessageHandler handler=null,CancellationToken voiceToken=default(CancellationToken)) {
            Settings.Validate(url,credential); server=url.TrimEnd('/'); key=credential; voiceCancellation=voiceToken;
            // Não encaminha a chave a outro domínio por redirecionamento.
            http=new HttpClient(handler ?? new HttpClientHandler { AllowAutoRedirect=false });
            http.Timeout=TimeSpan.FromSeconds(150);
        }
        public async Task<Reply> Send(string text,byte[] wave,bool viaAudio=false) {
            var body=new Dictionary<string,object> { {"pedido_id",Guid.NewGuid().ToString()}, {"voz",true}, {"voz_separada",true} };
            if(wave!=null) body["audio_base64"]=Convert.ToBase64String(wave); else body["texto"]=text;
            if(viaAudio) body["via_audio"]=true;
            return await Request<Reply>(HttpMethod.Post,"/api/bella/mensagem",body,150);
        }
        public Task<Reply> Transcribe(byte[] wave) {
            return Request<Reply>(HttpMethod.Post,"/api/bella/transcrever",new Dictionary<string,object> {
                {"pedido_id",Guid.NewGuid().ToString()}, {"audio_base64",Convert.ToBase64String(wave)} },130);
        }
        public Task<Reply> LocalVoice(string code) {
            return Request<Reply>(HttpMethod.Post,"/api/bella/voz-local",new Dictionary<string,object> { {"codigo",code} },VoiceWaitSeconds,voiceCancellation);
        }
        public Task<Reply> ResponseVoice(string id) {
            return Request<Reply>(HttpMethod.Post,"/api/bella/voz-resposta",new {voz_id=id},VoiceWaitSeconds,voiceCancellation);
        }
        public Task<InterpretacaoComando> InterpretarComando(string text,ComandoPasta[] comandos) {
            var catalogo=new List<object>();
            foreach(var c in comandos) catalogo.Add(new {id=c.Id,frase=c.Frase,tipo=c.Tipo ?? "pasta"});
            return Request<InterpretacaoComando>(HttpMethod.Post,"/api/bella/interpretar-comando",new {texto=text,comandos=catalogo},15);
        }
        public Task<AcaoPrograma> InterpretarPrograma(string text,ComandoPasta[] comandos,bool safada=false) {
            var catalogo=new List<object>();
            foreach(var c in comandos) catalogo.Add(new {id=c.Id,frase=c.Frase,tipo=c.Tipo});
            var body=new Dictionary<string,object> {{"texto",text},{"comandos",catalogo}};
            if(safada) body["modo"]="safada";
            return Request<AcaoPrograma>(HttpMethod.Post,"/api/bella/programa",body,25);
        }
        public Task<Reply> GerarImagem(string prompt) {
            return Request<Reply>(HttpMethod.Post,"/api/bella/imagem",new {pedido_id=Guid.NewGuid().ToString(),prompt=prompt},135);
        }
        public Task<Reply> Conversar(string text,string imagem=null) {
            var body=new Dictionary<string,object> {{"texto",text},{"modo","safada"},{"voz_separada",true}};
            int segundos=Regex.IsMatch(text ?? "",@"prompt|character\s*sheet|ficha\s+de\s+personagem|posehot",RegexOptions.IgnoreCase) ? 145 : 25;      // um prompt com o Grok lento pode levar mais de 1 min
            // Referência de roupa para o prompt: "data:image/jpeg;base64,...". O servidor valida tipo e tamanho.
            const string marca=";base64,";
            if(imagem!=null && imagem.StartsWith("data:image/") && imagem.Length<8000000) {
                int i=imagem.IndexOf(marca,StringComparison.Ordinal);
                if(i>11) {
                    body["imagem_mime"]=imagem.Substring(5,i-5);
                    body["imagem_base64"]=imagem.Substring(i+marca.Length);
                    segundos=145;
                }
            }
            return Request<Reply>(HttpMethod.Post,"/api/bella/conversa",body,segundos);
        }
        public Task<GreetingSet> Greetings() { return Request<GreetingSet>(HttpMethod.Get,"/api/bella/saudacoes",null,8); }
        public Task<GreetingReply> Greeting(int id) {
            return Request<GreetingReply>(HttpMethod.Post,"/api/bella/saudacao",new Dictionary<string,object> { {"id",id} },VoiceWaitSeconds,voiceCancellation);
        }
        async Task<T> Request<T>(HttpMethod method,string path,object body,int seconds,CancellationToken cancellation=default(CancellationToken)) {
            var request=new HttpRequestMessage(method,server+path);
            request.Headers.Add("X-Bella-Chave",key);
            if(body!=null) request.Content=new StringContent(new JavaScriptSerializer { MaxJsonLength=16*1024*1024 }.Serialize(body),Encoding.UTF8,"application/json");
            try {
                using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancellation))
                using(request) {
                    timeout.CancelAfter(TimeSpan.FromSeconds(seconds));
                    cancellation.ThrowIfCancellationRequested();
                    using(var response=await http.SendAsync(request,timeout.Token)) {
                        var json=await response.Content.ReadAsStringAsync();
                        var parser=new JavaScriptSerializer { MaxJsonLength=16*1024*1024 };
                        if(!response.IsSuccessStatusCode) {
                            string detail="O Solo Bot respondeu HTTP "+(int)response.StatusCode+".";
                            try {
                                var data=parser.Deserialize<Dictionary<string,object>>(json);
                                object value; if(data.TryGetValue("detail",out value) && value is string) detail=(string)value;
                            } catch { }
                            if(path=="/api/bella/imagem" && (response.StatusCode==HttpStatusCode.NotFound || response.StatusCode==HttpStatusCode.MethodNotAllowed))
                                throw new InvalidOperationException("O Solo Bot no servidor ainda não está atualizado para gerar imagens. Publique o backend de imagens e tente novamente; este pedido não chegou ao Grok.");
                            if(response.StatusCode==HttpStatusCode.Unauthorized) throw new UnauthorizedAccessException(detail);
                            throw new InvalidOperationException(detail);
                        }
                        cancellation.ThrowIfCancellationRequested();
                        return parser.Deserialize<T>(json);
                    }
                }
            } catch(OperationCanceledException) {
                cancellation.ThrowIfCancellationRequested();
                if(path=="/api/bella/voz-local" || path=="/api/bella/voz-resposta" || path=="/api/bella/saudacao")
                    throw new InvalidOperationException("O motor de voz demorou para gerar o áudio. A resposta continua na tela.");
                throw new InvalidOperationException("A resposta demorou. Confira o resultado no sistema antes de repetir o pedido.");
            } catch(HttpRequestException) {
                throw new InvalidOperationException("A conexão falhou. Confira no sistema se o pedido foi executado antes de repetir.");
            }
        }
        public void Dispose() { http.Dispose(); }
    }
}
