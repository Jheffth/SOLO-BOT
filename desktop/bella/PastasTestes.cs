using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Threading;

namespace Bella {
    internal static class PastasTestes {
        static void Check(bool ok,string message) { if(!ok) throw new Exception("Pastas automáticas: "+message); }
        static void Pronto(IndicePastas indice) {
            indice.Iniciar(); var tempo=Stopwatch.StartNew();
            while(indice.Trabalhando && tempo.ElapsedMilliseconds<5000) Thread.Sleep(5);
            Check(!indice.Trabalhando,"índice sintético conclui em cinco segundos");
        }
        sealed class VozPastas : HttpMessageHandler {
            readonly List<string> pedidos;
            public VozPastas(List<string> lista) {pedidos=lista;}
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                string body=await r.Content.ReadAsStringAsync(); pedidos.Add(r.RequestUri.AbsolutePath+" "+body);
                string json=r.RequestUri.AbsolutePath.EndsWith("transcrever")
                    ? new JavaScriptSerializer().Serialize(new {ouvido="abrir pasta Biblioteca"})
                    : new JavaScriptSerializer().Serialize(new {falar="Pronto.",audio_base64="SUQz",mime="audio/mpeg"});
                return new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent(json,Encoding.UTF8,"application/json")};
            }
        }
        static void AguardarResultado(string raiz,string permitida) {
            foreach(bool cancelar in new[] {false,true}) {
                using(var entrou=new ManualResetEvent(false)) using(var liberar=new ManualResetEvent(false)) using(var progresso=new ManualResetEvent(false)) {
                    using(var indice=new IndicePastas(()=>new[] {raiz},p=> {
                        if(p==raiz) {entrou.Set(); liberar.WaitOne(); return new[] {permitida};} return new string[0];
                    },pauseMilliseconds:0)) {
                        var files=new Arquivos(()=>new string[0],p=>{},folderIndex:indice);
                        int finais=0,avisos=0;
                        files.ProgressoBusca+=q=> {if(q.HasValue) {Interlocked.Increment(ref avisos); progresso.Set();}};
                        var chamadas=new List<string>(); var fila=new PedidosWindows();
                        var tarefa=fila.Enviar("abrir pasta permitida",null,files,
                            ()=>new Client("https://test.invalid","bella_"+new string('x',43),new VozPastas(chamadas)),null,null,r=>Interlocked.Increment(ref finais));
                        try {
                            Check(entrou.WaitOne(2000) && progresso.WaitOne(2000),"busca lenta publica progresso");
                            Thread.Sleep(1400);
                            Check(!tarefa.IsCompleted && finais==0,"pedido permanece ativo após 1,2 segundo, sem exigir repetição");
                            if(cancelar) {
                                files.CancelarBusca();
                                Check(tarefa.Wait(2000),"cancelamento não aguarda o disco");
                            }
                        } finally {liberar.Set();}
                        var resposta=tarefa.GetAwaiter().GetResult();
                        Check(finais==1 && avisos>0,"uma única resposta final com progresso");
                        Check(cancelar ? resposta.CodigoVoz=="cancelado" : resposta.CodigoVoz=="aberto" || resposta.CodigoVoz=="escolha","resultado final ou cancelamento explícito");
                        Check(!resposta.texto.Contains("repita o pedido") && resposta.ExigirVozConfigurada,"não pede repetição e mantém voz configurada");
                        Pronto(indice);
                    }
                }
            }
        }
        public static void Run(string baseDirectory) {
            string raiz=Path.Combine(baseDirectory,"self-test-pastas-"+Guid.NewGuid().ToString("N"));
            string permitida=Path.Combine(raiz,"permitida"), biblioteca=Path.Combine(raiz,"Biblioteca"), projetos=Path.Combine(raiz,"Projetos");
            Directory.CreateDirectory(permitida); Directory.CreateDirectory(biblioteca); Directory.CreateDirectory(projetos);
            foreach(string nome in new[] {"Arquivos","Google","A Biblioteca","Solo Bot"}) Directory.CreateDirectory(Path.Combine(raiz,nome));
            string repetida=Path.Combine(raiz,"outro","Projetos"); Directory.CreateDirectory(repetida);
            string cache=Path.Combine(raiz,"node_modules","NaoIndexar"); Directory.CreateDirectory(cache);
            File.WriteAllText(Path.Combine(raiz,"NaoEPasta.pdf"),"fixture inerte");
            try {
                int leituras=0;
                DateTime agora=new DateTime(2026,10,24,12,0,0,DateTimeKind.Utc);
                using(var indice=new IndicePastas(()=>new[] {raiz},p=> { Interlocked.Increment(ref leituras); return Directory.EnumerateDirectories(p); },()=>agora,pauseMilliseconds:0)) {
                    var carga=Stopwatch.StartNew(); Pronto(indice); carga.Stop();
                    int primeiraLeitura=leituras;
                    Check(indice.Buscar("biblioteca").Completa && indice.Buscar("biblioteca").Caminhos.Single()==biblioteca,"busca fora das pastas configuradas");
                    Check(indice.Buscar("NaoEPasta").Caminhos.Length==0,"índice não lista arquivos");
                    Check(indice.Buscar("NaoIndexar").Caminhos.Length==0,"dependências volumosas não são indexadas");
                    var abertos=new List<string>();
                    var arquivos=new Arquivos(()=>new[] {permitida},p=>abertos.Add(p),folderIndex:indice);
                    foreach(string pedido in new[] {"Bella, abra a pasta Biblioteca.","Abra Biblioteca.","Abra a Biblioteca.","Abra o projeto Biblioteca.","Quero que abra minha pasta Biblioteca"}) {
                        var r=arquivos.Processar(pedido).GetAwaiter().GetResult();
                        Check(r.CodigoVoz=="aberto" && r.SomenteLocal && abertos.Last()==biblioteca,"abre por nome sem cadastro: "+pedido+" / "+r.texto);
                    }
                    Check(arquivos.Atender("abrir pasta \""+biblioteca+"\"").CodigoVoz=="aberto","caminho completo abre diretamente");
                    Check(arquivos.Atender("abrir pasta \""+cache+"\"").CodigoVoz=="aberto","caminho explícito abre pasta omitida do índice");
                    foreach(string nome in new[] {"Arquivos","Google","A Biblioteca"}) {
                        var literal=arquivos.Atender("abrir pasta \""+nome+"\"");
                        Check(literal.CodigoVoz=="aberto" && abertos.Last()==Path.Combine(raiz,nome),"nome de pasta explícito/literal não vira arquivo ou site: "+nome);
                    }
                    int antes=abertos.Count;
                    var repetidos=arquivos.Atender("abra minha pasta de projetos");
                    Check(repetidos.CodigoVoz=="escolha" && repetidos.opcoes.Length==2 && abertos.Count==antes,"homônimos nunca abrem automaticamente");
                    Check(arquivos.Processar(repetidos.opcoes[0].comando).GetAwaiter().GetResult().CodigoVoz=="aberto","escolha abre a pasta indicada");
                    Check(arquivos.Atender(repetidos.opcoes[0].comando).CodigoVoz=="expirou","escolha não é reutilizada");
                    antes=abertos.Count;
                    var busca=arquivos.Atender("Pesquisar minha pasta Biblioteca");
                    Check(busca.CodigoVoz=="escolha" && busca.SomenteLocal && abertos.Count==antes,"pesquisar pasta não abre navegador nem resultado automático");
                    Check(arquivos.Atender("Não abra a pasta Biblioteca").CodigoVoz=="cancelado" && abertos.Count==antes,"negação não abre pasta");
                    Check(arquivos.Atender("abrir conta")==null && arquivos.Atender("saldo")==null,"pedidos Solo não viram abertura de diretório");
                    Check(arquivos.Atender("excluir pasta \""+biblioteca+"\"").CodigoVoz=="erro" && Directory.Exists(biblioteca),"índice não concede permissão para excluir");
                    Check(arquivos.Atender("renomear pasta \""+biblioteca+"\" para Outra").CodigoVoz=="erro","índice não concede permissão para renomear");
                    Check(arquivos.Atender("mover pasta \""+biblioteca+"\" para \""+permitida+"\"").CodigoVoz=="erro","índice não concede permissão para mover");
                    Check(arquivos.Atender("criar pasta Nova em \""+biblioteca+"\"").CodigoVoz=="erro","índice não concede permissão para criar");
                    Check(arquivos.Atender("abrir arquivo \""+Path.Combine(raiz,"NaoEPasta.pdf")+"\"").CodigoVoz=="erro","arquivo fora do acesso não é aberto");
                    var fila=new PedidosWindows(); var pedidos=new List<string>();
                    Func<Client> vozConfigurada=()=>new Client("https://test.invalid","bella_"+new string('x',43),new VozPastas(pedidos));
                    var abriu=fila.Enviar("abra Biblioteca",null,arquivos,vozConfigurada,null).GetAwaiter().GetResult();
                    Check(abriu.CodigoVoz=="aberto" && abriu.ExigirVozConfigurada && abriu.mime=="audio/mpeg" && abriu.audio_base64=="SUQz","abertura usa áudio da rota configurada");
                    Check(pedidos.Count==1 && pedidos[0].StartsWith("/api/bella/voz-local ") && !pedidos[0].Contains(raiz.Replace("\\","\\\\")),"voz recebe somente código fixo, sem nome ou caminho");
                    pedidos.Clear();
                    var ausente=fila.Enviar("abrir pasta Inexistente",null,arquivos,vozConfigurada,null).GetAwaiter().GetResult();
                    Check(ausente.CodigoVoz=="vazio" && pedidos.Count==1 && pedidos[0].StartsWith("/api/bella/voz-local "),"ausência pede ElevenLabs sem interpretação de IA");
                    pedidos.Clear();
                    var falado=fila.Enviar(null,new byte[] {1},arquivos,vozConfigurada,null).GetAwaiter().GetResult();
                    Check(falado.CodigoVoz=="aberto" && pedidos.Count==2 && pedidos[0].StartsWith("/api/bella/transcrever ") && pedidos[1].StartsWith("/api/bella/voz-local "),"voz transcreve uma vez e responde pela rota ElevenLabs");
                    var parecido=arquivos.Atender("abra a pasta do Solobote");
                    Check(parecido.CodigoVoz=="aberto" && abertos.Last()==Path.Combine(raiz,"Solo Bot"),"transcrição Solobote abre Solo Bot quando é o único resultado");
                    bool semFallback=false;
                    using(var player=new Playback()) {
                        try { player.Say(new Reply {ExigirVozConfigurada=true,falar="Não usar voz do Windows"}).GetAwaiter().GetResult(); }
                        catch(InvalidOperationException e) {semFallback=e.Message.Contains("ElevenLabs");}
                    }
                    Check(semFallback,"falha do áudio configurado não troca silenciosamente para voz do Windows");
                    var repeticoes=Stopwatch.StartNew();
                    for(int i=0;i<300;i++) Check(indice.Buscar("Biblioteca").Caminhos.Single()==biblioteca,"cache estável");
                    repeticoes.Stop();
                    Check(leituras==primeiraLeitura,"300 consultas não enumeram novamente o disco");
                    Check(repeticoes.ElapsedMilliseconds<2000,"consultas ao cache têm limite folgado de dois segundos");
                    Console.WriteLine("Pastas: "+indice.Quantidade+" diretórios; carga sintética "+carga.ElapsedMilliseconds+" ms; 300 consultas "+repeticoes.ElapsedMilliseconds+" ms; nenhuma nova enumeração.");
                    string nova=Path.Combine(raiz,"Adicionada"); Directory.CreateDirectory(nova);
                    Check(indice.Buscar("Adicionada").Caminhos.Length==0,"não varre disco a cada nome ausente");
                    agora=agora.AddMinutes(16); Pronto(indice);
                    Check(indice.Buscar("Adicionada").Caminhos.Single()==nova && leituras>primeiraLeitura,"índice é atualizado após validade");
                    var antigo=arquivos.Atender("procure pasta Biblioteca");
                    Directory.Delete(biblioteca);
                    Check(arquivos.Atender(antigo.opcoes[0].comando).CodigoVoz=="erro","reconfere pasta removida antes da abertura");
                }
                // Mantém o trabalhador bloqueado: a pasta única deve abrir sem esperar o restante do disco.
                using(var entrou=new ManualResetEvent(false)) using(var liberar=new ManualResetEvent(false)) {
                    using(var parcial=new IndicePastas(()=>new[] {permitida},p=> {
                        entrou.Set(); liberar.WaitOne(); return new string[0];
                    },pauseMilliseconds:0)) {
                        try {
                            parcial.Iniciar(); Check(entrou.WaitOne(2000),"varredura parcial começou");
                            var abertos=new List<string>();
                            var files=new Arquivos(()=>new string[0],p=>abertos.Add(p),folderIndex:parcial);
                            var abrir=files.Processar("abra a pasta permitida");
                            Check(abrir.Wait(2000),"resultado único não espera conclusão do índice");
                            Check(abrir.Result.CodigoVoz=="aberto" && abertos.SequenceEqual(new[] {permitida}) && parcial.Trabalhando,
                                "uma pasta em busca parcial abre diretamente, uma única vez");
                            var buscar=files.Atender("procure pasta permitida");
                            Check(buscar.CodigoVoz=="escolha" && abertos.Count==1,"pedido de pesquisa permanece sem abertura automática");
                        } finally {liberar.Set();}
                        Pronto(parcial);
                    }
                }
                AguardarResultado(raiz,permitida);
                using(var limitado=new IndicePastas(()=>new[] {raiz},maxDirectories:2,pauseMilliseconds:0)) {
                    Pronto(limitado); Check(limitado.Quantidade<=2,"limite contém memória e fila de trabalho");
                    Check(!limitado.Buscar("Projetos").Completa,"índice truncado informa busca parcial");
                }
                using(var entrada=new ManualResetEvent(false)) using(var liberar=new ManualResetEvent(false)) {
                    int trabalhadores=0;
                    using(var lento=new IndicePastas(()=>new[] {raiz},p=> {Interlocked.Increment(ref trabalhadores); entrada.Set(); liberar.WaitOne(); return new string[0];},waitMilliseconds:30)) {
                        try {
                            lento.Iniciar(); Check(entrada.WaitOne(2000),"worker começou");
                            for(int i=0;i<10;i++) lento.Iniciar();
                            var tempo=Stopwatch.StartNew(); var parcial=lento.Buscar("ausente");
                            Check(!parcial.Completa && tempo.ElapsedMilliseconds<500,"busca responde sem esperar disco lento");
                            Check(trabalhadores==1,"pedidos simultâneos não iniciam múltiplas varreduras");
                            lento.Dispose(); Check(lento.Encerrado,"encerramento cancela trabalho futuro");
                        } finally { liberar.Set(); }
                    }
                }
            } finally {
                string full=Path.GetFullPath(raiz), esperado=Path.GetFullPath(baseDirectory).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
                if(!full.StartsWith(esperado,StringComparison.OrdinalIgnoreCase)) throw new Exception("Fixture fora da pasta de teste.");
                if(Directory.Exists(raiz)) Directory.Delete(raiz,true);
            }
        }
    }
}