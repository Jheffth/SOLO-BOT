using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Threading;
using System.Web.Script.Serialization;

namespace Bella {
    public sealed class GreetingLine { public int id { get; set; } public string texto { get; set; } }
    public sealed class GreetingSet {
        public string perfil { get; set; }
        public string usuario { get; set; }
        public Dictionary<string,string> voz { get; set; }
        public GreetingLine[] saudacoes { get; set; }
    }
    public sealed class GreetingReply : Reply {
        public string perfil { get; set; }
        public int id { get; set; }
        public string usuario { get; set; }
        public Dictionary<string,string> voz { get; set; }
    }
    public sealed class GreetingLibrary {
        readonly string root;
        readonly Random random=new Random();
        readonly Queue<int> deck=new Queue<int>();
        readonly JavaScriptSerializer json=new JavaScriptSerializer();
        GreetingSet current;
        string deckProfile;
        int last=-1;
        bool warming;
        public GreetingLibrary(Settings settings,string directory=null) {
            using(var hash=SHA256.Create()) {
                var scope=BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(settings.Server+"\n"+settings.Key))).Replace("-","").ToLowerInvariant().Substring(0,24);
                root=Path.Combine(directory ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Solo","Bella","saudacoes"),scope);
            }
            try { Set(json.Deserialize<GreetingSet>(File.ReadAllText(Path.Combine(root,"catalogo.json")))); } catch { current=null; }
        }
        static void Validate(GreetingSet set) {
            if(set==null || !Regex.IsMatch(set.perfil ?? "","^[a-f0-9]{64}$") || set.saudacoes==null
                || set.saudacoes.Length<20 || set.saudacoes.Length>50 || set.saudacoes.Select(x=>x.id).Distinct().Count()!=set.saudacoes.Length
                || set.saudacoes.Any(x=>x.id<0 || x.id>=50 || String.IsNullOrEmpty(x.texto)))
                throw new InvalidOperationException("O catálogo de saudações da Bella não é válido.");
        }
        void Set(GreetingSet set) {
            Validate(set); current=set;
            Directory.CreateDirectory(root); File.WriteAllText(Path.Combine(root,"catalogo.json"),json.Serialize(set),Encoding.UTF8);
        }
        public async Task Load(Client client) {
            try { Set(await client.Greetings()); }
            catch(UnauthorizedAccessException) { current=null; throw; }
            catch { if(current==null) throw; }
        }
        string FileFor(string profile,int id) {
            if(!Regex.IsMatch(profile ?? "","^[a-f0-9]{64}$") || id<0 || id>=50) throw new InvalidOperationException("Saudação inválida.");
            return Path.Combine(root,profile.Substring(0,24),id+".mp3");
        }
        Reply Read(int id,GreetingSet expected=null) {
            expected=expected ?? current;
            var line=expected.saudacoes.Single(x=>x.id==id);
            var path=FileFor(expected.perfil,id);
            if(!File.Exists(path) || new FileInfo(path).Length==0) return null;
            return new Reply { texto=line.texto, falar=line.texto, mime="audio/mpeg", AudioPath=path };
        }
        Reply Store(GreetingReply reply,GreetingSet expected=null) {
            expected=expected ?? current;
            if(reply==null || expected==null || !expected.saudacoes.Any(x=>x.id==reply.id && x.texto==reply.texto))
                throw new InvalidOperationException("A saudação não corresponde ao login atual.");
            var path=FileFor(reply.perfil,reply.id);
            if(current!=null && current.perfil==expected.perfil && reply.perfil!=current.perfil)
                Set(new GreetingSet { perfil=reply.perfil, usuario=reply.usuario, voz=reply.voz, saudacoes=expected.saudacoes });
            if(reply.mime=="audio/mpeg" && !String.IsNullOrEmpty(reply.audio_base64)) {
                var audio=Convert.FromBase64String(reply.audio_base64);
                if(audio.Length==0) return reply;
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                if(!File.Exists(path) || new FileInfo(path).Length==0) {
                    var temp=path+"."+Guid.NewGuid().ToString("N").Substring(0,8)+".tmp";
                    try { File.WriteAllBytes(temp,audio); if(File.Exists(path)) File.Delete(path); File.Move(temp,path); }
                    finally { if(File.Exists(temp)) File.Delete(temp); }
                }
                reply.AudioPath=path; reply.audio_base64=null;
            }
            return reply;
        }
        int NextId() {
            if(deckProfile!=current.perfil) { deck.Clear(); deckProfile=current.perfil; }
            if(deck.Count==0) {
                var ids=current.saudacoes.Select(x=>x.id).ToArray();
                for(int i=ids.Length-1;i>0;i--) { int j=random.Next(i+1), v=ids[i]; ids[i]=ids[j]; ids[j]=v; }
                if(ids.Length>1 && ids[0]==last) { int v=ids[0]; ids[0]=ids[1]; ids[1]=v; }
                foreach(var id in ids) deck.Enqueue(id);
            }
            last=deck.Dequeue(); return last;
        }
        public async Task<Reply> Next(Client client) {
            await Load(client);
            var expected=current;
            int id=NextId(); var saved=Read(id,expected);
            return saved ?? Store(await client.Greeting(id),expected);
        }
        public async Task Warm(Client client,Func<bool> keepGoing) {
            if(warming) return; warming=true;
            try {
                await Load(client);
                if(current.voz==null || String.IsNullOrEmpty(current.voz["voz"])) return;
                foreach(var id in current.saudacoes.Select(x=>x.id).ToArray()) {
                    if(!keepGoing()) return;
                    var expected=current;
                    if(Read(id,expected)!=null) continue;
                    var reply=Store(await client.Greeting(id),expected);
                    if(String.IsNullOrEmpty(reply.AudioPath)) return;
                }
            } finally { warming=false; }
        }
        internal static void SelfTest(string directory) {
            var settings=new Settings { Server="https://test.invalid",Key="bella_"+new string('x',43) };
            var library=new GreetingLibrary(settings,directory);
            var lines=Enumerable.Range(0,20).Select(i=>new GreetingLine { id=i,texto="Oi, jeff. Frase "+i }).ToArray();
            var a=new string('a',64); var b=new string('b',64);
            library.Set(new GreetingSet { perfil=a,usuario="jeff",saudacoes=lines });
            var seen=new HashSet<int>(); for(int i=0;i<20;i++) seen.Add(library.NextId());
            if(seen.Count!=20) throw new Exception("saudacoes nao se repetem no ciclo");
            int previous=library.last; if(library.NextId()==previous) throw new Exception("nao repete entre ciclos");
            library.Store(new GreetingReply { perfil=a,id=0,texto=lines[0].texto,falar=lines[0].texto,mime="audio/mpeg",audio_base64="SUQz" });
            var saved=new GreetingLibrary(settings,directory); if(saved.Read(0)==null) throw new Exception("audio salvo sobrevive ao reinicio");
            saved.Set(new GreetingSet { perfil=b,usuario="jeff",saudacoes=lines });
            if(saved.Read(0)!=null) throw new Exception("voz nova nao reutiliza voz anterior");
            bool rejected=false; try { saved.FileFor("../fora",0); } catch { rejected=true; }
            if(!rejected) throw new Exception("cache rejeita caminho externo");
            var handler=new GreetingTestHandler(lines,a,b);
            using(var client=new Client(settings.Server,settings.Key,handler)) {
                var real=new GreetingLibrary(settings,Path.Combine(directory,"http"));
                real.Warm(client,()=>true).GetAwaiter().GetResult();
                for(int i=0;i<25;i++) {
                    var reply=real.Next(client).GetAwaiter().GetResult();
                    if(String.IsNullOrEmpty(reply.AudioPath)) throw new Exception("reproduz audio salvo do perfil");
                }
                if(handler.Posts!=20) throw new Exception("chamadas repetidas nao solicitam nova sintese");
                handler.Profile=b;
                var changed=real.Next(client).GetAwaiter().GetResult();
                if(!changed.AudioPath.Contains(b.Substring(0,24)) || handler.Posts!=21)
                    throw new Exception("detecta troca de voz no servidor");
                handler.Revoked=true; rejected=false;
                try { real.Next(client).GetAwaiter().GetResult(); } catch(UnauthorizedAccessException) { rejected=true; }
                if(!rejected) throw new Exception("chave revogada nao usa cache antigo");
            }
        }
        sealed class GreetingTestHandler : HttpMessageHandler {
            readonly GreetingLine[] lines;
            readonly JavaScriptSerializer parser=new JavaScriptSerializer();
            public string Profile;
            public bool Revoked;
            public int Posts;
            public GreetingTestHandler(GreetingLine[] values,string a,string b) { lines=values; Profile=a; }
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token) {
                if(!request.Headers.Contains("X-Bella-Chave")) throw new Exception("autentica saudacoes");
                if(Revoked) return new HttpResponseMessage(HttpStatusCode.Unauthorized) { Content=new StringContent("{}") };
                var voice=new Dictionary<string,string> { {"conta","principal"},{"voz",Profile},{"modelo","flash"} };
                object body;
                if(request.Method==HttpMethod.Get) body=new GreetingSet { perfil=Profile,usuario="jeff",voz=voice,saudacoes=lines };
                else {
                    Posts++; int id=parser.Deserialize<Dictionary<string,int>>(await request.Content.ReadAsStringAsync())["id"];
                    body=new GreetingReply { perfil=Profile,usuario="jeff",voz=voice,id=id,texto=lines[id].texto,
                        falar=lines[id].texto,mime="audio/mpeg",audio_base64="SUQz" };
                }
                return new HttpResponseMessage(HttpStatusCode.OK) { Content=new StringContent(parser.Serialize(body)) };
            }
        }
    }
}
