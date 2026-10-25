using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Web.Script.Serialization;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

namespace Bella {
    internal static class ProgramasTestes {
        sealed class WordFalso : IEditorWord {
            public int Chamadas; public string Texto;
            public string Executar(string texto) { Check(Thread.CurrentThread.GetApartmentState()==ApartmentState.STA,"Word executa em STA"); Chamadas++; Texto=texto; return "Documento de teste pronto"; }
        }
        static void Check(bool ok,string texto) {if(!ok) throw new Exception("Aplicativos: "+texto);}
        public static void Run() {
            CriacaoEVoz();
            ModoConversaTestes.Run();
            var editar=new ComandoPasta {Tipo="word",Frase="Escreva {pedido}"};
            var gerar=new ComandoPasta {Tipo="word",Frase="Faça {pedido}"};
            var abrir=new ComandoPasta {Tipo="word",Frase="Abrir Word"};
            var editor=new WordFalso();
            var programas=new Programas(()=>new[] {editar,gerar,abrir},editor);
            int ia=0;
            Func<string,ComandoPasta[],Task<AcaoPrograma>> interpretar=(texto,comandos)=> {
                ia++; return Task.FromResult(new AcaoPrograma {comando_id=comandos[0].Id,acao="escrever",texto="O amor é uma flor.\nFloresce com calor."});
            };
            var tempos=new Dictionary<string,long>();
            var r=programas.Atender("Escreva O amor é lindo, por favor.",interpretar,tempos:tempos).GetAwaiter().GetResult();
            Check(editor.Texto=="O amor é lindo, por favor." && ia==0 && editor.Chamadas==1,"ditado literal preserva acentos, caixa e pontuação sem pedir IA");
            Check(tempos.ContainsKey("Aplicativo") && !tempos.ContainsKey("IA do aplicativo"),"tempos distinguem ação local de IA");
            programas.Atender("Faça uma rima com amor",interpretar).GetAwaiter().GetResult();
            Check(ia==1 && editor.Chamadas==2 && editor.Texto.Contains("flor"),"geração requer uma só interpretação e insere o resultado");
            programas.Atender("Abra o Word",interpretar).GetAwaiter().GetResult();
            Check(editor.Chamadas==3 && editor.Texto==null && ia==1,"abertura direta não gasta IA");
            foreach(var pedido in new[] {"/fin saldo","crie uma rotina diária de treino","não escreva amor"})
                Check(programas.Atender(pedido,interpretar).GetAwaiter().GetResult()==null,"comandos alheios e negações não escrevem no Word");
            int antes=editor.Chamadas;
            programas.Atender("Faça uma rima",(t,c)=>Task.FromResult(new AcaoPrograma {comando_id=abrir.Id,acao="escrever",texto="errado"})).GetAwaiter().GetResult();
            Check(editor.Chamadas==antes,"resposta de IA não pode trocar o comando selecionado");
            programas.Atender("Faça uma rima",(t,c)=>Task.FromResult(new AcaoPrograma {comando_id=gerar.Id,acao="salvar",texto="errado"})).GetAwaiter().GetResult();
            Check(editor.Chamadas==antes,"ação fora da lista não executa");
            bool cancelou=false;
            try {programas.Atender("Faça uma rima",interpretar,()=>false).GetAwaiter().GetResult();} catch(OperationCanceledException) {cancelou=true;}
            Check(cancelou && editor.Chamadas==antes,"cancelamento após IA impede execução");
            var arquivos=new Arquivos(()=>new string[0],commands:()=>new[] {editar,abrir});
            Check(Array.TrueForAll(arquivos.CatalogoComandos,c=>!Programas.Tipo(c.Tipo)),"programas não entram no motor de arquivos");
            var cadastrados=ComandosPastas.Atualizar(new ComandoPasta[0],null,"Escreva {pedido}","",tipo:"word");
            Check(cadastrados[0].Tipo=="word" && cadastrados[0].Caminho=="","Word configura sem caminho de executável");
            foreach(var caminho in new[] {@"C:\Windows\System32\cmd.exe /c whoami",@"C:\teste.ps1",@"\\servidor\teste.exe"}) {
                bool recusou=false; try {Programas.Executavel(caminho);} catch {recusou=true;}
                Check(recusou,"recusa argumentos, scripts e executáveis de rede");
            }
            string conteudo;
            Check(Programas.Casar(editar,"Escreva primeira linha\nsegunda linha",out conteudo) && conteudo=="primeira linha\nsegunda linha","ditado aceita parágrafos");
            var simples=new Programas(()=>new[] {abrir},editor);
            int iaAntes=ia;
            simples.Atender("Escreva o amor é lindo",interpretar).GetAwaiter().GetResult();
            Check(editor.Texto=="o amor é lindo" && ia==iaAntes,"um cadastro Word já permite ditado claro sem gastar IA");
            string executavel=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"Bella.exe"), aberto=null;
            var outro=new ComandoPasta {Tipo="programa",Frase="Abrir programa de teste",Caminho=executavel};
            var lancador=new Programas(()=>new[] {outro},editor,p=>aberto=p);
            lancador.Atender(outro.Frase,interpretar).GetAwaiter().GetResult();
            Check(aberto==executavel && ia==iaAntes,"programa configurado abre por caminho validado sem IA nem argumentos");
        }
        sealed class RedeAplicativo : HttpMessageHandler {
            public string Id; public bool FalharVoz, Incerto; public List<string> Rotas=new List<string>();
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                Rotas.Add(r.RequestUri.AbsolutePath);
                string body=await r.Content.ReadAsStringAsync();
                if(r.RequestUri.AbsolutePath.EndsWith("/programa")) {
                    Check(body.Contains("Crie o") && body.Contains("Bella"),"criação chega normalizada ao servidor existente");
                    return Json(new {comando_id=Incerto ? "" : Id,acao="escrever",texto="Uma pequena faísca pode iluminar seu próximo projeto. Com carinho, Bella."});
                }
                Check(r.RequestUri.AbsolutePath.EndsWith("/voz-local"),"aplicativo nunca segue ao hub de sistemas");
                Check(body.Contains("codigo") && !body.Contains("faísca"),"síntese recebe apenas código, sem documento");
                if(FalharVoz) return new HttpResponseMessage(HttpStatusCode.ServiceUnavailable) {Content=new StringContent("{}")};
                return Json(new {falar="Pronto.",audio_base64="SUQz",mime="audio/mpeg"});
            }
            static HttpResponseMessage Json(object obj) {return new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent(new JavaScriptSerializer().Serialize(obj),Encoding.UTF8,"application/json")};}
        }
        static void CriacaoEVoz() {
            var c=new ComandoPasta {Tipo="word",Frase="Escreva {pedido}"};
            var editor=new WordFalso(); var programas=new Programas(()=>new[] {c},editor);
            foreach(string pedido in new[] {"Abra o Word e escreva uma mensagem sua para mim.","Abra o Word e escreva uma mensagem surda para mim.","Escreva uma mensagem sua para mim.","Bella, crie uma mensagem sua para mim"}) {
                int chamadas=0,antes=editor.Chamadas;
                var r=programas.Atender(pedido,(t,cs)=> {
                    chamadas++; Check(t.StartsWith("Crie o conteúdo") && t.Contains("primeira pessoa como Bella") && !t.Contains("surda"),"criação pessoal não é ditado literal");
                    return Task.FromResult(new AcaoPrograma {comando_id=c.Id,acao="escrever",texto="Uma faísca para seu dia. Bella."});
                }).GetAwaiter().GetResult();
                Check(chamadas==1 && editor.Chamadas==antes+1 && editor.Texto=="Uma faísca para seu dia. Bella." && r.CodigoVoz=="aberto","criação gera uma vez e escreve uma vez");
            }
            foreach(bool falhar in new[] {false,true}) foreach(bool incerto in new[] {false,true}) {
                var rede=new RedeAplicativo {Id=c.Id,FalharVoz=falhar,Incerto=incerto};
                int antes=editor.Chamadas,exibidas=0;
                var fila=new PedidosWindows();
                var r=fila.Enviar("Abra o Word e escreva uma mensagem sua para mim",null,new Arquivos(()=>new string[0]),
                    ()=>new Client("https://test.invalid","bella_"+new string('x',43),rede),null,null,x=>exibidas++,programas).GetAwaiter().GetResult();
                Check(rede.Rotas.Count==2 && rede.Rotas[0].EndsWith("/programa") && rede.Rotas[1].EndsWith("/voz-local"),"sucesso e erro de aplicativo solicitam ElevenLabs");
                Check(editor.Chamadas==antes+(incerto ? 0 : 1) && exibidas==1,"falha de voz não repete operação nem resultado");
                Check(r.ExigirVozConfigurada && (falhar ? r.audio_base64==null : r.audio_base64=="SUQz"),"áudio configurado ou erro explícito, sem voz Windows");
            }
            using(var player=new Playback()) {
                bool erro=false;
                try {player.Say(new Reply {falar="Resposta comum sem áudio"}).GetAwaiter().GetResult();}
                catch(InvalidOperationException e) {erro=e.Message.Contains("ElevenLabs");}
                Check(erro,"respostas comuns também não usam voz Windows");
            }
        }
        public static void WordReal() {
            var processos=Process.GetProcessesByName("WINWORD"); bool aberto=processos.Length>0;
            foreach(var processo in processos) processo.Dispose();
            if(aberto) throw new InvalidOperationException("Feche seus documentos do Word antes do teste isolado; nenhum documento existente foi alterado.");
            object aplicativo=null, documento=null, faixa=null;
            try {
                aplicativo=Activator.CreateInstance(Type.GetTypeFromProgID("Word.Application"));
                dynamic app=aplicativo; app.Visible=true;
                documento=app.Documents.Add(); dynamic doc=documento;
                doc.Content.Text="Texto original.";
                faixa=doc.Range(0,5); ((dynamic)faixa).Select();
                var editor=new EditorWord(); editor.Executar(" NOVO");
                Check(((string)doc.Content.Text).StartsWith("Texto NOVO original."),"Word real preserva o texto selecionado e insere após a seleção");
                editor.Executar(null);
                Check(app.Documents.Count==1,"Word real é reutilizado sem criar documento duplicado");
                Check(!doc.Saved,"Word permanece sem salvamento automático");
            } finally {
                if(documento!=null) {try {((dynamic)documento).Close(0);} finally {Marshal.ReleaseComObject(documento);}}
                if(faixa!=null) Marshal.ReleaseComObject(faixa);
                if(aplicativo!=null) {try {if(((dynamic)aplicativo).Documents.Count==0) ((dynamic)aplicativo).Quit(0);} finally {Marshal.ReleaseComObject(aplicativo);}}
            }
        }
    }
}
