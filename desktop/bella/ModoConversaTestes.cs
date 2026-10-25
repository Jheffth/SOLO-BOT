using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace Bella {
    internal static class ModoConversaTestes {
        static void Check(bool ok,string erro) {if(!ok) throw new Exception("Modo de conversa: "+erro);}
        sealed class Editor : IEditorWord {
            public int Chamadas;
            public string Executar(string texto) {Chamadas++; return "Documento pronto";}
        }
        sealed class Rede : HttpMessageHandler {
            public readonly List<string> Rotas=new List<string>();
            public string Id; public bool Safada;
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                string rota=r.RequestUri.AbsolutePath, body=await r.Content.ReadAsStringAsync(); Rotas.Add(rota);
                var dados=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(body);
                object saida;
                if(rota.EndsWith("/programa")) {
                    Check(Safada ? (string)dados["modo"]=="safada" : !dados.ContainsKey("modo"),"modo do Word e compatibilidade com servidor antigo");
                    saida=new {comando_id=Id,acao="escrever",texto="Um sorriso para você."};
                } else if(rota.EndsWith("/conversa")) {
                    Check((string)dados["modo"]=="safada" && (bool)dados["voz_separada"],"conversa pede geração e voz separadas");
                    saida=new {texto="Um sorriso para você.",falar="Um sorriso para você.",voz_id="voz-teste",opcoes=new object[0]};
                } else if(rota.EndsWith("/mensagem")) {
                    Check(((string)dados["texto"]).StartsWith("/fin"),"comando explícito segue para os sistemas");
                    saida=new {texto="Saldo pronto",falar="Saldo pronto",opcoes=new object[0]};
                } else {
                    Check(rota.EndsWith("/voz-local") || rota.EndsWith("/voz-resposta"),"rota esperada");
                    saida=new {falar="Pronto.",audio_base64="SUQz",mime="audio/mpeg"};
                }
                return new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent(new JavaScriptSerializer().Serialize(saida),Encoding.UTF8,"application/json")};
            }
        }
        public static void Run() {
            var serializer=new JavaScriptSerializer();
            Check(!serializer.Deserialize<Settings>("{}").ModoSafada,"configuração antiga começa com modo desligado");
            Check(serializer.Deserialize<Settings>(serializer.Serialize(new Settings {ModoSafada=true})).ModoSafada,"preferência pode ser persistida");
            var arquivos=new Arquivos(()=>new string[0]);
            var rede=new Rede();
            Func<Client> cliente=()=>new Client("https://test.invalid","bella_"+new string('x',43),rede);
            int exibidas=0;
            var fila=new PedidosWindows();
            var r=fila.Enviar("Fale uma mensagem para mim",null,arquivos,cliente,null,null,x=>exibidas++,null,true).GetAwaiter().GetResult();
            Check(rede.Rotas.Count==2 && rede.Rotas[0].EndsWith("/conversa") && rede.Rotas[1].EndsWith("/voz-resposta") && r.audio_base64=="SUQz" && exibidas==1,"texto pessoal e ElevenLabs uma vez");
            rede.Rotas.Clear();
            fila.Enviar("/fin saldo",null,arquivos,cliente,null,safada:true).GetAwaiter().GetResult();
            Check(rede.Rotas.Count==1 && rede.Rotas[0].EndsWith("/mensagem"),"prefixo de sistema preservado no modo pessoal");
            var c=new ComandoPasta {Tipo="word",Frase="Escreva {pedido}"}; var editor=new Editor();
            var programas=new Programas(()=>new[] {c},editor); rede.Id=c.Id;
            foreach(bool ligado in new[] {false,true}) {
                rede.Rotas.Clear(); rede.Safada=ligado;
                fila.Enviar("Escreva uma mensagem sua para mim",null,arquivos,cliente,null,programas:programas,safada:ligado).GetAwaiter().GetResult();
                Check(rede.Rotas.Count==2 && rede.Rotas[0].EndsWith("/programa") && rede.Rotas[1].EndsWith("/voz-local"),"Word recebe modo, sem cair na conversa pessoal");
            }
            rede.Rotas.Clear();
            fila.Enviar("Escreva Olá, mundo.",null,arquivos,cliente,null,programas:programas,safada:true).GetAwaiter().GetResult();
            Check(editor.Chamadas==3 && rede.Rotas.Count==1 && rede.Rotas[0].EndsWith("/voz-local"),"ditado literal continua sem IA de criação");
        }
    }
}
